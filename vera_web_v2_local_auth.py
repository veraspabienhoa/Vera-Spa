"""PostgreSQL-backed sessions for Vera Spa Web V2.

The browser treats access and refresh tokens as opaque values. Only SHA-256
digests are persisted, so a database read cannot reveal reusable bearer tokens.

Production's ``vera_dev`` role intentionally has no CREATE privilege on the
public schema. Runtime Auth records therefore live in isolated categories inside
the existing ``vera_app_setting`` table rather than requiring deployment-time
DDL. The deploy probe verifies real SELECT/INSERT/UPDATE/DELETE access before
the service is switched away from Supabase Auth.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import unicodedata
from typing import Any

from sqlalchemy import text


ACCESS_TOKEN_PREFIX = "vera_at_"
REFRESH_TOKEN_PREFIX = "vera_rt_"
SESSION_STORE_TABLE = "public.vera_app_setting"
SESSION_CATEGORY = "__vera_local_auth_session_v1__"
ATTEMPT_CATEGORY = "__vera_local_auth_attempt_v1__"
SESSION_RECORD_KIND = "vera_local_auth_session"
ATTEMPT_RECORD_KIND = "vera_local_auth_attempt"
STORE_VERSION = 1
REQUIRED_STORE_COLUMNS = {
    "category",
    "setting_key",
    "value_json",
    "source",
    "updated_by",
    "revision",
    "created_at",
    "updated_at",
}
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{48,160}$")
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def local_auth_enabled() -> bool:
    """Return true only when this service was explicitly switched to local auth."""
    provider = str(os.getenv("VERA_AUTH_PROVIDER") or "supabase").strip().lower()
    return provider in {"local", "postgres", "postgresql", "vps"}


def _bounded_env_seconds(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def access_ttl_seconds() -> int:
    return _bounded_env_seconds("VERA_LOCAL_ACCESS_TTL_SECONDS", 15 * 60, 5 * 60, 2 * 60 * 60)


def refresh_ttl_seconds() -> int:
    return _bounded_env_seconds("VERA_LOCAL_REFRESH_TTL_SECONDS", 7 * 24 * 60 * 60, 60 * 60, 30 * 24 * 60 * 60)


def new_access_token() -> str:
    return ACCESS_TOKEN_PREFIX + secrets.token_urlsafe(48)


def new_refresh_token() -> str:
    return REFRESH_TOKEN_PREFIX + secrets.token_urlsafe(48)


def is_local_access_token(value: Any) -> bool:
    return str(value or "").startswith(ACCESS_TOKEN_PREFIX)


def is_local_refresh_token(value: Any) -> bool:
    return str(value or "").startswith(REFRESH_TOKEN_PREFIX)


def valid_local_token(value: Any, *, refresh: bool = False) -> bool:
    token = str(value or "")
    prefix = REFRESH_TOKEN_PREFIX if refresh else ACCESS_TOKEN_PREFIX
    if not token.startswith(prefix) or len(token) > 256:
        return False
    return bool(_TOKEN_PATTERN.fullmatch(token[len(prefix):]))


def token_digest(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _canonical_username(value: Any) -> str:
    source = unicodedata.normalize("NFKC", str(value or "").strip())
    return " ".join(source.split()).casefold()


def credential_fingerprint(username: Any, password_value: Any) -> str:
    """Invalidate sessions automatically when a password or username changes."""
    payload = (
        "vera-local-credential-v1\0"
        + _canonical_username(username)
        + "\0"
        + str(password_value or "")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_local_auth_store(conn, *, write_probe: bool = False) -> None:
    if not bool(conn.execute(
        text("SELECT has_schema_privilege(current_user, 'public', 'USAGE')")
    ).scalar_one()):
        raise RuntimeError("runtime role lacks USAGE on schema public")

    exists = conn.execute(
        text("SELECT to_regclass(:table_name)"),
        {"table_name": SESSION_STORE_TABLE},
    ).scalar_one_or_none()
    if not exists:
        raise RuntimeError("missing PostgreSQL runtime store: vera_app_setting")

    columns = {
        str(row[0])
        for row in conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='vera_app_setting'
        """))
    }
    missing_columns = sorted(REQUIRED_STORE_COLUMNS - columns)
    if missing_columns:
        raise RuntimeError("incomplete vera_app_setting schema: " + ", ".join(missing_columns))

    privileges = conn.execute(text("""
        SELECT
          has_table_privilege(current_user, :table_name, 'SELECT') AS can_select,
          has_table_privilege(current_user, :table_name, 'INSERT') AS can_insert,
          has_table_privilege(current_user, :table_name, 'UPDATE') AS can_update,
          has_table_privilege(current_user, :table_name, 'DELETE') AS can_delete
    """), {"table_name": SESSION_STORE_TABLE}).mappings().one()
    if not all(bool(privileges.get(key)) for key in ("can_select", "can_insert", "can_update", "can_delete")):
        raise RuntimeError("runtime role lacks CRUD access to vera_app_setting")

    if not write_probe:
        return

    probe_id = "probe-" + secrets.token_hex(16)
    probe_payload = json.dumps({"kind": "local_auth_probe", "state": 1})
    inserted = conn.execute(text(f"""
        INSERT INTO {SESSION_STORE_TABLE}(
            category, setting_key, value_json, source, updated_by,
            revision, created_at, updated_at
        ) VALUES (
            :category, :setting_key, CAST(:payload AS jsonb),
            'local_auth', 'deploy_probe', 1, NOW(), NOW()
        )
        RETURNING setting_key
    """), {
        "category": SESSION_CATEGORY,
        "setting_key": probe_id,
        "payload": probe_payload,
    }).scalar_one()
    if inserted != probe_id:
        raise RuntimeError("PostgreSQL runtime store insert probe failed")
    updated = conn.execute(text(f"""
        INSERT INTO {SESSION_STORE_TABLE} AS auth_probe(
            category, setting_key, value_json, source, updated_by,
            revision, created_at, updated_at
        ) VALUES (
            :category, :setting_key, CAST(:payload AS jsonb),
            'local_auth', 'deploy_probe', 1, NOW(), NOW()
        )
        ON CONFLICT (category, setting_key) DO UPDATE SET
          value_json=auth_probe.value_json || jsonb_build_object('state', 2),
          source='local_auth',
          updated_by='deploy_probe',
          revision=auth_probe.revision + 1,
          updated_at=NOW()
        RETURNING value_json->>'state'
    """), {
        "category": SESSION_CATEGORY,
        "setting_key": probe_id,
        "payload": probe_payload,
    }).scalar_one()
    if updated != "2":
        raise RuntimeError("PostgreSQL runtime store update probe failed")
    state = conn.execute(text(f"""
        SELECT value_json->>'state'
        FROM {SESSION_STORE_TABLE}
        WHERE category=:category AND setting_key=:setting_key
    """), {"category": SESSION_CATEGORY, "setting_key": probe_id}).scalar_one()
    if state != "2":
        raise RuntimeError("PostgreSQL runtime store write probe did not round-trip")
    deleted = conn.execute(text(f"""
        DELETE FROM {SESSION_STORE_TABLE}
        WHERE category=:category AND setting_key=:setting_key
    """), {"category": SESSION_CATEGORY, "setting_key": probe_id})
    if int(deleted.rowcount or 0) != 1:
        raise RuntimeError("PostgreSQL runtime store delete probe failed")


def ensure_local_auth_schema(engine, *, migrate: bool = False) -> None:
    """Validate the existing runtime store; deploy mode also performs a CRUD probe."""
    global _SCHEMA_READY
    if _SCHEMA_READY and not migrate:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY and not migrate:
            return
        if migrate:
            with engine.connect() as conn:
                transaction = conn.begin()
                try:
                    conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                    conn.execute(text("SET LOCAL statement_timeout = '30s'"))
                    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera-local-auth-store-v1'))"))
                    _validate_local_auth_store(conn, write_probe=True)
                finally:
                    # Roll back both the sentinel and any audit-trigger side effects.
                    transaction.rollback()
        else:
            with engine.connect() as conn:
                _validate_local_auth_store(conn)
        _SCHEMA_READY = True


def revoke_local_session_row(conn, session_id: str, reason: str) -> int:
    result = conn.execute(text(f"""
        UPDATE {SESSION_STORE_TABLE}
        SET value_json=value_json || jsonb_build_object(
              'revoked_at', EXTRACT(EPOCH FROM clock_timestamp()),
              'revoke_reason', CAST(:reason AS text)
            ),
            source='local_auth',
            updated_by='system',
            revision=revision + 1,
            updated_at=clock_timestamp()
        WHERE category=:category
          AND setting_key=:session_id
          AND value_json->>'kind'=:kind
          AND value_json->>'version'=:version
          AND value_json->>'revoked_at' IS NULL
    """), {
        "category": SESSION_CATEGORY,
        "session_id": str(session_id or ""),
        "reason": str(reason or "account_changed")[:120],
        "kind": SESSION_RECORD_KIND,
        "version": str(STORE_VERSION),
    })
    return int(result.rowcount or 0)


def revoke_local_sessions(conn, employee_username: str, reason: str) -> int:
    """Revoke every live local session for one canonical employee username."""
    result = conn.execute(text(f"""
        UPDATE {SESSION_STORE_TABLE}
        SET value_json=value_json || jsonb_build_object(
              'revoked_at', EXTRACT(EPOCH FROM clock_timestamp()),
              'revoke_reason', CAST(:reason AS text)
            ),
            source='local_auth',
            updated_by='system',
            revision=revision + 1,
            updated_at=clock_timestamp()
        WHERE category=:category
          AND value_json->>'kind'=:kind
          AND value_json->>'version'=:version
          AND value_json->>'employee_username'=:username
          AND value_json->>'revoked_at' IS NULL
    """), {
        "category": SESSION_CATEGORY,
        "username": str(employee_username or "").strip(),
        "reason": str(reason or "account_changed")[:120],
        "kind": SESSION_RECORD_KIND,
        "version": str(STORE_VERSION),
    })
    return int(result.rowcount or 0)


def main() -> None:
    """Deployment-time store and account validation entrypoint."""
    from vera_web_v2_api import _engine_instance

    engine = _engine_instance()
    ensure_local_auth_schema(engine, migrate=True)
    with engine.connect() as conn:
        linked_profiles = int(conn.execute(text("""
            SELECT COUNT(*)
            FROM public.vera_v2_user_profile p
            JOIN public.employees e ON e.username=p.employee_username
            WHERE p.is_active=true
              AND COALESCE(e.login_locked, false)=false
              AND COALESCE(e.payload->>'__deleted', 'false') <> 'true'
              AND COALESCE(
                    e.payload->>'Trạng thái làm việc',
                    e.payload->>'employment_status',
                    'Đang làm việc'
                  ) = 'Đang làm việc'
        """)).scalar_one())
        admin_profiles = int(conn.execute(text("""
            SELECT COUNT(*)
            FROM public.vera_v2_user_profile p
            JOIN public.employees e ON e.username=p.employee_username
            WHERE lower(btrim(e.username))='admin'
              AND p.is_active=true
              AND COALESCE(e.login_locked, false)=false
              AND COALESCE(e.payload->>'__deleted', 'false') <> 'true'
              AND COALESCE(
                    e.payload->>'Trạng thái làm việc',
                    e.payload->>'employment_status',
                    'Đang làm việc'
                  ) = 'Đang làm việc'
        """)).scalar_one())
    if linked_profiles < 1:
        raise RuntimeError("no active Web V2 profile is linked to an employee")
    if admin_profiles != 1:
        raise RuntimeError("the admin Web V2 profile is missing, inactive, or duplicated")
    print("LOCAL AUTH STORE: PostgreSQL vera_app_setting namespaces ready")


if __name__ == "__main__":
    main()

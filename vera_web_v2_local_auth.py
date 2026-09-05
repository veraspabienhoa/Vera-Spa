"""PostgreSQL-backed sessions for Vera Spa Web V2.

The browser treats access and refresh tokens as opaque values.  Only SHA-256
digests are stored in PostgreSQL, so a database read of the session table does
not reveal reusable bearer tokens.  Authorization data is deliberately not
stored in the token: every API request reloads the linked profile and employee
status from PostgreSQL.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import threading
import unicodedata
from typing import Any

from sqlalchemy import text


ACCESS_TOKEN_PREFIX = "vera_at_"
REFRESH_TOKEN_PREFIX = "vera_rt_"
SESSION_TABLE_NAME = "vera_v2_local_auth_session"
SESSION_TABLE = f"public.{SESSION_TABLE_NAME}"
ATTEMPT_TABLE_NAME = "vera_v2_auth_attempt"
ATTEMPT_TABLE = f"public.{ATTEMPT_TABLE_NAME}"
SCHEMA_VERSION = 1
SCHEMA_VERSION_TABLE = "public.vera_local_auth_schema_version"
REQUIRED_SESSION_COLUMNS = {
    "session_id",
    "auth_user_id",
    "employee_username",
    "access_token_hash",
    "refresh_token_hash",
    "credential_fingerprint",
    "refresh_generation",
    "access_expires_at",
    "refresh_expires_at",
    "created_at",
    "last_refreshed_at",
    "revoked_at",
    "revoke_reason",
}
REQUIRED_ATTEMPT_COLUMNS = {
    "attempt_key",
    "window_started_at",
    "failures",
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


def _validate_local_auth_schema(conn) -> None:
    missing_tables = []
    for table_name in (SESSION_TABLE_NAME, ATTEMPT_TABLE_NAME):
        if not conn.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": f"public.{table_name}"},
        ).scalar_one_or_none():
            missing_tables.append(table_name)
    if missing_tables:
        raise RuntimeError("missing local Auth tables: " + ", ".join(missing_tables))

    for table_name, required_columns in (
        (SESSION_TABLE_NAME, REQUIRED_SESSION_COLUMNS),
        (ATTEMPT_TABLE_NAME, REQUIRED_ATTEMPT_COLUMNS),
    ):
        columns = {
            str(row[0])
            for row in conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:table_name
            """), {"table_name": table_name})
        }
        missing_columns = sorted(required_columns - columns)
        if missing_columns:
            raise RuntimeError(
                f"incomplete {table_name} schema: " + ", ".join(missing_columns)
            )

    row = conn.execute(text("""
        SELECT c.relrowsecurity, c.relforcerowsecurity,
               pg_get_userbyid(c.relowner)=current_user AS owns_table
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=:table_name
    """), {"table_name": SESSION_TABLE_NAME}).mappings().one()
    if (
        not bool(row.get("relrowsecurity"))
        or bool(row.get("relforcerowsecurity"))
        or not bool(row.get("owns_table"))
    ):
        raise RuntimeError("local Auth session table ownership/RLS is not safe for the runtime role")

    constraints = {
        str(row[0]): int(row[1])
        for row in conn.execute(text("""
            SELECT contype, COUNT(*)
            FROM pg_constraint
            WHERE conrelid=to_regclass(:table_name)
            GROUP BY contype
        """), {"table_name": SESSION_TABLE})
    }
    if constraints.get("p", 0) < 1 or constraints.get("u", 0) < 2 or constraints.get("f", 0) < 2:
        raise RuntimeError("local Auth session constraints are incomplete")


def ensure_local_auth_schema(engine, *, migrate: bool = False) -> None:
    """Migrate at deploy time; perform only read-only validation at runtime."""
    global _SCHEMA_READY
    if _SCHEMA_READY and not migrate:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY and not migrate:
            return
        if migrate:
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(text("SET LOCAL statement_timeout = '30s'"))
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera-local-auth-schema-v1'))"))
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA_VERSION_TABLE} (
                        component text PRIMARY KEY,
                        version integer NOT NULL,
                        updated_at timestamptz NOT NULL DEFAULT NOW()
                    )
                """))
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS {ATTEMPT_TABLE} (
                        attempt_key char(64) PRIMARY KEY,
                        window_started_at timestamptz NOT NULL DEFAULT NOW(),
                        failures integer NOT NULL DEFAULT 0,
                        updated_at timestamptz NOT NULL DEFAULT NOW()
                    )
                """))
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS idx_vera_v2_auth_attempt_updated
                    ON {ATTEMPT_TABLE}(updated_at)
                """))
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS {SESSION_TABLE} (
                        session_id uuid PRIMARY KEY,
                        auth_user_id uuid NOT NULL
                            REFERENCES public.vera_v2_user_profile(auth_user_id)
                            ON UPDATE CASCADE ON DELETE CASCADE,
                        employee_username text NOT NULL
                            REFERENCES public.employees(username)
                            ON UPDATE CASCADE ON DELETE CASCADE,
                        access_token_hash char(64) NOT NULL UNIQUE,
                        refresh_token_hash char(64) NOT NULL UNIQUE,
                        credential_fingerprint char(64) NOT NULL,
                        refresh_generation integer NOT NULL DEFAULT 0,
                        access_expires_at timestamptz NOT NULL,
                        refresh_expires_at timestamptz NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT NOW(),
                        last_refreshed_at timestamptz,
                        revoked_at timestamptz,
                        revoke_reason text NOT NULL DEFAULT ''
                    )
                """))
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS idx_vera_v2_local_auth_employee_active
                    ON {SESSION_TABLE}(employee_username, created_at DESC)
                    WHERE revoked_at IS NULL
                """))
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS idx_vera_v2_local_auth_auth_user
                    ON {SESSION_TABLE}(auth_user_id)
                """))
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS idx_vera_v2_local_auth_employee
                    ON {SESSION_TABLE}(employee_username)
                """))
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS idx_vera_v2_local_auth_expiry
                    ON {SESSION_TABLE}(refresh_expires_at)
                """))
                conn.execute(text(f"ALTER TABLE {SESSION_TABLE} ENABLE ROW LEVEL SECURITY"))
                conn.execute(text(f"REVOKE ALL ON TABLE {SESSION_TABLE} FROM PUBLIC"))
                conn.execute(text(f"""
                    INSERT INTO {SCHEMA_VERSION_TABLE} AS versions(component, version, updated_at)
                    VALUES ('local_auth_sessions', :version, NOW())
                    ON CONFLICT (component) DO UPDATE SET
                      version=GREATEST(versions.version, EXCLUDED.version),
                      updated_at=NOW()
                """), {"version": SCHEMA_VERSION})
                _validate_local_auth_schema(conn)
        else:
            with engine.connect() as conn:
                _validate_local_auth_schema(conn)
        _SCHEMA_READY = True


def revoke_local_sessions(conn, employee_username: str, reason: str) -> int:
    """Revoke every live local session if the session table is present."""
    exists = conn.execute(text("SELECT to_regclass(:table_name)"), {
        "table_name": SESSION_TABLE,
    }).scalar_one_or_none()
    if not exists:
        return 0
    result = conn.execute(text(f"""
        UPDATE {SESSION_TABLE}
        SET revoked_at=COALESCE(revoked_at, NOW()), revoke_reason=:reason
        WHERE employee_username=:username AND revoked_at IS NULL
    """), {
        "username": str(employee_username or "").strip(),
        "reason": str(reason or "account_changed")[:120],
    })
    return int(result.rowcount or 0)


def main() -> None:
    """Deployment-time schema validation entrypoint."""
    from vera_web_v2_api import _engine_instance

    engine = _engine_instance()
    ensure_local_auth_schema(engine, migrate=True)
    with engine.connect() as conn:
        conn.execute(text(f"SELECT 1 FROM {SESSION_TABLE} LIMIT 1"))
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
    print("LOCAL AUTH SCHEMA: PostgreSQL session storage ready")


if __name__ == "__main__":
    main()

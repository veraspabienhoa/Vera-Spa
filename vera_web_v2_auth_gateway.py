"""Server-side authentication gateway for Web V2.

The browser talks only to api.veraspa.vn.  Production VPS deployments use
opaque PostgreSQL sessions, so login remains available when external identity
services are unavailable.  The Supabase path remains only for deployments that
have not explicitly selected the local provider.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
import time
import unicodedata
import uuid
from typing import Any, Callable

import google.auth
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from google.auth.transport.requests import AuthorizedSession
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_web_v2_local_auth import (
    ATTEMPT_TABLE,
    SESSION_TABLE,
    access_ttl_seconds,
    credential_fingerprint,
    ensure_local_auth_schema,
    is_local_refresh_token,
    local_auth_enabled,
    new_access_token,
    new_refresh_token,
    refresh_ttl_seconds,
    token_digest,
    valid_local_token,
)


_RETRYABLE_STATUS = {502, 503, 504}
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}
_HTTP = requests.Session()
_HTTP.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=20))
_SERVICE_ROLE_CACHE = ""


class VeraLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class VeraRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class VeraLogoutRequest(BaseModel):
    refresh_token: str = Field(default="", max_length=4096)


def _post_with_retry(url: str, *, headers: dict[str, str], payload: dict[str, Any]):
    last_error: requests.RequestException | None = None
    for attempt in range(2):
        try:
            response = _HTTP.post(url, headers=headers, json=payload, timeout=(4, 12))
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.35)
                continue
            raise HTTPException(503, "Dịch vụ đăng nhập tạm thời chưa kết nối được.") from exc
        if response.status_code not in _RETRYABLE_STATUS or attempt == 1:
            return response
        time.sleep(0.35)
    raise HTTPException(503, "Dịch vụ đăng nhập tạm thời chưa kết nối được.") from last_error


def _request_with_retry(method: str, url: str, *, headers: dict[str, str], payload: dict[str, Any] | None = None):
    last_error: requests.RequestException | None = None
    for attempt in range(2):
        try:
            response = _HTTP.request(
                method,
                url,
                headers=headers,
                json=payload if payload is not None else None,
                timeout=(4, 12),
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.35)
                continue
            raise HTTPException(503, "Dịch vụ Supabase Auth tạm thời chưa kết nối được.") from exc
        if response.status_code not in _RETRYABLE_STATUS or attempt == 1:
            return response
        time.sleep(0.35)
    raise HTTPException(503, "Dịch vụ Supabase Auth tạm thời chưa kết nối được.") from last_error


def _response_json(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _raise_upstream_error(response, *, default_message: str) -> None:
    payload = _response_json(response)
    error_code = str(payload.get("error_code") or payload.get("code") or "").strip()
    if response.status_code == 402:
        print(f"Web V2 auth: Supabase service restricted (code={error_code or 'unknown'})")
        raise HTTPException(
            503,
            "Dịch vụ Supabase đang bị giới hạn quota; VPS Auth sẽ được sử dụng khi đã bật cấu hình local.",
        )
    message = str(
        payload.get("message")
        or payload.get("msg")
        or payload.get("error_description")
        or payload.get("error")
        or ""
    ).strip()
    if response.status_code in {400, 401, 403, 404, 409, 422, 429} and message:
        raise HTTPException(response.status_code, message[:300])
    raise HTTPException(503, default_message)


def _public_session(payload: dict[str, Any]) -> dict[str, Any]:
    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or "")
    user = payload.get("user")
    if not access_token or not refresh_token or not isinstance(user, dict):
        raise HTTPException(503, "Supabase không trả về phiên đăng nhập hợp lệ.")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": str(payload.get("token_type") or "bearer"),
        "expires_in": int(payload.get("expires_in") or 3600),
        "expires_at": int(payload.get("expires_at") or 0),
        "user": user,
    }


def _normalize(value: Any) -> str:
    source = unicodedata.normalize("NFD", str(value or ""))
    source = "".join(ch for ch in source if unicodedata.category(ch) != "Mn")
    return " ".join(source.replace("đ", "d").replace("Đ", "D").strip().split()).lower()


def _locked(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalize(value) in {"1", "true", "yes", "y", "khoa", "locked", "x"}


def _employment_status(payload: Any) -> str:
    source = payload if isinstance(payload, dict) else {}
    return _normalize(source.get("Trạng thái làm việc") or source.get("employment_status") or "Đang làm việc")


def _engine_instance():
    import vera_web_v2_api_shared as shared
    return shared._api._engine_instance()


def _service_role_key() -> str:
    global _SERVICE_ROLE_CACHE
    if _SERVICE_ROLE_CACHE:
        return _SERVICE_ROLE_CACHE

    direct = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if direct:
        _SERVICE_ROLE_CACHE = direct
        return direct

    try:
        project_id = str(os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or "vera-hr-app").strip()
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(credentials)
        url = (
            "https://secretmanager.googleapis.com/v1/projects/"
            f"{project_id}/secrets/vera-supabase-service-role-key/versions/latest:access"
        )
        response = session.get(url, timeout=10)
        response.raise_for_status()
        encoded = str((response.json().get("payload") or {}).get("data") or "")
        key = base64.b64decode(encoded).decode("utf-8").strip() if encoded else ""
        if key:
            _SERVICE_ROLE_CACHE = key
            return key
    except Exception as exc:
        print(f"Web V2 auth: cannot load service-role secret: {type(exc).__name__}")

    raise HTTPException(503, "API Auth chưa được cấu hình đầy đủ.")


def _supabase_api_headers(key: str) -> dict[str, str]:
    """Build headers compatible with both legacy JWT keys and new sb_* keys.

    New Supabase publishable/secret keys are API keys, not JWTs, so they must
    not be sent as Authorization: Bearer. Legacy anon/service_role JWTs still
    need the Bearer header for backwards compatibility.
    """
    clean = str(key or "").strip()
    if not clean:
        raise HTTPException(503, "API Auth chưa được cấu hình đầy đủ.")
    headers = {
        "apikey": clean,
        "Content-Type": "application/json",
    }
    if not clean.startswith("sb_"):
        headers["Authorization"] = f"Bearer {clean}"
    return headers


def _admin_headers(_supabase_anon_key: str) -> dict[str, str]:
    return _supabase_api_headers(_service_role_key())


def _auth_user_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("user")
    if isinstance(nested, dict):
        return nested
    return payload


def _update_auth_user(
    supabase_url: str,
    headers: dict[str, str],
    auth_user_id: str,
    body: dict[str, Any],
    *,
    missing_ok: bool = False,
) -> dict[str, Any] | None:
    response = _request_with_retry(
        "PUT",
        f"{supabase_url}/auth/v1/admin/users/{auth_user_id}",
        headers=headers,
        payload=body,
    )
    if missing_ok and response.status_code == 404:
        return None
    if response.status_code not in {200, 201}:
        _raise_upstream_error(response, default_message="Không cập nhật được tài khoản xác thực VERA.")
    return _auth_user_from_payload(_response_json(response))


def _create_or_update_auth_user(
    *,
    supabase_url: str,
    supabase_anon_key: str,
    auth_user_id: str,
    internal_email: str,
    ephemeral_password: str,
    metadata: dict[str, Any],
) -> str:
    headers = _admin_headers(supabase_anon_key)
    body = {
        "email": internal_email,
        "password": ephemeral_password,
        "email_confirm": True,
        "user_metadata": metadata,
    }
    if auth_user_id:
        user = _update_auth_user(
            supabase_url,
            headers,
            auth_user_id,
            body,
            missing_ok=True,
        )
        if user:
            return str(user.get("id") or auth_user_id)

    response = _request_with_retry(
        "POST",
        f"{supabase_url}/auth/v1/admin/users",
        headers=headers,
        payload=body,
    )
    if response.status_code in {200, 201}:
        user = _auth_user_from_payload(_response_json(response))
        created_id = str(user.get("id") or "").strip()
        if created_id:
            return created_id

    listed = _request_with_retry(
        "GET",
        f"{supabase_url}/auth/v1/admin/users?page=1&per_page=1000",
        headers=headers,
    )
    if listed.status_code == 200:
        users = _response_json(listed).get("users") or []
        if isinstance(users, list):
            existing = next(
                (
                    item for item in users
                    if isinstance(item, dict)
                    and str(item.get("email") or "").lower() == internal_email.lower()
                ),
                None,
            )
            existing_id = str((existing or {}).get("id") or "").strip()
            if existing_id:
                _update_auth_user(supabase_url, headers, existing_id, body)
                return existing_id

    _raise_upstream_error(response, default_message="Không tạo được tài khoản xác thực VERA.")
    raise HTTPException(503, "Không tạo được tài khoản xác thực VERA.")


def _attempt_state(attempt_key: str) -> tuple[bool, int]:
    try:
        with _engine_instance().connect() as conn:
            row = conn.execute(text(f"""
                SELECT failures,
                       COALESCE(window_started_at >= NOW() - INTERVAL '15 minutes', false) AS active
                FROM {ATTEMPT_TABLE}
                WHERE attempt_key=:attempt_key
                LIMIT 1
            """), {"attempt_key": attempt_key}).mappings().first()
        if not row:
            return False, 0
        return bool(row.get("active")), int(row.get("failures") or 0)
    except Exception as exc:
        print(f"Web V2 auth: attempt-state unavailable: {type(exc).__name__}")
        return False, 0


def _record_failed_attempt(attempt_key: str) -> int:
    try:
        with _engine_instance().begin() as conn:
            conn.execute(text(f"""
                DELETE FROM {ATTEMPT_TABLE}
                WHERE updated_at < NOW() - INTERVAL '7 days'
            """))
            row = conn.execute(text(f"""
                INSERT INTO {ATTEMPT_TABLE} AS attempts(
                    attempt_key, window_started_at, failures, updated_at
                )
                VALUES (:attempt_key, NOW(), 1, NOW())
                ON CONFLICT (attempt_key) DO UPDATE SET
                  failures = CASE
                    WHEN attempts.window_started_at < NOW() - INTERVAL '15 minutes' THEN 1
                    ELSE attempts.failures + 1
                  END,
                  window_started_at = CASE
                    WHEN attempts.window_started_at < NOW() - INTERVAL '15 minutes' THEN NOW()
                    ELSE attempts.window_started_at
                  END,
                  updated_at = NOW()
                RETURNING failures
            """), {"attempt_key": attempt_key}).first()
        return int(row[0] if row else 1)
    except Exception as exc:
        print(f"Web V2 auth: failed-attempt tracking unavailable: {type(exc).__name__}")
        return 1


def _clear_attempt(attempt_key: str) -> None:
    try:
        with _engine_instance().begin() as conn:
            conn.execute(
                text(f"DELETE FROM {ATTEMPT_TABLE} WHERE attempt_key=:attempt_key"),
                {"attempt_key": attempt_key},
            )
    except Exception as exc:
        print(f"Web V2 auth: attempt cleanup unavailable: {type(exc).__name__}")


def _load_employee(username_key: str) -> dict[str, Any] | None:
    with _engine_instance().connect() as conn:
        rows = conn.execute(text("""
            SELECT username, password_value, role, full_name, email, login_locked, payload
            FROM employees
            WHERE COALESCE(payload->>'__deleted', 'false') <> 'true'
            LIMIT 500
        """)).mappings().all()
    return next((dict(row) for row in rows if _normalize(row.get("username")) == username_key), None)


def _existing_profile_auth_user_id(employee_username: str) -> str:
    with _engine_instance().connect() as conn:
        row = conn.execute(text("""
            SELECT auth_user_id
            FROM vera_v2_user_profile
            WHERE employee_username=:username
            LIMIT 1
        """), {"username": employee_username}).first()
    return str(row[0] if row and row[0] else "")


def _persist_profile_link(*, auth_user_id: str, employee: dict[str, Any], is_first_web_login: bool) -> None:
    username = str(employee.get("username") or "")
    role = str(employee.get("role") or "nhanvien").lower()
    with _engine_instance().begin() as conn:
        if is_first_web_login:
            conn.execute(text("""
                UPDATE employees
                SET payload=jsonb_set(COALESCE(payload, '{}'::jsonb), '{must_change_password}', 'true'::jsonb, true)
                WHERE username=:username
            """), {"username": username})
        conn.execute(text("""
            INSERT INTO vera_v2_user_profile(auth_user_id, employee_username, role, is_active, updated_at)
            VALUES (CAST(:auth_user_id AS uuid), :username, :role, true, NOW())
            ON CONFLICT (auth_user_id) DO UPDATE SET
              employee_username=EXCLUDED.employee_username,
              role=EXCLUDED.role,
              is_active=true,
              updated_at=NOW()
        """), {
            "auth_user_id": auth_user_id,
            "username": username,
            "role": role,
        })


def _local_user_payload(auth_user_id: str, employee: dict[str, Any]) -> dict[str, Any]:
    username = str(employee.get("username") or "").strip()
    return {
        "id": auth_user_id,
        "aud": "authenticated",
        "role": "authenticated",
        "email": str(employee.get("email") or "").strip(),
        "app_metadata": {"provider": "vera-local", "providers": ["vera-local"]},
        "user_metadata": {
            "employee_username": username,
            "full_name": employee.get("full_name") or username,
            "role": employee.get("role") or "nhanvien",
        },
    }


def _local_session_response(
    *,
    access_token: str,
    refresh_token: str,
    access_expires_at: datetime,
    auth_user_id: str,
    employee: dict[str, Any],
) -> dict[str, Any]:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": access_ttl_seconds(),
        "expires_at": int(access_expires_at.timestamp()),
        "user": _local_user_payload(auth_user_id, employee),
    }


def _ensure_local_auth_ready() -> None:
    try:
        ensure_local_auth_schema(_engine_instance())
    except Exception as exc:
        print(f"Web V2 local auth: session schema unavailable: {type(exc).__name__}")
        raise HTTPException(503, "Kho phiên đăng nhập PostgreSQL chưa sẵn sàng.") from exc


def _create_local_session(employee: dict[str, Any]) -> dict[str, Any]:
    """Issue a revocable opaque session for an already-linked Web V2 user."""
    _ensure_local_auth_ready()
    username = str(employee.get("username") or "").strip()
    access_token = new_access_token()
    refresh_token = new_refresh_token()
    now = datetime.now(timezone.utc)
    access_expires_at = now + timedelta(seconds=access_ttl_seconds())
    refresh_expires_at = now + timedelta(seconds=refresh_ttl_seconds())
    session_id = str(uuid.uuid4())
    fingerprint = credential_fingerprint(username, employee.get("password_value"))

    try:
        with _engine_instance().begin() as conn:
            profile = conn.execute(text("""
                SELECT auth_user_id::text AS auth_user_id, is_active
                FROM vera_v2_user_profile
                WHERE employee_username=:username AND is_active=true
                ORDER BY updated_at DESC
                LIMIT 1
                FOR UPDATE
            """), {"username": username}).mappings().first()
            if not profile:
                raise HTTPException(
                    403,
                    "Tài khoản chưa được liên kết Web V2. Vui lòng liên hệ Admin để kích hoạt.",
                )
            auth_user_id = str(profile.get("auth_user_id") or "").strip()
            try:
                auth_user_id = str(uuid.UUID(auth_user_id))
            except (TypeError, ValueError, AttributeError) as exc:
                raise HTTPException(503, "Liên kết tài khoản Web V2 không hợp lệ.") from exc

            conn.execute(text(f"""
                DELETE FROM {SESSION_TABLE}
                WHERE refresh_expires_at < NOW() - INTERVAL '7 days'
                   OR revoked_at < NOW() - INTERVAL '7 days'
            """))
            conn.execute(text(f"""
                INSERT INTO {SESSION_TABLE}(
                    session_id, auth_user_id, employee_username,
                    access_token_hash, refresh_token_hash,
                    credential_fingerprint, access_expires_at,
                    refresh_expires_at, created_at
                ) VALUES (
                    CAST(:session_id AS uuid), CAST(:auth_user_id AS uuid), :username,
                    :access_hash, :refresh_hash,
                    :credential_fingerprint, :access_expires_at,
                    :refresh_expires_at, NOW()
                )
            """), {
                "session_id": session_id,
                "auth_user_id": auth_user_id,
                "username": username,
                "access_hash": token_digest(access_token),
                "refresh_hash": token_digest(refresh_token),
                "credential_fingerprint": fingerprint,
                "access_expires_at": access_expires_at,
                "refresh_expires_at": refresh_expires_at,
            })
            conn.execute(text(f"""
                WITH stale AS (
                    SELECT session_id
                    FROM {SESSION_TABLE}
                    WHERE employee_username=:username AND revoked_at IS NULL
                    ORDER BY created_at DESC
                    OFFSET 10
                )
                UPDATE {SESSION_TABLE} AS target
                SET revoked_at=NOW(), revoke_reason='session_limit'
                FROM stale
                WHERE target.session_id=stale.session_id
            """), {"username": username})
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Web V2 local auth: cannot create session: {type(exc).__name__}")
        raise HTTPException(503, "Không tạo được phiên đăng nhập PostgreSQL.") from exc

    return _local_session_response(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_expires_at,
        auth_user_id=auth_user_id,
        employee=employee,
    )


def _rotate_local_session(refresh_token: str) -> dict[str, Any]:
    if not valid_local_token(refresh_token, refresh=True):
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
    _ensure_local_auth_ready()
    new_access_token_value = new_access_token()
    new_refresh_token_value = new_refresh_token()
    now = datetime.now(timezone.utc)
    access_expires_at = now + timedelta(seconds=access_ttl_seconds())
    credential_changed = False

    try:
        with _engine_instance().begin() as conn:
            row = conn.execute(text(f"""
                SELECT s.session_id::text AS session_id,
                       s.auth_user_id::text AS auth_user_id,
                       s.employee_username,
                       s.credential_fingerprint,
                       s.refresh_generation,
                       p.is_active AS profile_active,
                       e.password_value, e.role, e.full_name, e.email,
                       e.login_locked, e.payload
                FROM {SESSION_TABLE} s
                JOIN vera_v2_user_profile p
                  ON p.auth_user_id=s.auth_user_id
                 AND p.employee_username=s.employee_username
                JOIN employees e ON e.username=s.employee_username
                WHERE s.refresh_token_hash=:refresh_hash
                  AND s.revoked_at IS NULL
                  AND s.refresh_expires_at > NOW()
                  AND COALESCE(e.payload->>'__deleted', 'false') <> 'true'
                LIMIT 1
                FOR UPDATE OF s
            """), {"refresh_hash": token_digest(refresh_token)}).mappings().first()
            if not row:
                raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
            employee = dict(row)
            if not bool(row.get("profile_active")):
                raise HTTPException(403, "Tài khoản Web V2 đang bị vô hiệu hóa.")
            if _locked(row.get("login_locked")):
                raise HTTPException(403, "Tài khoản đang bị khóa.")
            if _employment_status(row.get("payload")) != "dang lam viec":
                raise HTTPException(403, "Tài khoản không còn ở trạng thái Đang làm việc.")
            expected_fingerprint = credential_fingerprint(
                row.get("employee_username"),
                row.get("password_value"),
            )
            if not hmac.compare_digest(
                str(row.get("credential_fingerprint") or ""),
                expected_fingerprint,
            ):
                conn.execute(text(f"""
                    UPDATE {SESSION_TABLE}
                    SET revoked_at=NOW(), revoke_reason='credential_changed'
                    WHERE session_id=CAST(:session_id AS uuid)
                """), {"session_id": row["session_id"]})
                credential_changed = True
            else:
                conn.execute(text(f"""
                    UPDATE {SESSION_TABLE}
                    SET access_token_hash=:access_hash,
                        refresh_token_hash=:refresh_hash,
                        access_expires_at=:access_expires_at,
                        refresh_generation=refresh_generation + 1,
                        last_refreshed_at=NOW()
                    WHERE session_id=CAST(:session_id AS uuid)
                """), {
                    "session_id": row["session_id"],
                    "access_hash": token_digest(new_access_token_value),
                    "refresh_hash": token_digest(new_refresh_token_value),
                    "access_expires_at": access_expires_at,
                })
                auth_user_id = str(row.get("auth_user_id") or "")
                employee["username"] = str(row.get("employee_username") or "")
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Web V2 local auth: cannot refresh session: {type(exc).__name__}")
        raise HTTPException(503, "Không làm mới được phiên đăng nhập PostgreSQL.") from exc

    if credential_changed:
        raise HTTPException(401, "Phiên đăng nhập đã bị thu hồi sau khi đổi mật khẩu.")

    return _local_session_response(
        access_token=new_access_token_value,
        refresh_token=new_refresh_token_value,
        access_expires_at=access_expires_at,
        auth_user_id=auth_user_id,
        employee=employee,
    )


def _revoke_local_session(refresh_token: str) -> None:
    if not valid_local_token(refresh_token, refresh=True):
        return
    _ensure_local_auth_ready()
    try:
        with _engine_instance().begin() as conn:
            conn.execute(text(f"""
                UPDATE {SESSION_TABLE}
                SET revoked_at=COALESCE(revoked_at, NOW()), revoke_reason='logout'
                WHERE refresh_token_hash=:refresh_hash
            """), {"refresh_hash": token_digest(refresh_token)})
    except Exception as exc:
        print(f"Web V2 local auth: logout revocation unavailable: {type(exc).__name__}")
        raise HTTPException(503, "Chưa thu hồi được phiên đăng nhập PostgreSQL.") from exc


def install_auth_gateway(
    app: FastAPI,
    *,
    supabase_url: str,
    supabase_anon_key: str,
    profile_loader: Callable[[str], dict[str, Any]] | None = None,
    verified_token_callback: Callable[[str, str], None] | None = None,
) -> None:
    if any(getattr(route, "path", "") == "/v2/auth/login" for route in app.routes):
        return

    def _public_headers() -> dict[str, str]:
        if not supabase_url or not supabase_anon_key:
            raise HTTPException(503, "API Auth chưa được cấu hình.")
        return _supabase_api_headers(supabase_anon_key)

    @app.get("/v2/auth/health")
    def auth_health():
        if local_auth_enabled():
            _ensure_local_auth_ready()
            with _engine_instance().connect() as conn:
                linked_profiles = int(conn.execute(text("""
                    SELECT COUNT(*)
                    FROM vera_v2_user_profile p
                    JOIN employees e ON e.username=p.employee_username
                    WHERE p.is_active=true
                      AND COALESCE(e.login_locked, false)=false
                      AND COALESCE(e.payload->>'__deleted', 'false') <> 'true'
                      AND COALESCE(
                            e.payload->>'Trạng thái làm việc',
                            e.payload->>'employment_status',
                            'Đang làm việc'
                          ) = 'Đang làm việc'
                """)).scalar_one())
                conn.execute(text(f"SELECT 1 FROM {SESSION_TABLE} LIMIT 1"))
            if linked_profiles < 1:
                raise HTTPException(503, "Chưa có tài khoản Web V2 hoạt động trong PostgreSQL.")
            return {
                "ok": True,
                "provider": "postgres-local",
            }
        return {
            "ok": bool(supabase_url and supabase_anon_key),
            "provider": "supabase",
        }

    @app.post("/v2/auth/login")
    def login(body: VeraLoginRequest, request: Request):
        username = body.username.strip()
        if not username:
            raise HTTPException(400, "Tên đăng nhập hoặc mật khẩu không hợp lệ.")

        username_key = _normalize(username)
        # The right-most hop is appended by the trusted edge proxy.  Taking the
        # first value would let a client-supplied X-Forwarded-For evade limits.
        forwarded = str(request.headers.get("x-forwarded-for") or "").split(",")[-1].strip()
        client_ip = forwarded or str(getattr(request.client, "host", "") or "unknown")
        attempt_key = hashlib.sha256(f"{username_key}|{client_ip}".encode("utf-8")).hexdigest()
        active_window, failures = _attempt_state(attempt_key)
        if active_window and failures >= 8:
            raise HTTPException(429, "Đăng nhập tạm khóa 15 phút do thử sai quá nhiều lần.")

        employee = _load_employee(username_key)
        password_matches = bool(
            employee
            and not _locked(employee.get("login_locked"))
            and hmac.compare_digest(
                str(body.password).encode("utf-8"),
                str(employee.get("password_value") or "").encode("utf-8"),
            )
        )
        if not password_matches:
            new_failures = _record_failed_attempt(attempt_key)
            time.sleep(min(1.2, 0.25 + new_failures * 0.1))
            if employee and _locked(employee.get("login_locked")):
                raise HTTPException(401, "Tài khoản đang bị khóa.")
            raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng.")

        if _employment_status(employee.get("payload")) != "dang lam viec":
            raise HTTPException(403, "Tài khoản đang Tạm thời nghỉ việc hoặc Đã nghỉ việc nên không thể đăng nhập.")

        canonical_username = str(employee.get("username") or "")
        if local_auth_enabled():
            session = _create_local_session(employee)
            session_auth_user_id = str(session["user"].get("id") or "").strip()
            if profile_loader:
                profile = profile_loader(canonical_username)
                profile["auth_user_id"] = session_auth_user_id
                session["vera_profile"] = profile
            _clear_attempt(attempt_key)
            return JSONResponse(session, headers=_NO_STORE_HEADERS)

        existing_auth_user_id = _existing_profile_auth_user_id(canonical_username)
        is_first_web_login = not bool(existing_auth_user_id)
        email_hash = hashlib.sha256(_normalize(canonical_username).encode("utf-8")).hexdigest()
        internal_email = f"vera-{email_hash[:32]}@users.veraspa.local"
        ephemeral_password = secrets.token_urlsafe(32)
        metadata = {
            "employee_username": canonical_username,
            "full_name": employee.get("full_name") or canonical_username,
            "role": employee.get("role") or "nhanvien",
        }

        auth_user_id = _create_or_update_auth_user(
            supabase_url=supabase_url,
            supabase_anon_key=supabase_anon_key,
            auth_user_id=existing_auth_user_id,
            internal_email=internal_email,
            ephemeral_password=ephemeral_password,
            metadata=metadata,
        )
        _persist_profile_link(
            auth_user_id=auth_user_id,
            employee=employee,
            is_first_web_login=is_first_web_login,
        )

        token_response = _post_with_retry(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers=_public_headers(),
            payload={"email": internal_email, "password": ephemeral_password},
        )
        if token_response.status_code != 200:
            _raise_upstream_error(
                token_response,
                default_message="Chưa tạo được phiên đăng nhập VERA.",
            )
        session = _public_session(_response_json(token_response))
        session_auth_user_id = str(session["user"].get("id") or auth_user_id).strip()
        if verified_token_callback and session_auth_user_id:
            verified_token_callback(session["access_token"], session_auth_user_id)
        if profile_loader:
            profile = profile_loader(canonical_username)
            profile["auth_user_id"] = session_auth_user_id or str(profile.get("auth_user_id") or "")
            session["vera_profile"] = profile
        _clear_attempt(attempt_key)
        return JSONResponse(session, headers=_NO_STORE_HEADERS)

    @app.post("/v2/auth/refresh")
    def refresh(body: VeraRefreshRequest):
        if local_auth_enabled():
            if not is_local_refresh_token(body.refresh_token):
                raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
            session = _rotate_local_session(body.refresh_token)
            employee_username = str(
                (session.get("user") or {}).get("user_metadata", {}).get("employee_username") or ""
            ).strip()
            if profile_loader and employee_username:
                profile = profile_loader(employee_username)
                profile["auth_user_id"] = str(session["user"].get("id") or "")
                session["vera_profile"] = profile
            return JSONResponse(session, headers=_NO_STORE_HEADERS)
        if is_local_refresh_token(body.refresh_token):
            raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")

        token_response = _post_with_retry(
            f"{supabase_url}/auth/v1/token?grant_type=refresh_token",
            headers=_public_headers(),
            payload={"refresh_token": body.refresh_token},
        )
        if token_response.status_code != 200:
            _raise_upstream_error(
                token_response,
                default_message="Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
            )
        session = _public_session(_response_json(token_response))
        auth_user_id = str(session["user"].get("id") or "").strip()
        if verified_token_callback and auth_user_id:
            verified_token_callback(session["access_token"], auth_user_id)
        return JSONResponse(session, headers=_NO_STORE_HEADERS)

    @app.post("/v2/auth/logout")
    def logout(body: VeraLogoutRequest):
        if is_local_refresh_token(body.refresh_token):
            _revoke_local_session(body.refresh_token)
        return JSONResponse({"ok": True}, headers=_NO_STORE_HEADERS)

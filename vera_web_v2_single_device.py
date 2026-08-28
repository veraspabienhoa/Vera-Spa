"""One-active-device session guard for VERA SPA Web V2.

Supabase remains responsible for authentication. This guard adds a VERA-side
active-device lease keyed by the authenticated Supabase user ID. A successful
fresh login explicitly claims the device; the previous device is rejected on
its next Python API request.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Callable

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text


SINGLE_DEVICE_RELEASE = "single-device-v1"
DEVICE_ID_MAX = 160


def _ensure_table(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_v2_active_device (
            auth_user_id uuid PRIMARY KEY,
            employee_username text NOT NULL DEFAULT '',
            device_id text NOT NULL,
            user_agent text NOT NULL DEFAULT '',
            claimed_at timestamptz NOT NULL DEFAULT NOW(),
            last_seen_at timestamptz NOT NULL DEFAULT NOW()
        )
    """))


def _clean_device_id(value: Any) -> str:
    device_id = str(value or "").strip()
    if not device_id or len(device_id) > DEVICE_ID_MAX:
        raise HTTPException(400, "Mã thiết bị đăng nhập không hợp lệ. Vui lòng tải lại trang.")
    return device_id


def _jwt_subject(token: str) -> str:
    """Read JWT subject only for lease lookup; route auth still verifies token."""
    try:
        segment = token.split('.')[1]
        segment += '=' * (-len(segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(segment.encode('ascii')).decode('utf-8'))
        return str(payload.get('sub') or '').strip()
    except Exception:
        return ''


def _blocked_response(request: Request, status_code: int, content: dict[str, Any]) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=content)
    origin = str(request.headers.get("origin") or "").strip()
    configured = str(os.getenv("VERA_V2_CORS_ORIGINS", "https://veraspabienhoa.github.io") or "")
    allowed = {item.strip() for item in configured.split(",") if item.strip()}
    if origin and origin in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


def install_single_device_guard(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    identity_type,
) -> None:
    if getattr(app.state, "single_device_guard_installed", False):
        return

    @app.get("/v2/device/health")
    def device_health():
        return {"ok": True, "release": SINGLE_DEVICE_RELEASE}

    @app.post("/v2/device/claim")
    def claim_device(
        request: Request,
        device_id: str = Query(min_length=1, max_length=DEVICE_ID_MAX),
        ident: identity_type = Depends(current_identity),
    ):
        clean_id = _clean_device_id(device_id)
        with engine_instance().begin() as conn:
            _ensure_table(conn)
            conn.execute(text("""
                INSERT INTO vera_v2_active_device(
                    auth_user_id, employee_username, device_id, user_agent,
                    claimed_at, last_seen_at
                ) VALUES (
                    CAST(:auth_user_id AS uuid), :employee_username, :device_id,
                    :user_agent, NOW(), NOW()
                )
                ON CONFLICT (auth_user_id) DO UPDATE SET
                    employee_username=EXCLUDED.employee_username,
                    device_id=EXCLUDED.device_id,
                    user_agent=EXCLUDED.user_agent,
                    claimed_at=NOW(),
                    last_seen_at=NOW()
            """), {
                "auth_user_id": ident.auth_user_id,
                "employee_username": ident.employee_username,
                "device_id": clean_id,
                "user_agent": str(request.headers.get("user-agent") or "")[:1000],
            })
        return {
            "ok": True,
            "release": SINGLE_DEVICE_RELEASE,
            "device_id": clean_id,
            "message": "Thiết bị này hiện là thiết bị đăng nhập duy nhất của tài khoản.",
        }

    @app.middleware("http")
    async def enforce_single_device(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/v2/"):
            return await call_next(request)
        if path == "/v2/device/claim" or path.endswith("/health"):
            return await call_next(request)

        authorization = str(request.headers.get("authorization") or "")
        if not authorization.lower().startswith("bearer "):
            return await call_next(request)
        token = authorization.split(" ", 1)[1].strip()
        auth_uid = _jwt_subject(token)
        if not auth_uid:
            return await call_next(request)

        device_id = str(request.query_params.get("device_id") or "").strip()
        if not device_id or len(device_id) > DEVICE_ID_MAX:
            return _blocked_response(request, 428, {
                "detail": "Phiên Web V2 chưa có mã thiết bị. Vui lòng tải lại trang rồi đăng nhập lại.",
                "code": "DEVICE_ID_REQUIRED",
            })

        try:
            with engine_instance().begin() as conn:
                _ensure_table(conn)
                row = conn.execute(text("""
                    SELECT device_id
                    FROM vera_v2_active_device
                    WHERE auth_user_id=CAST(:auth_user_id AS uuid)
                    FOR UPDATE
                """), {"auth_user_id": auth_uid}).mappings().first()
                if row is None:
                    conn.execute(text("""
                        INSERT INTO vera_v2_active_device(
                            auth_user_id, employee_username, device_id, user_agent,
                            claimed_at, last_seen_at
                        ) VALUES (
                            CAST(:auth_user_id AS uuid), '', :device_id, :user_agent,
                            NOW(), NOW()
                        )
                    """), {
                        "auth_user_id": auth_uid,
                        "device_id": device_id,
                        "user_agent": str(request.headers.get("user-agent") or "")[:1000],
                    })
                elif str(row.get("device_id") or "") != device_id:
                    return _blocked_response(request, 409, {
                        "detail": "Tài khoản này đã đăng nhập trên thiết bị khác. Thiết bị hiện tại đã bị đăng xuất.",
                        "code": "DEVICE_CONFLICT",
                    })
                else:
                    conn.execute(text("""
                        UPDATE vera_v2_active_device
                        SET last_seen_at=NOW(), user_agent=:user_agent
                        WHERE auth_user_id=CAST(:auth_user_id AS uuid)
                    """), {
                        "auth_user_id": auth_uid,
                        "user_agent": str(request.headers.get("user-agent") or "")[:1000],
                    })
        except Exception:
            return _blocked_response(request, 503, {
                "detail": "Không kiểm tra được thiết bị đăng nhập. Vui lòng thử lại.",
                "code": "DEVICE_GUARD_UNAVAILABLE",
            })

        return await call_next(request)

    app.state.single_device_guard_installed = True
    app.state.single_device_release = SINGLE_DEVICE_RELEASE

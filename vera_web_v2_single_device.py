"""Durable multi-device session tracking for VERA SPA Web V2.

Supabase remains responsible for authentication and already persists/refreshes
browser sessions. This module keeps lightweight per-device activity records
without invalidating a user's other logged-in devices. That is important for
an employee who keeps the VERA SPA PWA installed on iPhone for lock-screen push
while also using the same account on another browser/device.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Callable

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import text


SINGLE_DEVICE_RELEASE = "multi-device-durable-v2"
DEVICE_ID_MAX = 160


def _ensure_table(conn) -> None:
    # Keep the legacy one-device table untouched for rollback/history. The new
    # composite key lets the same authenticated account remain active on every
    # browser/PWA that it has explicitly logged into.
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_v2_active_device_session (
            auth_user_id uuid NOT NULL,
            device_id text NOT NULL,
            employee_username text NOT NULL DEFAULT '',
            user_agent text NOT NULL DEFAULT '',
            claimed_at timestamptz NOT NULL DEFAULT NOW(),
            last_seen_at timestamptz NOT NULL DEFAULT NOW(),
            PRIMARY KEY (auth_user_id, device_id)
        )
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_vera_v2_active_device_session_seen
        ON vera_v2_active_device_session(last_seen_at DESC)
    """))


def _clean_device_id(value: Any) -> str:
    device_id = str(value or "").strip()
    if not device_id or len(device_id) > DEVICE_ID_MAX:
        raise HTTPException(400, "Mã thiết bị đăng nhập không hợp lệ. Vui lòng tải lại trang.")
    return device_id


def _jwt_subject(token: str) -> str:
    """Read JWT subject only for activity tracking; route auth still verifies it."""
    try:
        segment = token.split('.')[1]
        segment += '=' * (-len(segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(segment.encode('ascii')).decode('utf-8'))
        return str(payload.get('sub') or '').strip()
    except Exception:
        return ''


def _upsert_device(
    conn,
    *,
    auth_user_id: str,
    device_id: str,
    employee_username: str,
    user_agent: str,
) -> None:
    conn.execute(text("""
        INSERT INTO vera_v2_active_device_session(
            auth_user_id, device_id, employee_username, user_agent,
            claimed_at, last_seen_at
        ) VALUES (
            CAST(:auth_user_id AS uuid), :device_id, :employee_username,
            :user_agent, NOW(), NOW()
        )
        ON CONFLICT (auth_user_id, device_id) DO UPDATE SET
            employee_username=CASE
                WHEN EXCLUDED.employee_username <> '' THEN EXCLUDED.employee_username
                ELSE vera_v2_active_device_session.employee_username
            END,
            user_agent=EXCLUDED.user_agent,
            last_seen_at=NOW()
    """), {
        "auth_user_id": auth_user_id,
        "device_id": device_id,
        "employee_username": employee_username,
        "user_agent": user_agent[:1000],
    })


def install_single_device_guard(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    identity_type,
) -> None:
    """Compatibility installer; the old one-device restriction is retired."""
    if getattr(app.state, "single_device_guard_installed", False):
        return

    @app.get("/v2/device/health")
    def device_health():
        return {
            "ok": True,
            "release": SINGLE_DEVICE_RELEASE,
            "mode": "multi_device",
            "durable_login": True,
            "other_devices_are_not_revoked": True,
        }

    @app.post("/v2/device/claim")
    def claim_device(
        request: Request,
        device_id: str = Query(min_length=1, max_length=DEVICE_ID_MAX),
        ident: identity_type = Depends(current_identity),
    ):
        clean_id = _clean_device_id(device_id)
        with engine_instance().begin() as conn:
            _ensure_table(conn)
            _upsert_device(
                conn,
                auth_user_id=ident.auth_user_id,
                device_id=clean_id,
                employee_username=ident.employee_username,
                user_agent=str(request.headers.get("user-agent") or ""),
            )
        return {
            "ok": True,
            "release": SINGLE_DEVICE_RELEASE,
            "device_id": clean_id,
            "message": "Thiết bị đã được duy trì đăng nhập; các thiết bị khác không bị đăng xuất.",
        }

    @app.middleware("http")
    async def track_active_device(request: Request, call_next):
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

        # Device ID is telemetry only. A valid authenticated request is never
        # rejected because another iPhone/desktop session exists.
        device_id = str(request.query_params.get("device_id") or "").strip()
        if device_id and len(device_id) <= DEVICE_ID_MAX:
            try:
                with engine_instance().begin() as conn:
                    _ensure_table(conn)
                    _upsert_device(
                        conn,
                        auth_user_id=auth_uid,
                        device_id=device_id,
                        employee_username="",
                        user_agent=str(request.headers.get("user-agent") or ""),
                    )
            except Exception:
                # Session tracking must never break authentication/navigation.
                pass

        return await call_next(request)

    app.state.single_device_guard_installed = True
    app.state.single_device_release = SINGLE_DEVICE_RELEASE

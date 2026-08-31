"""Global and per-viewer control for attendance break notifications.

Admin can pause/resume all mid-shift-break notifications for every account.
When paused, browser alerts and Web Push deliveries are suppressed. Existing
native break notifications are cleared on every subscribed device.

This installer also exposes the separate Admin-only TourVera cache switch used
to stop the frequent Google Drive -> PostgreSQL cache refresh without turning
off TimeSoft attendance or the independent Auto Check policy engine.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import Depends, HTTPException
from sqlalchemy import text

import vera_tour_cache_control as tour_cache_control
import vera_web_v2_attendance_break_alerts as alerts


RELEASE = "attendance-break-alert-control-2026-08-31-v2-tour-cache"
CATEGORY = "attendance_break_alert_control"
SETTING_KEY = "global"


def _disabled(conn) -> bool:
    value = conn.execute(text("""
        SELECT value_json
        FROM vera_app_setting
        WHERE category=:category AND setting_key=:setting_key
        LIMIT 1
    """), {"category": CATEGORY, "setting_key": SETTING_KEY}).scalar_one_or_none()
    if not isinstance(value, dict):
        return False
    return bool(value.get("disabled"))


def _set_disabled(conn, disabled: bool, actor: str) -> None:
    value = {"disabled": bool(disabled)}
    conn.execute(text("""
        INSERT INTO vera_app_setting(
          category,setting_key,value_json,source,updated_by,revision,created_at,updated_at
        ) VALUES (
          :category,:setting_key,CAST(:value AS jsonb),'web_v2',:actor,1,NOW(),NOW()
        )
        ON CONFLICT(category,setting_key) DO UPDATE SET
          value_json=EXCLUDED.value_json,
          source='web_v2',
          updated_by=EXCLUDED.updated_by,
          revision=vera_app_setting.revision+1,
          updated_at=NOW()
    """), {
        "category": CATEGORY,
        "setting_key": SETTING_KEY,
        "value": json.dumps(value, ensure_ascii=False),
        "actor": actor or "admin",
    })


def _all_subscriptions(conn) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text("""
        SELECT subscription_id::text AS subscription_id, endpoint, p256dh, auth_secret
        FROM vera_v2_push_subscription
        WHERE is_active=true
        ORDER BY updated_at DESC
    """)).mappings().all()]


def install_break_alert_control(
    app,
    *,
    engine_instance: Callable[[], Any],
    api_module,
    current_identity,
    identity_type,
) -> None:
    if getattr(app.state, "break_alert_control_installed", False):
        return

    original_employee_subscriptions = alerts._employee_subscriptions
    original_management_subscriptions = alerts._management_subscriptions
    original_viewer_alerts = alerts._viewer_alerts

    def employee_subscriptions_guarded(conn, username: str):
        if _disabled(conn):
            return []
        return original_employee_subscriptions(conn, username)

    def management_subscriptions_guarded(conn):
        if _disabled(conn):
            return []
        return original_management_subscriptions(conn)

    def viewer_alerts_guarded(facts, ident, now):
        try:
            with engine_instance().connect() as conn:
                if _disabled(conn):
                    return []
        except Exception:
            # A control read failure must not disable safety alerts implicitly.
            pass
        return original_viewer_alerts(facts, ident, now)

    alerts._employee_subscriptions = employee_subscriptions_guarded
    alerts._management_subscriptions = management_subscriptions_guarded
    alerts._viewer_alerts = viewer_alerts_guarded

    @app.get("/v2/attendance/break-alerts/control")
    def get_break_alert_control(ident: identity_type = Depends(current_identity)):
        del ident
        with engine_instance().connect() as conn:
            disabled = _disabled(conn)
        return {
            "ok": True,
            "release": RELEASE,
            "disabled": disabled,
            "scope": "all_accounts",
        }

    @app.put("/v2/attendance/break-alerts/control")
    def update_break_alert_control(
        payload: dict[str, Any],
        ident: identity_type = Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role != "admin":
            raise HTTPException(403, "Chỉ Admin được tắt/bật thông báo nghỉ giữa ca cho mọi tài khoản.")
        disabled = bool(payload.get("disabled"))
        actor = str(getattr(ident, "employee_username", "") or "admin").strip()
        subscriptions: list[dict[str, Any]] = []
        with engine_instance().begin() as conn:
            _set_disabled(conn, disabled, actor)
            if disabled:
                subscriptions = _all_subscriptions(conn)

        push = {"sent": 0, "failed": 0}
        if disabled and subscriptions:
            clear_payload = {
                "kind": "attendance-break-global-disabled",
                "tag": "vera-break-global-disabled",
                "url": alerts.APP_URL,
            }
            deliveries = [{**row, "payload": clear_payload} for row in subscriptions]
            push = alerts._send_payloads(api_module, engine_instance, deliveries)

        return {
            "ok": True,
            "release": RELEASE,
            "disabled": disabled,
            "scope": "all_accounts",
            "push_clear": push,
        }

    @app.get("/v2/attendance/tour-cache/control")
    def get_tour_cache_control(ident: identity_type = Depends(current_identity)):
        del ident
        with engine_instance().connect() as conn:
            state = tour_cache_control.status(conn)
        return {
            "ok": True,
            "release": RELEASE,
            **state,
            "scope": "web_v2_tour_cache",
            "auto_check_unchanged": True,
        }

    @app.put("/v2/attendance/tour-cache/control")
    def update_tour_cache_control(
        payload: dict[str, Any],
        ident: identity_type = Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role != "admin":
            raise HTTPException(403, "Chỉ Admin được tạm dừng hoặc mở lại đồng bộ TourVera cho Web V2.")
        disabled = bool(payload.get("disabled"))
        actor = str(getattr(ident, "employee_username", "") or "admin").strip()
        with engine_instance().begin() as conn:
            tour_cache_control.set_disabled(conn, disabled, actor)
            state = tour_cache_control.status(conn)
        return {
            "ok": True,
            "release": RELEASE,
            **state,
            "scope": "web_v2_tour_cache",
            "auto_check_unchanged": True,
            "message": (
                "Đã tạm dừng đồng bộ TourVera cho cảnh báo nghỉ giữa ca Web V2."
                if disabled else
                "Đã mở lại đồng bộ TourVera; job nền kế tiếp sẽ làm mới cache."
            ),
        }

    @app.get("/v2/attendance/break-alerts/control/health")
    def break_alert_control_health():
        return {
            "ok": True,
            "release": RELEASE,
            "admin_global_control": True,
            "suppresses_browser_alerts": True,
            "suppresses_web_push": True,
            "admin_tour_cache_control": True,
        }

    app.state.break_alert_control_installed = True
    app.state.break_alert_control_release = RELEASE

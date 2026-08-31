"""Global and per-viewer control for attendance break notifications.

Admin can pause/resume all mid-shift-break notifications for every account.
When paused, browser alerts and Web Push deliveries are suppressed. Existing
native break notifications are cleared on every subscribed device.

Admin can also permanently dismiss one concrete break-alert event for every
account. The event key remains stored as an audit tombstone so browser polling
and server-side push dispatch cannot recreate that same alert.

This installer also exposes the separate Admin-only TourVera cache switch used
to stop the frequent Google Drive -> PostgreSQL cache-only refresh without
turning off break alerts, TimeSoft attendance, or the independent Auto Check
policy engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable

from fastapi import Depends, HTTPException
from sqlalchemy import text

import vera_tour_cache_control as tour_cache_control
import vera_web_v2_attendance_break_alerts as alerts


RELEASE = "attendance-break-alert-control-2026-08-31-v4-global-item-delete"
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


def _globally_deleted_keys(conn, keys: list[str]) -> set[str]:
    clean = sorted({str(key or "").strip() for key in keys if str(key or "").strip()})
    if not clean:
        return set()
    rows = conn.execute(text("""
        SELECT setting_key
        FROM vera_app_setting
        WHERE category='attendance_break_alert'
          AND setting_key = ANY(:keys)
          AND COALESCE(value_json->>'globally_deleted_at','') <> ''
    """), {"keys": clean}).scalars().all()
    return {str(value or "").strip() for value in rows if str(value or "").strip()}


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

        visible = original_viewer_alerts(facts, ident, now)
        if not visible:
            return visible
        try:
            with engine_instance().connect() as conn:
                deleted = _globally_deleted_keys(conn, [row.get("key", "") for row in visible])
            if deleted:
                visible = [row for row in visible if str(row.get("key") or "") not in deleted]
        except Exception:
            # Failing to read tombstones should not break normal attendance pages.
            pass
        return visible

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

    @app.delete("/v2/attendance/break-alerts/item")
    def delete_break_alert_for_all_accounts(
        key: str,
        tag: str,
        ident: identity_type = Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role != "admin":
            raise HTTPException(403, "Chỉ Admin được xóa hoàn toàn cảnh báo nghỉ giữa ca cho mọi tài khoản.")

        event_key = str(key or "").strip()
        notification_tag = str(tag or "").strip()
        if not event_key or len(event_key) > 128:
            raise HTTPException(400, "Mã cảnh báo không hợp lệ.")
        if not notification_tag or len(notification_tag) > 240 or not notification_tag.startswith("vera-break-"):
            raise HTTPException(400, "Tag thông báo không hợp lệ.")

        actor = str(getattr(ident, "employee_username", "") or "admin").strip() or "admin"
        deleted_at = datetime.now(timezone.utc).isoformat()
        subscriptions: list[dict[str, Any]] = []
        with engine_instance().begin() as conn:
            state = alerts._ensure_state(conn, event_key)
            state.update({
                "globally_deleted_at": deleted_at,
                "globally_deleted_by": actor,
                # Mark every delivery phase consumed so neither browser polling nor
                # the 5-minute server dispatcher can recreate this exact event.
                "reminder_sent_at": state.get("reminder_sent_at") or deleted_at,
                "overdue_sent_at": state.get("overdue_sent_at") or deleted_at,
                "cleared_at": state.get("cleared_at") or deleted_at,
            })
            alerts._save_state(conn, event_key, state)
            subscriptions = _all_subscriptions(conn)

        push = {"sent": 0, "failed": 0}
        if subscriptions:
            clear_payload = {
                "kind": "attendance-break-cleared",
                "tag": notification_tag,
                "url": alerts.APP_URL,
                "event_key": event_key,
                "globally_deleted": True,
            }
            deliveries = [{**row, "payload": clear_payload} for row in subscriptions]
            push = alerts._send_payloads(api_module, engine_instance, deliveries)

        return {
            "ok": True,
            "release": RELEASE,
            "key": event_key,
            "tag": notification_tag,
            "globally_deleted": True,
            "deleted_by": actor,
            "deleted_at": deleted_at,
            "push_clear": push,
            "message": "Đã xóa cảnh báo này cho tất cả tài khoản và chặn không cho xuất hiện lại.",
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
            "scope": "web_v2_tour_cache_refresh",
            "auto_check_unchanged": True,
            "break_alerts_unchanged": True,
            "break_alert_roles": ["quanly", "letan", "nhanvien"],
        }

    @app.put("/v2/attendance/tour-cache/control")
    def update_tour_cache_control(
        payload: dict[str, Any],
        ident: identity_type = Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role != "admin":
            raise HTTPException(403, "Chỉ Admin được tạm dừng hoặc mở lại làm mới TourVera cho Web V2.")
        disabled = bool(payload.get("disabled"))
        actor = str(getattr(ident, "employee_username", "") or "admin").strip()
        with engine_instance().begin() as conn:
            tour_cache_control.set_disabled(conn, disabled, actor)
            state = tour_cache_control.status(conn)
        return {
            "ok": True,
            "release": RELEASE,
            **state,
            "scope": "web_v2_tour_cache_refresh",
            "auto_check_unchanged": True,
            "break_alerts_unchanged": True,
            "break_alert_roles": ["quanly", "letan", "nhanvien"],
            "message": (
                "Đã tạm dừng làm mới TourVera định kỳ. Cảnh báo nghỉ giữa ca vẫn hoạt động cho Quản lý, Lễ tân và Nhân viên."
                if disabled else
                "Đã mở lại làm mới TourVera định kỳ. Cảnh báo nghỉ giữa ca vẫn hoạt động bình thường."
            ),
        }

    @app.get("/v2/attendance/break-alerts/control/health")
    def break_alert_control_health():
        return {
            "ok": True,
            "release": RELEASE,
            "admin_global_control": True,
            "admin_global_item_delete": True,
            "global_item_delete_persists_tombstone": True,
            "suppresses_browser_alerts": True,
            "suppresses_web_push": True,
            "admin_tour_cache_control": True,
            "tour_pause_only_stops_refresh": True,
            "tour_pause_keeps_break_alerts": True,
        }

    app.state.break_alert_control_installed = True
    app.state.break_alert_control_release = RELEASE
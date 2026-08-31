"""Server-side Web Push dispatcher for mid-shift break deadlines.

Unlike the in-app polling, this endpoint is designed for pg_cron. It lets an
installed iPhone PWA receive lock-screen push even while VERA SPA is closed.
Existing alert state rows provide idempotency when browser polling and server
cron happen at the same time. Production cadence is every 5 minutes.
"""
from __future__ import annotations

from datetime import datetime
import hmac
from typing import Any, Callable

from fastapi import Header, HTTPException

import vera_web_v2_attendance_break_alerts as alerts
import vera_web_v2_snapshot as snapshot


RELEASE = "attendance-break-server-push-2026-08-31-v2"
_ORIGINAL_PAYLOAD = alerts._payload


def _payload_without_source(fact: dict[str, Any], kind: str) -> dict[str, Any]:
    """Preserve the canonical payload but omit technical source text."""
    payload = _ORIGINAL_PAYLOAD(fact, kind)
    if kind == "overdue":
        employee = fact["employee"]
        start = fact["break_out"].strftime("%H:%M:%S")
        deadline = fact["deadline"].strftime("%H:%M:%S")
        late_minutes = max(1, (max(0, fact["late_seconds"]) + 59) // 60)
        payload["body"] = (
            f"{employee}: nghỉ từ {start}, phải vào lại {deadline}, "
            f"hiện đã trễ {late_minutes} phút."
        )
    return payload


def install_attendance_break_dispatch(
    app,
    *,
    engine_instance: Callable[[], Any],
    api_module,
    vn_tz,
) -> None:
    if getattr(app.state, "attendance_break_dispatch_installed", False):
        return

    # Also clean the payload emitted by the authenticated browser polling route.
    alerts._payload = _payload_without_source

    def dispatch_once() -> dict[str, Any]:
        now_aware = datetime.now(vn_tz)
        now = now_aware.replace(tzinfo=None)
        today = now.date()
        deliveries: list[dict[str, Any]] = []
        fact_count = 0
        reminder_events = 0
        overdue_events = 0
        cleared_events = 0

        with engine_instance().begin() as conn:
            records = snapshot._records(conn, today, today)
            facts = [fact for item in records if (fact := alerts._fact(item, now)) is not None]
            fact_count = len(facts)
            management_cache: list[dict[str, Any]] | None = None

            for fact in facts:
                state = alerts._ensure_state(conn, fact["key"])
                remaining = fact["remaining_seconds"]

                if (
                    fact["break_in"] is None
                    and 0 < remaining <= alerts.REMINDER_SECONDS
                    and not state.get("reminder_sent_at")
                ):
                    subscriptions = alerts._employee_subscriptions(conn, fact["employee"])
                    if subscriptions:
                        payload = alerts._payload(fact, "reminder")
                        deliveries.extend({**row, "payload": payload} for row in subscriptions)
                        state["reminder_sent_at"] = now_aware.isoformat()
                        reminder_events += 1

                if fact["break_in"] is None and remaining <= 0 and not state.get("overdue_sent_at"):
                    if management_cache is None:
                        management_cache = alerts._management_subscriptions(conn)
                    if management_cache:
                        payload = alerts._payload(fact, "overdue")
                        deliveries.extend({**row, "payload": payload} for row in management_cache)
                        state["overdue_sent_at"] = now_aware.isoformat()
                        overdue_events += 1

                if fact["break_in"] is not None and state.get("overdue_sent_at") and not state.get("cleared_at"):
                    if management_cache is None:
                        management_cache = alerts._management_subscriptions(conn)
                    if management_cache:
                        payload = alerts._payload(fact, "clear")
                        deliveries.extend({**row, "payload": payload} for row in management_cache)
                    state["cleared_at"] = now_aware.isoformat()
                    cleared_events += 1

                state.update({
                    "employee": fact["employee"],
                    "work_date": fact["date"].isoformat(),
                    "break_out": fact["break_out"].isoformat(),
                    "deadline": fact["deadline"].isoformat(),
                    "break_in": fact["break_in"].isoformat() if fact["break_in"] else "",
                    "source": fact["source"],
                    "last_checked_at": now_aware.isoformat(),
                    "dispatch_mode": "server_cron_5m",
                })
                alerts._save_state(conn, fact["key"], state)

        push_result = alerts._send_payloads(api_module, engine_instance, deliveries)
        return {
            "ok": True,
            "release": RELEASE,
            "checked_at": now_aware.isoformat(),
            "fact_count": fact_count,
            "reminder_events": reminder_events,
            "overdue_events": overdue_events,
            "cleared_events": cleared_events,
            "deliveries": len(deliveries),
            "push": push_result,
        }

    @app.post("/v2/attendance/break-alerts/dispatch")
    def dispatch_break_push(
        x_vera_push_webhook: str | None = Header(default=None),
    ):
        with engine_instance().connect() as conn:
            expected = api_module._vault_secret(conn, "vera_v2_push_webhook_secret")
        supplied = str(x_vera_push_webhook or "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            raise HTTPException(403, "Webhook Web Push không hợp lệ.")
        return dispatch_once()

    @app.get("/v2/attendance/break-alerts/dispatch/health")
    def dispatch_break_push_health():
        return {
            "ok": True,
            "release": RELEASE,
            "schedule_recommended": "every 5 minutes",
            "works_when_pwa_closed": True,
            "reminder_before_minutes": 15,
        }

    app.state.attendance_break_dispatch_installed = True
    app.state.attendance_break_dispatch_release = RELEASE

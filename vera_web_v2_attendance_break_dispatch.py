"""Server-side Web Push dispatcher for mid-shift break deadlines and queue watchdog.

Unlike the in-app polling, these endpoints are designed for pg_cron. They let
production monitoring continue independently of browsers and GitHub Actions.
"""
from __future__ import annotations

from datetime import datetime
import hmac
from typing import Any, Callable

from fastapi import Header, HTTPException

import vera_web_v2_attendance_break_alerts as alerts
import vera_web_v2_snapshot as snapshot
import vera_postgres_job_queue as job_queue
import vera_live_tour_queue_alerts as queue_alerts


RELEASE = "attendance-break-server-push-2026-09-16-v3-queue-watchdog"
QUEUE_NAME = "live_tour_projection"
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

    alerts._payload = _payload_without_source

    def require_cron_secret(supplied: str | None) -> None:
        with engine_instance().connect() as conn:
            expected = api_module._vault_secret(conn, "vera_v2_push_webhook_secret")
        value = str(supplied or "")
        if not expected or not value or not hmac.compare_digest(expected, value):
            raise HTTPException(403, "Webhook Web Push không hợp lệ.")

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

                if fact["break_in"] is None and 0 < remaining <= alerts.REMINDER_SECONDS and not state.get("reminder_sent_at"):
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
                    "employee": fact["employee"], "work_date": fact["date"].isoformat(),
                    "break_out": fact["break_out"].isoformat(), "deadline": fact["deadline"].isoformat(),
                    "break_in": fact["break_in"].isoformat() if fact["break_in"] else "",
                    "source": fact["source"], "last_checked_at": now_aware.isoformat(),
                    "dispatch_mode": "server_cron_5m",
                })
                alerts._save_state(conn, fact["key"], state)

        push_result = alerts._send_payloads(api_module, engine_instance, deliveries)
        return {
            "ok": True, "release": RELEASE, "checked_at": now_aware.isoformat(),
            "fact_count": fact_count, "reminder_events": reminder_events,
            "overdue_events": overdue_events, "cleared_events": cleared_events,
            "deliveries": len(deliveries), "push": push_result,
        }

    @app.post("/v2/attendance/break-alerts/dispatch")
    def dispatch_break_push(x_vera_push_webhook: str | None = Header(default=None)):
        require_cron_secret(x_vera_push_webhook)
        return dispatch_once()

    @app.post("/v2/live-tour/projection-queue/watchdog")
    def dispatch_live_tour_queue_watchdog(x_vera_push_webhook: str | None = Header(default=None)):
        """pg_cron entry point: evaluate queue health and deliver alert/recovery Web Push."""
        require_cron_secret(x_vera_push_webhook)
        metrics = job_queue.health_metrics(engine_instance, QUEUE_NAME)
        result = queue_alerts.monitor_once(engine_instance, QUEUE_NAME, metrics)
        status = queue_alerts.health_status(engine_instance, QUEUE_NAME, metrics)
        return {
            "ok": not status["active"], "release": RELEASE,
            "checked_at": datetime.now(vn_tz).isoformat(),
            "watchdog": result, "alerting": status,
        }

    @app.get("/v2/attendance/break-alerts/dispatch/health")
    def dispatch_break_push_health():
        return {
            "ok": True, "release": RELEASE, "schedule_recommended": "every 5 minutes",
            "works_when_pwa_closed": True, "reminder_before_minutes": 15,
            "queue_watchdog_endpoint": "/v2/live-tour/projection-queue/watchdog",
        }

    app.state.attendance_break_dispatch_installed = True
    app.state.attendance_break_dispatch_release = RELEASE

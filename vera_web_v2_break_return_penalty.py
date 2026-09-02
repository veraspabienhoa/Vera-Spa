"""Auto-penalty after a confirmed late return from the mid-shift break.

A penalty is created only after the return FaceID is known. This prevents an
open/incomplete break from being penalized before the employee actually comes
back. The official Nội quy catalog determines the matching "Ra ngoài vào muộn"
reason and amount. The same confirmed-return fact is used by the frequent
TimeSoft background sync, so the penalty no longer depends on opening the
attendance screen or waiting for Auto Check. The affected employee receives
Web Push after the violation has been recorded.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import math
from typing import Any, Callable

import vera_auto_check as auto_check
import vera_auto_penalty_notifications as penalty_notifications
import vera_web_v2_attendance_break_alerts as alerts
import vera_web_v2_snapshot as snapshot
from vera_attendance_rules import break_return_deadline


RELEASE = "attendance-break-return-penalty-2026-09-02-v4-cutoff-2000"


def _work_day(item: dict[str, Any]) -> date | None:
    raw = str(item.get("date") or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def confirmed_break_return_fact(item: dict[str, Any], today: date) -> dict[str, Any] | None:
    """Return a confirmed, eligible late-return fact for UI and background jobs."""
    work_day = _work_day(item)
    if (
        work_day != today
        or not bool(item.get("break_enabled"))
        or item.get("break_restricted_reason")
        or item.get("break_final_early_checkout")
    ):
        return None

    break_out = alerts._parse_clock(item.get("break_out"), work_day)
    break_in = alerts._parse_clock(item.get("break_in"), work_day)
    if break_out is None or break_in is None:
        return None
    if break_in < break_out:
        break_in += timedelta(days=1)

    planned = max(1, int(item.get("break_planned_minutes") or alerts.DEFAULT_BREAK_MINUTES))
    calculated_deadline = break_return_deadline(work_day, break_out, planned)
    stored_deadline = alerts._parse_clock(item.get("break_return_deadline"), work_day)
    deadline = min(stored_deadline, calculated_deadline) if stored_deadline else calculated_deadline
    late_seconds = int((break_in - deadline).total_seconds())
    if late_seconds <= 0:
        return None
    return {
        "work_day": work_day,
        "employee": str(item.get("employee_name") or "").strip(),
        "break_out": break_out,
        "break_in": break_in,
        "deadline": deadline,
        "planned_minutes": planned,
        "late_minutes": max(1, int(math.ceil(late_seconds / 60))),
    }


def install_break_return_penalty(
    app,
    *,
    engine_instance: Callable[[], Any],
    api_module,
    vn_tz,
) -> None:
    if getattr(app.state, "break_return_penalty_installed", False):
        return

    original_records = snapshot._records

    def records_with_confirmed_return_penalty(conn, start: date, end: date):
        records = original_records(conn, start, end)
        now_aware = datetime.now(vn_tz)
        today = now_aware.date()
        if not (start <= today <= end):
            return records

        catalog: dict[str, dict] | None = None
        output: list[dict[str, Any]] = []

        for raw in records:
            item = dict(raw)
            fact = confirmed_break_return_fact(item, today)
            if fact is None:
                output.append(item)
                continue

            work_day = fact["work_day"]
            break_out = fact["break_out"]
            break_in = fact["break_in"]
            deadline = fact["deadline"]
            late_minutes = fact["late_minutes"]
            if catalog is None:
                with engine_instance().connect() as catalog_conn:
                    catalog = auto_check.load_catalog(catalog_conn)
            reason_item = auto_check.outside_reason(catalog or {}, late_minutes)
            if not reason_item:
                item["break_return_penalty_error"] = "Nội quy chưa có lý do Ra ngoài vào muộn phù hợp."
                output.append(item)
                continue

            employee = fact["employee"]
            detail = (
                f"Tự động phạt nghỉ giữa ca vào lại trễ {late_minutes} phút"
                f" · Giờ ra {break_out.strftime('%H:%M:%S')}"
                f" · Hạn vào lại {deadline.strftime('%H:%M:%S')}"
                f" · FaceID vào lại {break_in.strftime('%H:%M:%S')}"
            )
            try:
                with engine_instance().begin() as write_conn:
                    ok, message = auto_check.save_violation(
                        write_conn,
                        work_date=work_day,
                        employee=employee,
                        reason_item=reason_item,
                        detail=detail,
                        source="AUTO UPDATE 24/7 - NGHỈ GIỮA CA",
                        minutes=late_minutes,
                    )
                item["break_return_penalty_reason"] = str(reason_item.get("name") or "")
                item["break_return_penalty_minutes"] = late_minutes
                item["break_return_penalty_amount"] = float(reason_item.get("penalty") or 0)
                item["break_return_penalty_status"] = message if ok else f"ERROR: {message}"

            except Exception as exc:
                item["break_return_penalty_error"] = str(exc)[:240]

            output.append(item)

        penalty_notifications.notify_pending(engine_instance())

        return output

    snapshot._records = records_with_confirmed_return_penalty

    @app.get("/v2/attendance/break-return-penalty/health")
    def break_return_penalty_health():
        return {
            "ok": True,
            "release": RELEASE,
            "penalty_only_after_return_faceid": True,
            "policy_source": "official Nội quy",
            "employee_push_after_penalty": True,
        }

    app.state.break_return_penalty_installed = True
    app.state.break_return_penalty_release = RELEASE

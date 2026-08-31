"""Same-day outside-break restriction for late/early leave records.

Business rule:
- If an employee has any same-day Đi trễ or Về sớm record (CÓ phép or
  KHÔNG phép), that employee cannot use the normal outside/mid-shift break.
- TimeSoft remains the first source of the actual outside time; the attendance
  break stack may then fall back to TourVera R=Break, S=Giờ ra, U=Giờ vào.
- If the employee went outside before/equal 17:00 and the late/early record is
  entered afterwards, Auto Check still catches it on the next attendance poll.
  Violation minutes are calculated from the actual Giờ ra through 17:00.
- If Giờ ra is after 17:00, use "Ra ngoài chỉ có dữ liệu một lần".

The module wraps snapshot._records after TimeSoft/TourVera break reconstruction,
so it works for both the CHẤM CÔNG screen and the break-alert poller without
changing either data source.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import math
import unicodedata
from typing import Any, Callable

from sqlalchemy import text

import vera_auto_check as auto_check
import vera_web_v2_attendance_break_alerts as break_alerts
import vera_web_v2_snapshot as snapshot


RELEASE = "outside-leave-restriction-2026-08-31-v1"
VN_TZ = timezone(timedelta(hours=7))
CUTOFF = time(17, 0, 0)


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").strip().lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return " ".join(raw.replace("đ", "d").split())


def _restricted_leave_reason(value: Any) -> bool:
    key = _norm(value)
    return "di tre" in key or "ve som" in key or "ra som" in key


def _restriction_map(conn, start: date, end: date) -> dict[tuple[date, str], list[str]]:
    rows = conn.execute(text("""
        SELECT leave_date, employee_name, leave_reason
        FROM leave_records
        WHERE leave_date BETWEEN :start_date AND :end_date
        ORDER BY leave_date, employee_name, created_at
    """), {"start_date": start, "end_date": end}).mappings().all()
    output: dict[tuple[date, str], list[str]] = {}
    for row in rows:
        reason = str(row.get("leave_reason") or "").strip()
        if not _restricted_leave_reason(reason):
            continue
        key = (row["leave_date"], _norm(row.get("employee_name")))
        bucket = output.setdefault(key, [])
        if reason and reason not in bucket:
            bucket.append(reason)
    return output


def _parse_clock(value: Any, work_day: date) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in (
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%H:%M:%S", "%H:%M",
    ):
        try:
            parsed = datetime.strptime(raw, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=work_day.year, month=work_day.month, day=work_day.day)
            return parsed
        except ValueError:
            continue
    return None


def _work_day(item: dict[str, Any]) -> date | None:
    raw = str(item.get("date") or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _single_side_item(catalog: dict[str, dict]) -> dict | None:
    for name in (
        "Ra ngoài chỉ có dữ liệu một lần",
        "Ra ngoài thiếu giờ ra/vào",
    ):
        item = auto_check.catalog_item(catalog, name)
        if item:
            return item
    return None


def _violation_for(
    *,
    catalog: dict[str, dict],
    work_day: date,
    break_out: datetime,
) -> tuple[dict | None, int, str]:
    cutoff = datetime.combine(work_day, CUTOFF)
    if break_out > cutoff:
        return _single_side_item(catalog), 0, "Giờ ra sau 17:00"

    minutes = max(0, int(math.ceil((cutoff - break_out).total_seconds() / 60)))
    return auto_check.outside_reason(catalog, minutes), minutes, "Tính từ Giờ ra đến 17:00"


def _apply_restrictions_and_penalties(
    engine_instance: Callable[[], Any],
    conn,
    records: list[dict[str, Any]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    restrictions = _restriction_map(conn, start, end)
    if not restrictions:
        return records

    today = datetime.now(VN_TZ).date()
    catalog: dict[str, dict] | None = None
    output: list[dict[str, Any]] = []

    for raw in records:
        item = dict(raw)
        work_day = _work_day(item)
        if work_day is None:
            output.append(item)
            continue

        reasons = restrictions.get((work_day, _norm(item.get("employee_name"))))
        if not reasons:
            output.append(item)
            continue

        restriction_text = " / ".join(reasons)
        item["break_restricted_reason"] = restriction_text
        item["break_alert_suppressed"] = True
        item["break_status"] = f"KHÔNG ĐƯỢC SỬ DỤNG GIỜ RA NGOÀI · {restriction_text}"
        item["break_return_deadline"] = ""
        item["break_return_deadline_iso"] = ""
        item["break_remaining_seconds"] = 0

        break_out = _parse_clock(item.get("break_out"), work_day)
        if break_out is None or work_day != today:
            output.append(item)
            continue

        if catalog is None:
            with engine_instance().connect() as catalog_conn:
                catalog = auto_check.load_catalog(catalog_conn)

        reason_item, minutes, calculation = _violation_for(
            catalog=catalog or {},
            work_day=work_day,
            break_out=break_out,
        )
        if not reason_item:
            item["break_auto_penalty_error"] = "Nội quy chưa có lý do phạt Ra ngoài phù hợp."
            output.append(item)
            continue

        detail = (
            f"Tự động phạt do trong ngày đã có {restriction_text} nên không được sử dụng giờ ra ngoài"
            f" · Giờ ra {break_out.strftime('%H:%M:%S')} · {calculation}"
        )
        source = str(item.get("break_source") or item.get("break_method") or "TimeSoft/TourVera")
        detail += f" · Dữ liệu ra ngoài: {source}"

        try:
            with engine_instance().begin() as write_conn:
                ok, message = auto_check.save_violation(
                    write_conn,
                    work_date=work_day,
                    employee=str(item.get("employee_name") or "").strip(),
                    reason_item=reason_item,
                    detail=detail,
                    source="AUTO UPDATE 24/7 - QUY TẮC RA NGOÀI",
                    minutes=minutes,
                )
            item["break_auto_penalty_reason"] = str(reason_item.get("name") or "")
            item["break_auto_penalty_minutes"] = minutes
            item["break_auto_penalty_status"] = message if ok else f"ERROR: {message}"
        except Exception as exc:
            # Never make the attendance page unavailable because a background
            # penalty write failed; surface the error for operational diagnosis.
            item["break_auto_penalty_error"] = str(exc)[:240]

        output.append(item)

    return output


def install_outside_leave_rule(
    app,
    *,
    engine_instance: Callable[[], Any],
) -> None:
    if getattr(app.state, "outside_leave_rule_installed", False):
        return

    original_records = snapshot._records
    original_fact = break_alerts._fact

    def records_with_leave_restriction(conn, start: date, end: date):
        records = original_records(conn, start, end)
        return _apply_restrictions_and_penalties(
            engine_instance,
            conn,
            records,
            start,
            end,
        )

    def fact_without_normal_break_alert(item: dict[str, Any], now: datetime):
        # A late/early-leave day has no 90-minute outside allowance, so do not
        # send the ordinary "15 minutes remaining" break reminder for it.
        if item.get("break_restricted_reason"):
            return None
        return original_fact(item, now)

    snapshot._records = records_with_leave_restriction
    break_alerts._fact = fact_without_normal_break_alert

    @app.get("/v2/attendance/outside-leave-rule/health")
    def outside_leave_rule_health():
        return {
            "ok": True,
            "release": RELEASE,
            "restricted_when_same_day_reason_contains": ["Đi trễ", "Về sớm"],
            "permission_independent": True,
            "before_or_at_1700": "penalty minutes = 17:00 - Giờ ra",
            "after_1700": "Ra ngoài chỉ có dữ liệu một lần",
            "source_priority": ["TimeSoft", "TourVera R=Break S=Giờ ra U=Giờ vào"],
        }

    app.state.outside_leave_rule_installed = True
    app.state.outside_leave_rule_release = RELEASE

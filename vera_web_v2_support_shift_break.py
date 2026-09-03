"""Apply Hỗ trợ-ca shift allowances before mid-shift break restriction.

Recognized support leave rows adjust the effective shift start for every employee:
- Ca 1 sau 23H đi trễ 2 tiếng: +120 minutes
- Ca 1 sau 0:0H đi trễ 3 tiếng: +180 minutes
- Ca 2 sau 0:0H đi trễ 1 tiếng: +60 minutes

A recognized support row never removes the employee's configured mid-shift break.
Only lateness remaining after the allowance may restrict the break.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import re
import unicodedata
from typing import Any, Callable

from sqlalchemy import text


RELEASE = "support-shift-break-2026-09-03.3"


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").strip().lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    raw = raw.replace("đ", "d")
    return " ".join(raw.split())


SUPPORT_ALLOWANCES = {
    _norm("Hỗ trợ Ca 1 sau 23H đi trễ 2 tiếng"): 120,
    _norm("Hỗ trợ Ca 1 đi trễ 2 tiếng"): 120,
    _norm("Hỗ trợ Ca 1 sau 0:0H đi trễ 3 tiếng"): 180,
    _norm("Hỗ trợ Ca 2 sau 0:0H đi trễ 1 tiếng"): 60,
}


def is_break_preserving_support(value: Any) -> bool:
    """Only recognized Hỗ trợ-ca reasons preserve the normal mid-shift break."""
    return _norm(value) in SUPPORT_ALLOWANCES


def _support_map(conn, start, end) -> dict[tuple[str, str], tuple[int, str]]:
    rows = conn.execute(text("""
        SELECT leave_date, employee_name, leave_reason
        FROM leave_records
        WHERE leave_date BETWEEN :start AND :end
    """), {"start": start, "end": end}).mappings().all()
    output: dict[tuple[str, str], tuple[int, str]] = {}
    for row in rows:
        reason = str(row.get("leave_reason") or "").strip()
        allowance = SUPPORT_ALLOWANCES.get(_norm(reason))
        if allowance is None:
            continue
        key = (row["leave_date"].strftime("%d/%m/%Y"), _norm(row.get("employee_name")))
        current = output.get(key)
        if current is None or allowance > current[0]:
            output[key] = (allowance, reason)
    return output


def _clock_minutes(value: Any) -> float | None:
    raw = str(value or "").strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.hour * 60 + parsed.minute + parsed.second / 60.0
        except ValueError:
            continue
    return None


def _apply_arrival_allowance(item: dict[str, Any], allowance: int) -> None:
    """Recalculate lateness against the approved, effective shift start."""
    start_minutes = _clock_minutes(
        item.get("shift_start") or item.get("start_work_time") or item.get("StartWorkTime")
    )
    if start_minutes is None:
        return
    effective = (start_minutes + allowance) % (24 * 60)
    hour = int(effective // 60)
    minute = int(effective % 60)
    item["effective_shift_start"] = f"{hour:02d}:{minute:02d}:00"

    raw_check_in = str(item.get("check_in") or "").strip()
    if " " in raw_check_in:
        raw_check_in = raw_check_in.rsplit(" ", 1)[-1]
    check_in_minutes = _clock_minutes(raw_check_in)
    if check_in_minutes is None:
        return
    # Attendance rows belong to one work day. A smaller clock value after an
    # evening shift start is a punch after midnight on the following day.
    if check_in_minutes < start_minutes and start_minutes >= 12 * 60:
        check_in_minutes += 24 * 60
    effective_minutes = start_minutes + allowance
    late_minutes = max(0, int((check_in_minutes - effective_minutes) // 1))
    item["late_minutes"] = late_minutes
    item["arrival_status"] = "Đi trễ" if late_minutes > 0 else "Đúng giờ"


def _remove_late_restriction(item: dict[str, Any]) -> None:
    reason = str(item.get("break_restricted_reason") or "").strip()
    if not reason:
        return
    parts = [part.strip() for part in re.split(r"\s+(?:và|/)\s+", reason, flags=re.IGNORECASE) if part.strip()]
    parts = [
        part for part in parts
        if _norm(part) != "di tre" and not is_break_preserving_support(part)
    ]
    item["break_restricted_reason"] = " và ".join(parts)
    if parts:
        return

    item["break_alert_suppressed"] = False

    enabled = bool(item.get("break_enabled"))
    planned = int(item.get("break_planned_minutes") or 0)
    actual = int(item.get("break_actual_minutes") or 0)
    break_out = str(item.get("break_out") or "").strip()
    break_in = str(item.get("break_in") or "").strip()
    deadline = str(item.get("break_return_deadline") or "").strip()
    late = int(item.get("break_return_late_minutes") or 0)
    if break_out and break_in:
        if late > 0:
            item["break_status"] = f"Vào lại trễ {late} phút" + (f" · hạn {deadline}" if deadline else "")
        elif planned > 0 and actual > planned:
            item["break_status"] = f"Quá {actual - planned} phút" + (f" · hạn {deadline}" if deadline else "")
        elif enabled:
            item["break_status"] = "Trong giới hạn" + (f" · hạn vào lại {deadline}" if deadline else "")
    elif break_out and enabled:
        item["break_status"] = "Đã bắt đầu nghỉ giữa ca" + (f" · phải vào lại lúc {deadline}" if deadline else "")
    elif enabled:
        item["break_status"] = "Chưa ghi nhận FaceID nghỉ"


def install_support_shift_break(app, *, engine_instance: Callable[[], Any], snapshot_module) -> None:
    if getattr(app.state, "support_shift_break_installed", False):
        return

    original_records = snapshot_module._records

    def records_with_support(conn, start, end):
        rows = original_records(conn, start, end)
        supports = _support_map(conn, start, end)
        for raw in rows:
            item = raw
            key = (str(item.get("date") or ""), _norm(item.get("employee_name")))
            support = supports.get(key)
            if not support:
                continue
            allowance, reason = support
            item["support_shift_reason"] = reason
            item["support_shift_allowance_minutes"] = allowance
            item["support_break_allowed"] = True

            _apply_arrival_allowance(item, allowance)
            _remove_late_restriction(item)
            item["arrival_support_applied"] = True
        return rows

    snapshot_module._records = records_with_support

    @app.get("/v2/support-shift-break/health")
    def support_shift_break_health():
        return {
            "ok": True,
            "release": RELEASE,
            "all_employees": True,
            "allowances": {
                "Hỗ trợ Ca 1 sau 23H đi trễ 2 tiếng": 120,
                "Hỗ trợ Ca 1 sau 0:0H đi trễ 3 tiếng": 180,
                "Hỗ trợ Ca 2 sau 0:0H đi trễ 1 tiếng": 60,
            },
            "support_keeps_break": True,
            "support_never_creates_outside_penalty": True,
        }

    app.state.support_shift_break_installed = True
    app.state.support_shift_break_release = RELEASE

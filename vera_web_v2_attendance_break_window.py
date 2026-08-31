"""Attendance break-window rules for Web V2.

A FaceID cluster from 15:00 onward is already the start of the employee's
mid-shift break even when the matching return FaceID has not happened yet.
The operational return deadline is 20:00 every workday.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable

import vera_web_v2_attendance_v42 as attendance


RELEASE = "break-start-1500-return-2000-2026-08-31-v1"
BREAK_START = time(15, 0, 0)
BREAK_RETURN_DEADLINE = time(20, 0, 0)


def _is_break_start(value: datetime, work_day: date) -> bool:
    return value.date() == work_day and BREAK_START <= value.time() < BREAK_RETURN_DEADLINE


def _pick_break_pair(values: list[datetime], planned: int, cluster_minutes: int):
    """Choose a break pair whose break-out starts from 15:00 and before 20:00.

    A return after 20:00 is still paired so the UI can show how late the employee
    returned instead of losing the attendance event.
    """
    if len(values) < 2:
        return None
    minimum = max(int(cluster_minutes or 10) + 1, min(30, max(15, round(max(1, planned) * .25))))
    candidates = []
    for index, (start, end) in enumerate(zip(values, values[1:])):
        if not _is_break_start(start, start.date()):
            continue
        gap = round((end - start).total_seconds() / 60)
        if gap < 0:
            continue
        penalty = 10000 if gap < minimum else 0
        candidates.append((abs(gap - max(1, planned)) + penalty, abs(gap - max(1, planned)), index, start, end))
    if not candidates:
        return None
    _, _, index, start, end = min(candidates)
    return start, end, f"Cụm FaceID {index + 2} → {index + 3} từ 15:00"


def _parse_clock_on_day(value: Any, work_day: date) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.replace(year=work_day.year, month=work_day.month, day=work_day.day)
        except ValueError:
            continue
    return None


def _enhance_break_payload(
    original: Callable[..., dict[str, Any]],
    punches: list[datetime],
    *,
    work_day: date,
    representative: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    result = dict(original(
        punches,
        work_day=work_day,
        representative=representative,
        cfg=cfg,
    ))

    cluster_minutes = int(cfg.get("faceid_cluster_minutes") or 10)
    clustered = attendance._cluster_punches(punches, cluster_minutes)
    middle = list(clustered[1:])
    if middle and attendance._looks_like_final_checkout(middle[-1], work_day, representative, len(clustered)):
        middle.pop()

    break_out = _parse_clock_on_day(result.get("break_out"), work_day)
    break_in = _parse_clock_on_day(result.get("break_in"), work_day)

    # The important in-progress case: 12:58:59 / 12:59:02 are clustered as the
    # shift check-in, while 15:53:31 / 15:53:33 are clustered as the break start.
    # Do not wait for a third cluster before exposing that break start in Web V2.
    if break_out is None:
        starts = [value for value in middle if _is_break_start(value, work_day)]
        if starts:
            break_out = starts[0]
            result.update({
                "break_out": break_out.strftime("%H:%M:%S"),
                "break_in": "",
                "break_actual_minutes": 0,
                "break_over_minutes": 0,
                "break_count": 0,
                "break_source": "TimeSoft FaceID",
                "break_method": "Bắt đầu nghỉ giữa ca · chờ FaceID vào lại",
                "break_detail": f"Bắt đầu nghỉ giữa ca {break_out.strftime('%d/%m/%Y %H:%M:%S')}",
            })

    deadline = datetime.combine(work_day, BREAK_RETURN_DEADLINE)
    return_late_minutes = 0
    if break_in is not None and break_in > deadline:
        return_late_minutes = max(1, int((break_in - deadline).total_seconds() // 60))

    result["break_window_start"] = BREAK_START.strftime("%H:%M:%S")
    result["break_return_deadline"] = BREAK_RETURN_DEADLINE.strftime("%H:%M:%S")
    result["break_return_late_minutes"] = return_late_minutes
    result["break_started"] = bool(break_out)

    restricted_reason = str(cfg.get("break_restricted_reason") or "").strip()
    enabled = bool(cfg.get("break_enabled"))
    planned = int(cfg.get("break_planned_minutes") or 0)
    actual = int(result.get("break_actual_minutes") or 0)

    if break_out and break_in:
        result["break_detail"] = (
            f"Nghỉ giữa ca {break_out.strftime('%d/%m/%Y %H:%M:%S')} → "
            f"{break_in.strftime('%d/%m/%Y %H:%M:%S')}"
        )
        if restricted_reason:
            result["break_status"] = f"Vi phạm: {restricted_reason} không được nghỉ giữa ca ({actual} phút)"
        elif return_late_minutes > 0:
            over = max(0, actual - planned)
            suffix = f" · nghỉ quá {over} phút" if planned > 0 and over > 0 else ""
            result["break_status"] = f"Vào lại sau 20:00 {return_late_minutes} phút{suffix}"
        elif planned > 0 and actual > planned:
            result["break_status"] = f"Quá {actual - planned} phút"
        elif enabled:
            result["break_status"] = "Trong giới hạn · vào lại trước 20:00"
    elif break_out:
        if restricted_reason:
            result["break_status"] = f"Vi phạm: {restricted_reason} · đã bắt đầu nghỉ giữa ca"
        elif enabled:
            result["break_status"] = "Đã bắt đầu nghỉ giữa ca · phải quay lại trước 20:00"

    return result


def install_attendance_break_window(app) -> None:
    if getattr(app.state, "attendance_break_window_installed", False):
        return

    # _records_v42 resolves these globals on every request, so patching them after
    # Attendance 4.2 is installed upgrades both screen and Excel data builders.
    original_break = attendance._break_from_punches
    attendance._pick_break_pair = _pick_break_pair

    def wrapped_break_from_punches(punches, *, work_day, representative, cfg):
        return _enhance_break_payload(
            original_break,
            punches,
            work_day=work_day,
            representative=representative,
            cfg=cfg,
        )

    attendance._break_from_punches = wrapped_break_from_punches

    @app.get("/v2/attendance-break-window/health")
    def attendance_break_window_health():
        return {
            "ok": True,
            "release": RELEASE,
            "break_start_from": "15:00:00",
            "return_deadline": "20:00:00",
            "show_in_progress_break": True,
        }

    app.state.attendance_break_window_installed = True
    app.state.attendance_break_window_release = RELEASE

"""Attendance break-window rules for Web V2.

A FaceID event from 15:00 onward is the start of the employee's mid-shift
break even when the matching return FaceID has not happened yet. Repeated
FaceID scans inside the same 5-minute window are one attendance event and the
first scan in that group is authoritative. The return deadline is the exact
break-start time plus the configured break length (normally 90 minutes), but
all employees must return no later than 20:00.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable

import vera_web_v2_attendance_v42 as attendance
from vera_attendance_rules import BREAK_RETURN_LATEST, break_return_deadline


RELEASE = "break-return-latest-2000-2026-09-02-v4"
BREAK_START = time(15, 0, 0)
BREAK_START_LATEST = time(23, 0, 0)
DEFAULT_BREAK_MINUTES = 90
FACEID_GROUP_MINUTES = 5


def _is_break_start(value: datetime, work_day: date) -> bool:
    return value.date() == work_day and BREAK_START <= value.time() < BREAK_START_LATEST


def _pick_break_pair(values: list[datetime], planned: int, cluster_minutes: int):
    """Choose a break pair whose break-out begins from 15:00 onward.

    The first FaceID group is still the shift check-in and is removed by the
    caller. A return later than the planned duration remains paired so the UI
    can report the exact late time instead of losing the event.
    """
    if len(values) < 2:
        return None
    target = max(1, int(planned or DEFAULT_BREAK_MINUTES))
    minimum = max(FACEID_GROUP_MINUTES + 1, min(30, max(15, round(target * .25))))
    candidates = []
    for index, (start, end) in enumerate(zip(values, values[1:])):
        if not _is_break_start(start, start.date()):
            continue
        gap = round((end - start).total_seconds() / 60)
        if gap < 0:
            continue
        penalty = 10000 if gap < minimum else 0
        candidates.append((abs(gap - target) + penalty, abs(gap - target), index, start, end))
    if not candidates:
        return None
    _, _, index, start, end = min(candidates)
    return start, end, f"Nhóm FaceID {index + 2} → {index + 3} từ 15:00"


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
    # Canonical rule: every group spans at most 5 minutes from its first scan.
    # Example 15:30:00 / 15:32:10 / 15:35:00 => one group at 15:30:00.
    grouped_cfg = dict(cfg)
    grouped_cfg["faceid_cluster_minutes"] = FACEID_GROUP_MINUTES
    result = dict(original(
        punches,
        work_day=work_day,
        representative=representative,
        cfg=grouped_cfg,
    ))

    clustered = attendance._cluster_punches(punches, FACEID_GROUP_MINUTES)
    middle = list(clustered[1:])
    if middle and attendance._looks_like_final_checkout(middle[-1], work_day, representative, len(clustered)):
        middle.pop()

    break_out = _parse_clock_on_day(result.get("break_out"), work_day)
    break_in = _parse_clock_on_day(result.get("break_in"), work_day)
    planned = max(1, int(cfg.get("break_planned_minutes") or DEFAULT_BREAK_MINUTES))

    # Example: 12:58:59 / 12:59:02 are one shift-check-in group, while
    # 15:53:31 / 15:53:33 are one later group. Do not wait for another scan
    # before exposing the first scan of that later group as break-out.
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

    deadline = break_return_deadline(work_day, break_out, planned) if break_out else None
    return_late_minutes = 0
    if break_in is not None and deadline is not None and break_in > deadline:
        return_late_minutes = max(1, int((break_in - deadline).total_seconds() // 60))

    result["break_window_start"] = BREAK_START.strftime("%H:%M:%S")
    result["break_return_deadline"] = deadline.strftime("%H:%M:%S") if deadline else ""
    result["break_return_deadline_iso"] = deadline.isoformat() if deadline else ""
    result["break_return_late_minutes"] = return_late_minutes
    result["break_started"] = bool(break_out)
    result["break_planned_minutes"] = planned
    result["faceid_group_minutes"] = FACEID_GROUP_MINUTES
    result["break_remaining_seconds"] = (
        int((deadline - datetime.now()).total_seconds())
        if deadline is not None and break_in is None else 0
    )

    restricted_reason = str(cfg.get("break_restricted_reason") or "").strip()
    enabled = bool(cfg.get("break_enabled"))
    actual = int(result.get("break_actual_minutes") or 0)
    deadline_text = deadline.strftime("%H:%M:%S") if deadline else ""

    if break_out and break_in:
        result["break_detail"] = (
            f"Nghỉ giữa ca {break_out.strftime('%d/%m/%Y %H:%M:%S')} → "
            f"{break_in.strftime('%d/%m/%Y %H:%M:%S')}"
        )
        if restricted_reason:
            result["break_status"] = f"Vi phạm: {restricted_reason} không được nghỉ giữa ca ({actual} phút)"
        elif return_late_minutes > 0:
            result["break_status"] = f"Vào lại trễ {return_late_minutes} phút · hạn {deadline_text}"
        elif planned > 0 and actual > planned:
            result["break_status"] = f"Quá {actual - planned} phút · hạn {deadline_text}"
        elif enabled:
            result["break_status"] = f"Trong giới hạn · hạn vào lại {deadline_text}"
    elif break_out:
        if restricted_reason:
            result["break_status"] = f"Vi phạm: {restricted_reason} · đã bắt đầu nghỉ giữa ca"
        elif enabled:
            result["break_status"] = f"Đã bắt đầu nghỉ giữa ca · phải vào lại lúc {deadline_text}"

    return result


def install_attendance_break_window(app) -> None:
    if getattr(app.state, "attendance_break_window_installed", False):
        return

    # Attendance 4.2 resolves _cluster_punches at runtime. Force every screen,
    # export and break calculation to use the user's 5-minute grouping rule.
    original_cluster = attendance._cluster_punches

    def cluster_in_five_minutes(values, minutes=FACEID_GROUP_MINUTES):
        return original_cluster(values, FACEID_GROUP_MINUTES)

    attendance._cluster_punches = cluster_in_five_minutes

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
            "deadline_rule": "min(break_out + configured break minutes, 20:00:00)",
            "return_latest": BREAK_RETURN_LATEST.strftime("%H:%M:%S"),
            "default_break_minutes": DEFAULT_BREAK_MINUTES,
            "faceid_group_minutes": FACEID_GROUP_MINUTES,
            "group_rule": "first FaceID in each <=5 minute group",
            "show_in_progress_break": True,
        }

    app.state.attendance_break_window_installed = True
    app.state.attendance_break_window_release = RELEASE

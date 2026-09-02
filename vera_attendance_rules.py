"""Dependency-free attendance rules shared by API code and regression tests."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any


VERA_TIMEZONE = timezone(timedelta(hours=7))
BREAK_RETURN_LATEST = time(20, 0, 0)


def break_return_deadline(work_day: date, break_out: datetime, planned_minutes: int) -> datetime:
    """Return the earned break deadline, capped at the mandatory 20:00 return."""
    earned_deadline = break_out + timedelta(minutes=max(1, int(planned_minutes or 0)))
    latest_deadline = datetime.combine(work_day, BREAK_RETURN_LATEST)
    return min(earned_deadline, latest_deadline)


def supported_late_minutes(raw_minutes: float, allowance_minutes: int | None) -> float | None:
    """Return minutes late after support; None means unknown support is fail-closed."""
    if allowance_minutes is None:
        return None
    return max(0.0, float(raw_minutes or 0) - max(0, int(allowance_minutes)))


def late_penalty_eligible(raw_minutes: float, threshold_minutes: int, allowance_minutes: int | None = 0) -> bool:
    """Apply support first, then the normal late-penalty threshold."""
    adjusted = supported_late_minutes(raw_minutes, allowance_minutes)
    return adjusted is not None and adjusted >= max(0, int(threshold_minutes))


def apply_break_restriction(cfg: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    """Attach eligibility reasons without changing the shift's configured break."""
    result = dict(cfg)
    if reasons:
        result["break_restricted_reason"] = " và ".join(reasons)
    return result


def departure_status_is_final(
    *,
    clustered_punch_count: int,
    work_day: date,
    expected_end: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Return whether TimeSoft's departure label can be treated as final."""
    if clustered_punch_count < 2:
        return False

    current = now
    if current is None:
        current = datetime.now(VERA_TIMEZONE).replace(tzinfo=None)
    elif current.tzinfo is not None:
        current = current.astimezone(VERA_TIMEZONE).replace(tzinfo=None)

    if expected_end is not None:
        return current >= expected_end
    return current.date() > work_day

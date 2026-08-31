"""Dependency-free attendance rules shared by API code and regression tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any


VERA_TIMEZONE = timezone(timedelta(hours=7))


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

"""Pure calculations for Web V2 department attendance."""
from __future__ import annotations

import re
from typing import Any


def _clock_minutes(value: Any) -> float | None:
    match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(value or ""))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2)) + int(match.group(3) or 0) / 60


def schedule_late_minutes(check_in: Any, start_time: Any) -> float | None:
    """Return lateness against the Web V2 scheduled start, including overnight clocks."""
    actual, expected = _clock_minutes(check_in), _clock_minutes(start_time)
    if actual is None or expected is None:
        return None
    difference = actual - expected
    if difference < -12 * 60:
        difference += 24 * 60
    return max(0.0, difference)

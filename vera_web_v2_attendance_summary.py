"""Read-only attendance card predicates, mirrored by SnapshotPage's filters.

These groups intentionally overlap. They only select existing, authorized
snapshot rows; they do not calculate attendance, violations, or penalties.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Literal
from zoneinfo import ZoneInfo


SummaryFilter = Literal["all", "breaks", "over", "incomplete"]
SUMMARY_FILTERS = {"all", "breaks", "over", "incomplete"}
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_CLOCK = re.compile(r"^\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$")
_ISO_DEADLINE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
    r"(?P<offset>Z|[+-]\d{2}:?\d{2})?$", re.IGNORECASE,
)


def _localize(value: datetime) -> datetime:
    return value.replace(tzinfo=VIETNAM_TZ) if value.tzinfo is None else value


def _deadline(item: dict[str, Any]) -> datetime | None:
    raw = str(item.get("break_return_deadline_iso") or "").strip().replace(" ", "T", 1)
    match = _ISO_DEADLINE.fullmatch(raw)
    if match:
        try:
            offset = (match.group("offset") or "").upper()
            # Python normalizes malformed offsets such as +07:60, while the
            # browser rejects them. Reject before parsing to keep selection equal.
            if offset and offset != "Z":
                digits = offset[1:].replace(":", "")
                if int(digits[:2]) >= 24 or int(digits[2:]) >= 60:
                    raise ValueError("Invalid timezone offset")
            return _localize(datetime.fromisoformat(raw.upper().replace("Z", "+00:00")))
        except ValueError:
            pass

    day = str(item.get("date") or "").strip()
    clock = str(item.get("break_return_deadline") or "").strip()
    if not _CLOCK.fullmatch(clock):
        return None
    for pattern, fmt in (
        (r"\d{1,2}/\d{1,2}/\d{4}", "%d/%m/%Y"),
        (r"\d{1,2}-\d{1,2}-\d{4}", "%d-%m-%Y"),
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
    ):
        if not re.fullmatch(pattern, day):
            continue
        try:
            parsed_day = datetime.strptime(day, fmt).date()
            return _localize(datetime.fromisoformat(f"{parsed_day.isoformat()}T{clock}"))
        except ValueError:
            return None
    return None


def _positive(value: Any) -> bool:
    try:
        return float(value or 0) > 0
    except (TypeError, ValueError, OverflowError):
        return False


def filter_attendance_summary(
    records: list[dict[str, Any]],
    summary_filter: SummaryFilter = "all",
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Select a card using one server timestamp, preserving rows and order."""
    if summary_filter not in SUMMARY_FILTERS:
        raise ValueError("Unknown attendance summary filter")
    if summary_filter == "all":
        return records
    if summary_filter == "breaks":
        return [item for item in records if not item.get("break_restricted_reason")
                and item.get("break_out") and item.get("break_in")]
    if summary_filter == "incomplete":
        return [item for item in records if not item.get("break_restricted_reason")
                and item.get("break_enabled")
                and (not item.get("break_out") or not item.get("break_in"))]

    observed_at = _localize(now) if now is not None else datetime.now(VIETNAM_TZ)

    def over(item):
        if item.get("break_restricted_reason"):
            return bool(item.get("break_out"))
        if _positive(item.get("break_over_minutes")) or _positive(item.get("break_return_late_minutes")):
            return True
        if not item.get("break_out") or item.get("break_in"):
            return False
        deadline = _deadline(item)
        return deadline is not None and deadline < observed_at

    return [item for item in records if over(item)]

"""Pure, fail-closed calendar authorization for Live Tour date filters.

The caller supplies already-resolved feature grants; this module never acquires
connections or changes permission inheritance. Dates are inclusive Vietnam
calendar dates, independent of Live Tour's operational counter rollover.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
import re
from typing import Any, Callable, Iterable, Mapping, TypeVar
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PRESETS = ("all", "today", "yesterday", "week", "last-week", "month", "last-month", "custom")
SECTIONS = ("pending", "invoices", "reports", "history")
FINITE_PRESETS = tuple(preset for preset in PRESETS if preset not in {"all", "custom"})
PARENT_FEATURES = {
    "pending": ("live_tour_pending_view", "live_tour_invoice_view"),
    "invoices": ("live_tour_paid_invoice_view",),
    "reports": ("live_tour_reports_view",),
    "history": ("live_tour_history_view", "live_tour_backup"),
}
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
Row = TypeVar("Row")
DateRange = tuple[date, date]


class DatePolicyError(ValueError):
    """Framework-independent validation error for the HTTP adapter."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def feature_id(section: str, preset: str) -> str:
    if section not in SECTIONS or preset not in PRESETS:
        raise ValueError("Unknown Live Tour date section or preset")
    return f"live_tour_{section}_date_{preset.replace('-', '_')}"


DATE_FEATURES = tuple(feature_id(section, preset) for section in SECTIONS for preset in PRESETS)


def server_today(now: datetime | date) -> date:
    """Use Vietnam calendar midnight; a naive server timestamp is Vietnam time."""
    if isinstance(now, datetime):
        moment = now.replace(tzinfo=VN_TZ) if now.tzinfo is None else now.astimezone(VN_TZ)
        return moment.date()
    if isinstance(now, date):
        return now
    raise TypeError("now must be a server datetime or date")


def build_policy(effective_features: Mapping[str, bool], now: datetime | date) -> dict[str, Any]:
    """Return public capabilities when the section's read gates pass.

    Board/collection routes independently enforce ``live_tour_view``. Direct
    section exports and standalone Reports do not require that board grant.
    History supports either its audit read gate or its backup gate. This does
    not authorize audit rows for a backup-only user: callers must still apply
    each collection's existing read gate before returning its rows.
    """
    sections = {}
    for section in SECTIONS:
        parents = PARENT_FEATURES[section]
        parent_values = [bool(effective_features.get(key, False)) for key in parents]
        readable = any(parent_values) if section == "history" else all(parent_values)
        sections[section] = [preset for preset in PRESETS
                             if readable and bool(effective_features.get(feature_id(section, preset), False))]
    return {"version": 1, "sections": sections, "server_today": server_today(now).isoformat()}


def _grants(policy: Mapping[str, Any], section: str) -> frozenset[str]:
    if section not in SECTIONS:
        raise DatePolicyError(400, "Bộ lọc ngày không thuộc danh sách Live Tour hợp lệ.")
    if not isinstance(policy, Mapping) or policy.get("version") != 1:
        return frozenset()
    sections = policy.get("sections")
    if not isinstance(sections, Mapping):
        return frozenset()
    values = sections.get(section)
    if not isinstance(values, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(value for value in values if isinstance(value, str) and value in PRESETS)


def canonical_range(preset: str, now: datetime | date) -> DateRange:
    """Compute one finite preset from the current trusted server clock."""
    today = server_today(now)
    if preset == "today":
        return today, today
    if preset == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if preset in {"week", "last-week"}:
        first = today - timedelta(days=today.weekday() + (7 if preset == "last-week" else 0))
        return first, first + timedelta(days=6)
    if preset in {"month", "last-month"}:
        first = today.replace(day=1)
        if preset == "last-month":
            first = (first - timedelta(days=1)).replace(day=1)
        return first, first.replace(day=monthrange(first.year, first.month)[1])
    raise DatePolicyError(400, "Bộ lọc ngày không có khoảng ngày cố định hợp lệ.")


def _parse_date(value: str | None, field: str) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise DatePolicyError(400, f"{field} phải là ngày hợp lệ theo định dạng YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DatePolicyError(400, f"{field} phải là ngày hợp lệ theo định dạng YYYY-MM-DD.") from exc


def _merged(ranges: Iterable[DateRange]) -> tuple[DateRange, ...]:
    merged: list[DateRange] = []
    for first, last in sorted(ranges):
        # Compare ordinals to avoid overflow at date.max.
        if merged and first.toordinal() <= merged[-1][1].toordinal() + 1:
            merged[-1] = merged[-1][0], max(merged[-1][1], last)
        else:
            merged.append((first, last))
    return tuple(merged)


def _covered(first: date, last: date, ranges: Iterable[DateRange]) -> bool:
    return any(start <= first and last <= end for start, end in _merged(ranges))


def authorize_request(
    policy: Mapping[str, Any], section: str, now: datetime | date,
    preset: str = "", date_from: str = "", date_to: str = "", selected_date: str = "",
) -> dict[str, Any]:
    """Validate and normalize a requested range, raising 400 or 403 on failure.

    Named presets require that exact grant, even if another grant covers the
    same dates. Finite presets derive missing bounds from the server clock and
    allow only narrowing. Legacy unnamed ranges require complete coverage by
    the union of finite grants (or the unrestricted ``all`` grant). A lone
    selected date is bounded; partial ranges require ``all``. ``custom`` never
    grants an implicit range and always requires both real, ordered dates.

    Returned ``date_from``/``date_to`` are ISO strings (empty when unbounded),
    and ``bounds`` contains equivalent date objects for the export predicate.
    A supplied ``selected_date`` is intersected into the normalized range.
    """
    grants = _grants(policy, section)
    if not isinstance(preset, str) or (preset and preset not in PRESETS):
        raise DatePolicyError(400, "Bộ lọc ngày Live Tour không hợp lệ.")
    first = _parse_date(date_from, "Ngày bắt đầu")
    last = _parse_date(date_to, "Ngày kết thúc")
    selected = _parse_date(selected_date, "Ngày đã chọn")
    if first and last and first > last:
        raise DatePolicyError(400, "Ngày bắt đầu không được sau ngày kết thúc.")
    if preset == "custom" and (first is None or last is None):
        raise DatePolicyError(400, "Khoảng ngày tùy chọn phải có đủ ngày bắt đầu và ngày kết thúc.")

    if preset:
        if preset not in grants:
            raise DatePolicyError(403, "Bạn chưa được cấp quyền dùng bộ lọc ngày này.")
        if preset in FINITE_PRESETS:
            canonical_first, canonical_last = canonical_range(preset, now)
            if any(value is not None and not canonical_first <= value <= canonical_last
                   for value in (first, last, selected)):
                raise DatePolicyError(403, "Khoảng ngày vượt quá bộ lọc ngày được cấp quyền.")
            first = first or canonical_first
            last = last or canonical_last
    elif "all" not in grants:
        if first is None and last is None and selected is not None:
            first = last = selected
        if first is None or last is None or not _covered(
            first, last, (canonical_range(item, now) for item in FINITE_PRESETS if item in grants)
        ):
            raise DatePolicyError(403, "Khoảng ngày không nằm trong các bộ lọc ngày được cấp quyền.")

    if selected is not None:
        if (first is not None and selected < first) or (last is not None and selected > last):
            raise DatePolicyError(403, "Ngày đã chọn nằm ngoài khoảng ngày được cấp quyền.")
        first = last = selected
    return {
        "section": section,
        "preset": preset or ("all" if first is None and last is None else ""),
        "date_from": first.isoformat() if first else "",
        "date_to": last.isoformat() if last else "",
        "selected_date": selected.isoformat() if selected else "",
        "bounds": {"date_from": first, "date_to": last},
    }


def allowed_ranges(
    policy: Mapping[str, Any], section: str, now: datetime | date,
    request: Mapping[str, Any] | None = None,
) -> tuple[DateRange, ...] | None:
    """Public row date coverage; ``None`` is unrestricted, ``()`` denies all.

    Custom alone yields no default coverage. A valid explicit custom request
    supplements the finite-grant union for its own section only. Revalidate it
    instead of trusting caller-provided bounds or an obsolete capability date.
    """
    grants = _grants(policy, section)
    if "all" in grants:
        return None
    ranges = [canonical_range(preset, now) for preset in FINITE_PRESETS if preset in grants]
    if request is not None and request.get("section") == section and request.get("preset") == "custom":
        authorized = authorize_request(
            policy, section, now, preset="custom", date_from=request.get("date_from", ""),
            date_to=request.get("date_to", ""), selected_date=request.get("selected_date", ""),
        )
        ranges.append((authorized["bounds"]["date_from"], authorized["bounds"]["date_to"]))
    return _merged(ranges)


def calendar_date(value: Any) -> date | None:
    """Parse a stored row's date or timestamp to a Vietnam calendar date.

    The caller chooses the source field to preserve each collection's existing
    date semantics. Unknown or malformed row dates fail closed for finite grants.
    """
    if isinstance(value, datetime):
        return server_today(value)
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        if _ISO_DATE.fullmatch(value):
            return date.fromisoformat(value)
        # Stored timestamps may be naive: existing Live Tour treats those as VN.
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return server_today(moment)
    except (TypeError, ValueError, OverflowError):
        return None


def date_allowed(value: Any, ranges: tuple[DateRange, ...] | None) -> bool:
    if ranges is None:
        return True
    day = calendar_date(value)
    return day is not None and any(first <= day <= last for first, last in ranges)


def filter_rows(
    policy: Mapping[str, Any], section: str, now: datetime | date,
    rows: Iterable[Row], date_getter: Callable[[Row], Any],
    request: Mapping[str, Any] | None = None,
) -> list[Row]:
    """Filter before pagination, counts, totals, nested summaries, or export."""
    ranges = allowed_ranges(policy, section, now, request=request)
    if ranges is None:
        return list(rows)
    return [row for row in rows if date_allowed(date_getter(row), ranges)]

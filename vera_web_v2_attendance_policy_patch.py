"""Attendance policy compatibility patch for current VERA Nội quy.

This module keeps four business rules in one place:
1. Current official policy names use "nhỏ hơn hoặc bằng" thresholds for
   Ra ngoài vào muộn, while the legacy helper searched older "dưới" labels.
2. A pre-registered Về sớm day with only two FaceID groups is shift check-in
   + final early checkout, not a mid-shift break. Five-minute FaceID grouping
   means a checkout group beginning a few minutes before 17:00 is still the
   17:00 checkout event.
3. If an employee first goes outside and only afterwards receives/enters a
   same-day Đi trễ/Về sớm restriction, the outside event is a violation. The
   violation duration is measured from the first FaceID of the outside group
   through exactly 17:00:00 and rounded up to the next whole minute for the
   official Ra ngoài vào muộn penalty tier.
4. TimeSoft summary-only checkout values must not keep a false open-break alert
   when TourVera already has a completed S=Giờ ra / U=Giờ vào pair. R=Break is
   still authoritative while the employee is actively out; after return R may
   be blank while S/U retain the completed pair, which must clear the alert.

Performance patches are installed at module-import time because api_v38 imports
this module before it installs the attendance route chain. This guarantees
Chấm công reads only requested TimeSoft date keys and TourVera fallback reads
only the PostgreSQL cache populated by background jobs; user requests never
open/download the XLSM from Google Drive.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
import math
from typing import Any

import vera_auto_check as auto_check
import vera_web_v2_attendance_break_alerts as break_alerts
import vera_web_v2_outside_leave_rule as outside_rule
import vera_web_v2_tour_cache_perf as tour_cache_perf
from vera_web_v2_attendance_query_perf import install as install_attendance_query_perf
from vera_web_v2_tour_cache_perf import install as install_tour_cache_perf


RELEASE = "attendance-policy-faceid-5m-tour-pg-fast-2026-08-31-v4"
EARLY_CHECKOUT_GROUP_START = time(16, 55, 0)
TOUR_MATCH_PADDING = timedelta(minutes=5)

# api_v38 imports this module before calling install_attendance_v42(). Patching
# here ensures snapshot._records captures the optimized function from the start.
install_attendance_query_perf()
install_tour_cache_perf()


def _catalog_first(catalog: dict[str, dict], names: list[str]):
    for name in names:
        item = auto_check.catalog_item(catalog, name)
        if item:
            return item
    return None


def _outside_reason_current_policy(catalog: dict[str, dict], minutes: float):
    """Resolve current Nội quy labels and keep legacy aliases as fallback."""
    value = max(0.0, float(minutes or 0))
    if value <= 30:
        names = [
            "Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút",
            "Ra ngoài vào muộn dưới 30 phút",
        ]
    elif value <= 60:
        names = [
            "Ra ngoài vào muộn nhỏ hơn hoặc bằng 60 phút",
            "Ra ngoài vào muộn dưới 60 phút",
        ]
    elif value <= 120:
        names = [
            "Ra ngoài vào muộn nhỏ hơn hoặc bằng 120 phút",
            "Ra ngoài vào muộn dưới 120 phút",
        ]
    else:
        names = [
            "Ra ngoài vào muộn trên 120 phút",
            "Ra ngoài vào muộn từ 120 phút trở lên",
        ]
    return _catalog_first(catalog, names)


def _violation_for_1700_cutoff(*, catalog: dict[str, dict], work_day, break_out: datetime):
    """Calculate the no-break violation from actual outside time to 17:00.

    The FaceID group is already anchored to its first scan by the attendance
    five-minute grouping patch. Keep the exact seconds in the audit detail, but
    round any partial minute upward when selecting the official penalty tier.

    Example: 15:53:31 -> 17:00:00 is 66m29s, therefore 67 penalty minutes.
    """
    cutoff = datetime.combine(work_day, outside_rule.CUTOFF)
    if break_out > cutoff:
        return (
            outside_rule._single_side_item(catalog),
            0,
            f"Giờ ra {break_out.strftime('%H:%M:%S')} sau 17:00:00",
        )

    exact_seconds = max(0, int((cutoff - break_out).total_seconds()))
    whole_minutes, remainder_seconds = divmod(exact_seconds, 60)
    penalty_minutes = max(0, int(math.ceil(exact_seconds / 60)))
    reason_item = auto_check.outside_reason(catalog, penalty_minutes)
    calculation = (
        f"Tính từ Giờ ra {break_out.strftime('%H:%M:%S')} đến 17:00:00"
        f" = {whole_minutes} phút {remainder_seconds:02d} giây"
        f" · Quy đổi {penalty_minutes} phút"
    )
    return reason_item, penalty_minutes, calculation


def _parse_group_times(item: dict[str, Any], work_day) -> list[datetime]:
    values = item.get("punch_times") or []
    if not isinstance(values, list):
        return []
    output = []
    for value in values:
        parsed = outside_rule._parse_clock(value, work_day)
        if parsed is not None:
            output.append(parsed)
    return sorted(output)


def _tour_completed_pairs(conn, work_day) -> dict[str, dict[str, Any]]:
    """Read completed S/U pairs from the fresh PostgreSQL TourVera cache."""
    return tour_cache_perf.completed_pairs(conn, work_day)


def _completed_tour_covers_timesoft_open(
    current_break_out: datetime | None,
    tour_break_out: datetime | None,
    tour_break_in: datetime | None,
) -> bool:
    """Return True when TourVera proves the TimeSoft 'open' event already ended."""
    if current_break_out is None or tour_break_out is None or tour_break_in is None:
        return False
    return (
        tour_break_out - TOUR_MATCH_PADDING
        <= current_break_out
        <= tour_break_in + TOUR_MATCH_PADDING
    )


def install_attendance_policy_patch() -> None:
    if getattr(outside_rule, "_attendance_policy_patch_release", "") == RELEASE:
        return

    # Current official Nội quy names and exact 17:00 cutoff logic are both used
    # by the same-day restriction wrapper on every attendance refresh/poll.
    auto_check.outside_reason = _outside_reason_current_policy
    outside_rule._violation_for = _violation_for_1700_cutoff

    original_scheduled_early_checkout = outside_rule._scheduled_early_checkout
    original_tour_break_map = break_alerts._tour_break_map
    original_apply_tour_fallback = break_alerts._apply_tour_fallback

    def scheduled_early_checkout_with_faceid_groups(
        item: dict[str, Any],
        *,
        work_day,
        reasons: list[str],
        early_leave_registered_at: datetime | None,
        break_out: datetime,
    ) -> datetime | None:
        # Preserve the critical distinction:
        # - Về sớm entered before the checkout event => final checkout.
        # - employee went outside first, Về sớm entered afterwards => NOT a
        #   normal break and NOT a final checkout; keep the outside event so the
        #   17:00-cutoff automatic penalty is written by outside_leave_rule.
        if not any(outside_rule._early_leave_reason(reason) for reason in reasons):
            return None
        if early_leave_registered_at is None or early_leave_registered_at > break_out:
            return None

        source = outside_rule._norm(item.get("break_source") or item.get("break_method"))
        if source and "timesoft" not in source:
            return original_scheduled_early_checkout(
                item,
                work_day=work_day,
                reasons=reasons,
                early_leave_registered_at=early_leave_registered_at,
                break_out=break_out,
            )

        groups = _parse_group_times(item, work_day)
        # The canonical pre-registered Về sớm shape is exactly two groups:
        # group 1 = shift check-in; group 2 = final checkout around/from 17:00.
        # Because a group is anchored by its first scan, tolerate 16:55..17:00.
        if len(groups) == 2:
            checkout = groups[1]
            if checkout.time() >= EARLY_CHECKOUT_GROUP_START and outside_rule._same_event(checkout, break_out, 5 * 60):
                return checkout

        return original_scheduled_early_checkout(
            item,
            work_day=work_day,
            reasons=reasons,
            early_leave_registered_at=early_leave_registered_at,
            break_out=break_out,
        )

    def tour_break_map_with_completed(conn, work_day):
        result = dict(original_tour_break_map(conn, work_day))
        for key, pair in _tour_completed_pairs(conn, work_day).items():
            current = result.get(key)
            # Active R=Break from the cached map remains authoritative. Once R
            # is blank, persisted S/U confirms the employee has already returned.
            if not current or not str(current.get("break_flag") or "").strip():
                result[key] = pair
        return result

    def apply_tour_fallback_with_completed(conn, records, start, end):
        # Preserve the existing fallback first. The original function resolves
        # _tour_break_map at runtime, so it also sees PostgreSQL active breaks.
        output = original_apply_tour_fallback(conn, records, start, end)
        today = datetime.now().date()
        if not (start <= today <= end):
            return output

        tour_map = break_alerts._tour_break_map(conn, today)
        patched = []
        for raw in output:
            item = dict(raw)
            try:
                work_day = datetime.strptime(str(item.get("date") or ""), "%d/%m/%Y").date()
            except ValueError:
                patched.append(item)
                continue
            if work_day != today:
                patched.append(item)
                continue

            tour = tour_map.get(break_alerts._norm(item.get("employee_name")))
            if not tour or tour.get("break_in") is None:
                patched.append(item)
                continue

            # A genuine complete TimeSoft pair keeps priority. Repair only an
            # apparently open TimeSoft event that sits inside the completed
            # TourVera S/U interval.
            if str(item.get("break_in") or "").strip():
                patched.append(item)
                continue

            current_break_out = break_alerts._parse_clock(item.get("break_out"), work_day)
            tour_break_out = tour.get("break_out")
            tour_break_in = tour.get("break_in")
            if not _completed_tour_covers_timesoft_open(current_break_out, tour_break_out, tour_break_in):
                patched.append(item)
                continue

            planned = int(item.get("break_planned_minutes") or break_alerts.DEFAULT_BREAK_MINUTES)
            item.update(break_alerts._deadline_payload(
                work_day=work_day,
                break_out=tour_break_out,
                break_in=tour_break_in,
                planned_minutes=planned,
                source="TourVera · S=Giờ ra, U=Giờ vào (đã vào lại)",
            ))
            item["break_count"] = 1
            item["break_method"] = "TourVera xác nhận cặp nghỉ đã hoàn tất; bỏ cảnh báo TimeSoft summary"
            item["break_false_open_repaired"] = True
            patched.append(item)
        return patched

    outside_rule._scheduled_early_checkout = scheduled_early_checkout_with_faceid_groups
    break_alerts._tour_break_map = tour_break_map_with_completed
    break_alerts._apply_tour_fallback = apply_tour_fallback_with_completed
    outside_rule._attendance_policy_patch_release = RELEASE

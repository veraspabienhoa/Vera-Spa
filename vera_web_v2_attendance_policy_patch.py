"""Attendance policy compatibility patch for current VERA Nội quy.

This module keeps three business rules in one place:
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
"""
from __future__ import annotations

from datetime import datetime, time
import math
from typing import Any

import vera_auto_check as auto_check
import vera_web_v2_outside_leave_rule as outside_rule


RELEASE = "attendance-policy-faceid-5m-1700-cutoff-2026-08-31-v2"
EARLY_CHECKOUT_GROUP_START = time(16, 55, 0)


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


def install_attendance_policy_patch() -> None:
    if getattr(outside_rule, "_attendance_policy_patch_release", "") == RELEASE:
        return

    # Current official Nội quy names and exact 17:00 cutoff logic are both used
    # by the same-day restriction wrapper on every attendance refresh/poll.
    auto_check.outside_reason = _outside_reason_current_policy
    outside_rule._violation_for = _violation_for_1700_cutoff

    original_scheduled_early_checkout = outside_rule._scheduled_early_checkout

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

    outside_rule._scheduled_early_checkout = scheduled_early_checkout_with_faceid_groups
    outside_rule._attendance_policy_patch_release = RELEASE

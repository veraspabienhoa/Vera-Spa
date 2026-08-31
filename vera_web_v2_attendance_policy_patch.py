"""Attendance policy compatibility patch for current VERA Nội quy.

This module keeps two business rules in one place:
1. Current official policy names use "nhỏ hơn hoặc bằng" thresholds for
   Ra ngoài vào muộn, while the legacy helper searched older "dưới" labels.
2. A pre-registered Về sớm day with only two FaceID groups is shift check-in
   + final early checkout, not a mid-shift break.  Five-minute FaceID grouping
   means a checkout group beginning a few minutes before 17:00 is still the
   17:00 checkout event.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any

import vera_auto_check as auto_check
import vera_web_v2_outside_leave_rule as outside_rule


RELEASE = "attendance-policy-faceid-5m-2026-08-31-v1"
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

    auto_check.outside_reason = _outside_reason_current_policy

    original_scheduled_early_checkout = outside_rule._scheduled_early_checkout

    def scheduled_early_checkout_with_faceid_groups(
        item: dict[str, Any],
        *,
        work_day,
        reasons: list[str],
        early_leave_registered_at: datetime | None,
        break_out: datetime,
    ) -> datetime | None:
        # Preserve the earlier distinction: if Về sớm was entered only after
        # the employee had already gone out, that event remains a violation.
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
        # The user's canonical Về sớm shape is exactly two groups:
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

"""Granular permissions for VERA Web V2 work schedules.

Adds exactly three schedule permissions to the existing Phân quyền system:
- work_schedule_quanly: lịch Quản lý
- work_schedule_letan: lịch Lễ tân
- work_schedule_locker: lịch Locker

The permission module and the core API import their feature/default dictionaries by
reference, so mutating those dictionaries in place keeps the existing permission
routes, role/account overrides, cache, and Google Sheet mirror fully compatible.
"""
from __future__ import annotations

import vera_web_v2_permissions as permissions


WORK_SCHEDULE_PERMISSION_GROUP = {
    "work_schedule_quanly": "Lịch làm việc · Quản lý",
    "work_schedule_letan": "Lịch làm việc · Lễ tân",
    "work_schedule_locker": "Lịch làm việc · Locker",
}


def install_work_schedule_permissions() -> None:
    group = permissions.FEATURE_GROUPS.setdefault("Lịch làm việc", {})
    group.update(WORK_SCHEDULE_PERMISSION_GROUP)
    permissions.FEATURES.update(WORK_SCHEDULE_PERMISSION_GROUP)

    # Defaults: Quản lý can arrange all three groups; Lễ tân and Locker can see
    # their own group. Admin already receives set(FEATURES) dynamically through
    # the permission resolver and remains unrestricted.
    permissions.DEFAULT_ROLE_FEATURES.setdefault("quanly", set()).update(WORK_SCHEDULE_PERMISSION_GROUP)
    permissions.DEFAULT_ROLE_FEATURES.setdefault("letan", set()).add("work_schedule_letan")
    permissions.DEFAULT_ROLE_FEATURES.setdefault("locker", set()).add("work_schedule_locker")

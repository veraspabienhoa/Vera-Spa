"""Lễ tân/Quản lý leave-edit/delete guard for VERA SPA Web V2.

Business rule (restored from the 2026-08-29 guard and applied equally to
``letan`` and ``quanly``):
- Records before today cannot be edited or deleted.
- For records dated today whose current reason belongs to one of the five
  explicitly approved groups below, the editor cannot delete the row and may
  change ``Lý do nghỉ`` only within that same group.
- Other reasons/types dated today keep the existing canonical edit/delete
  behavior from Phân quyền + Nội quy.
- Future-dated records continue through the existing canonical permission and
  cancellation rules unchanged.

Admin is intentionally not handled by this guard. The canonical Admin path
remains unrestricted by these editor-role locks.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException


RELEASE = "operations-leave-guard-2026-09-07-v3"
EDITOR_ROLES = {
    "letan": "Lễ tân",
    "quanly": "Quản lý",
}

LETAN_REASON_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Nhóm 1",
        (
            "Nghỉ CÓ phép",
            "Đi trễ CÓ phép",
            "Về sớm CÓ phép",
        ),
    ),
    (
        "Nhóm 2",
        (
            "Nghỉ KHÔNG phép",
            "Đi trễ KHÔNG phép",
            "Về sớm KHÔNG phép",
        ),
    ),
    (
        "Nhóm 3",
        (
            "Nghỉ CUỐI TUẦN CÓ phép",
            "Đi trễ CUỐI TUẦN CÓ phép",
            "Về sớm CUỐI TUẦN CÓ phép",
        ),
    ),
    (
        "Nhóm 4",
        (
            "Nghỉ CUỐI TUẦN KHÔNG phép",
            "Đi trễ CUỐI TUẦN KHÔNG phép",
            "Về sớm CUỐI TUẦN KHÔNG phép",
        ),
    ),
    (
        "Nhóm 5",
        (
            "Leader nghỉ phép theo chính sách",
            "Leader đi trễ sớm theo chính sách",
            "Leader về sớm về sớm theo chính sách",
            # Compatibility alias for existing Nội quy rows that may use the
            # corrected wording without the duplicated "về sớm".
            "Leader về sớm theo chính sách",
        ),
    ),
)


def _role(ident: Any) -> str:
    return str(getattr(ident, "role", "") or "").strip().lower()


def _role_label(role: str) -> str:
    return EDITOR_ROLES.get(role, role or "Tài khoản")


def _reason_group(reason: Any, norm) -> str:
    key = norm(reason)
    if not key:
        return ""
    for group_name, reasons in LETAN_REASON_GROUPS:
        if any(norm(item) == key for item in reasons):
            return group_name
    return ""


def install_letan_leave_guard(app, *, api_module, vn_tz) -> None:
    if getattr(app.state, "letan_leave_guard_installed", False):
        return

    original_edit = api_module._validate_edit_permission
    original_delete = api_module._validate_delete_permission
    norm = api_module._norm

    def validate_edit_permission(conn, row: dict, new_reason: str, ident):
        role = _role(ident)
        if role not in EDITOR_ROLES:
            return original_edit(conn, row, new_reason, ident)

        label = _role_label(role)
        target = row["leave_date"]
        today = datetime.now(vn_tz).date()
        if target < today:
            raise HTTPException(
                403,
                f"Tài khoản {label} không được sửa đăng ký có ngày trước ngày hiện tại.",
            )

        if target == today:
            old_reason = str(row.get("leave_reason") or "").strip()
            old_group = _reason_group(old_reason, norm)

            # The five named groups are the only same-day rows with the special
            # lock. Every other reason/type falls back to the canonical rules,
            # so anything the editor role is normally allowed to manage today
            # remains editable/changeable according to Phân quyền + Nội quy.
            if not old_group:
                return original_edit(conn, row, new_reason, ident)

            new_group = _reason_group(new_reason, norm)
            if new_group != old_group:
                raise HTTPException(
                    403,
                    f"Ngày hiện tại {label} chỉ được đổi Lý do nghỉ trong cùng {old_group}.",
                )

            # Explicit same-day/same-group exception restored from the original
            # Lễ tân rule. The replacement reason must still exist in Nội quy,
            # but editor-role/day/timing checks do not block switching among
            # the three reasons of the same group. Remaining canonical update
            # validation (duplicates, quotas, employee and persistence) stays on.
            item = api_module._reason_item(conn, new_reason)
            return item, True

        # Future-dated rows preserve feature flags, notice/cancellation period,
        # registration rules and all other canonical behavior.
        return original_edit(conn, row, new_reason, ident)

    def validate_delete_permission(conn, row: dict, ident) -> None:
        role = _role(ident)
        if role not in EDITOR_ROLES:
            return original_delete(conn, row, ident)

        label = _role_label(role)
        target = row["leave_date"]
        today = datetime.now(vn_tz).date()
        if target < today:
            raise HTTPException(
                403,
                f"Tài khoản {label} không được xóa đăng ký có ngày trước ngày hiện tại.",
            )

        reason = str(row.get("leave_reason") or "").strip()
        if target == today and _reason_group(reason, norm):
            raise HTTPException(
                403,
                f"Tài khoản {label} không được xóa đăng ký ngày hiện tại thuộc Nhóm 1–5; chỉ được đổi Lý do nghỉ trong cùng nhóm.",
            )

        # Today + non-group, and all future rows, retain canonical delete
        # permission/cancellation rules from Phân quyền + Nội quy.
        return original_delete(conn, row, ident)

    api_module._validate_edit_permission = validate_edit_permission
    api_module._validate_delete_permission = validate_delete_permission

    @app.get("/v2/letan-leave-policy/health")
    def letan_leave_policy_health():
        return {
            "ok": True,
            "release": RELEASE,
            "managed_roles": sorted(EDITOR_ROLES),
            "today_special_scope": "groups_1_to_5_only",
            "other_today_reasons": "canonical_edit_delete",
            "groups": [
                {"name": name, "reasons": list(reasons[:3])}
                for name, reasons in LETAN_REASON_GROUPS
            ],
        }

    app.state.letan_leave_guard_installed = True
    app.state.letan_leave_guard_release = RELEASE

"""Lễ tân leave-edit/delete guard for VERA SPA Web V2.

Business rule:
- A ``letan`` account cannot edit or delete any leave registration before today.
- For registrations dated today whose current reason belongs to one of the five
  explicitly approved groups below, ``letan`` cannot delete the row and may
  change ``Lý do nghỉ`` only within that same group.
- Other reasons/types that ``letan`` is allowed to use today keep the existing
  canonical edit/delete behavior from Phân quyền + Nội quy.
- Future-dated records continue through the existing canonical permission and
  cancellation rules unchanged.

The guard patches the canonical permission helpers instead of only hiding UI
controls. Therefore direct API calls, Admin archive wrappers, and storage-side
leave deletion all hit the same server-side boundary.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException


RELEASE = "letan-leave-guard-2026-08-29-v2"

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
        if _role(ident) != "letan":
            return original_edit(conn, row, new_reason, ident)

        target = row["leave_date"]
        today = datetime.now(vn_tz).date()
        if target < today:
            raise HTTPException(
                403,
                "Tài khoản Lễ tân không được sửa đăng ký có ngày trước ngày hiện tại.",
            )

        if target == today:
            old_reason = str(row.get("leave_reason") or "").strip()
            old_group = _reason_group(old_reason, norm)

            # The five named groups are the only same-day rows with the special
            # lock. Every other reason/type falls back to the canonical rules,
            # so anything Lễ tân is normally allowed to manage today remains
            # editable/changeable.
            if not old_group:
                return original_edit(conn, row, new_reason, ident)

            new_group = _reason_group(new_reason, norm)
            if new_group != old_group:
                raise HTTPException(
                    403,
                    f"Ngày hiện tại Lễ tân chỉ được đổi Lý do nghỉ trong cùng {old_group}.",
                )

            # This is an explicit editor-role exception. The editor is Lễ tân,
            # so the old allowed_roles check must not reject Leader-policy rows
            # merely because they are intended for a Leader employee. The new
            # reason still has to exist in the canonical Nội quy. Returning
            # True bypasses only the old edit/cancellation timing rule; the
            # canonical update path still performs duplicate, quota, employee,
            # penalty and persistence validation.
            item = api_module._reason_item(conn, new_reason)
            return item, True

        # Future-dated rows preserve the existing feature flags, notice period,
        # registration rules and all other canonical behavior.
        return original_edit(conn, row, new_reason, ident)

    def validate_delete_permission(conn, row: dict, ident) -> None:
        if _role(ident) != "letan":
            return original_delete(conn, row, ident)

        target = row["leave_date"]
        today = datetime.now(vn_tz).date()
        if target < today:
            raise HTTPException(
                403,
                "Tài khoản Lễ tân không được xóa đăng ký có ngày trước ngày hiện tại.",
            )

        reason = str(row.get("leave_reason") or "").strip()
        if target == today and _reason_group(reason, norm):
            raise HTTPException(
                403,
                "Tài khoản Lễ tân không được xóa đăng ký ngày hiện tại thuộc Nhóm 1–5; chỉ được đổi Lý do nghỉ trong cùng nhóm.",
            )

        # Today + non-group, and all future rows, retain the canonical delete
        # permission/cancellation rules.
        return original_delete(conn, row, ident)

    api_module._validate_edit_permission = validate_edit_permission
    api_module._validate_delete_permission = validate_delete_permission

    @app.get("/v2/letan-leave-policy/health")
    def letan_leave_policy_health():
        return {
            "ok": True,
            "release": RELEASE,
            "today_special_scope": "groups_1_to_5_only",
            "other_today_reasons": "canonical_edit_delete",
            "groups": [
                {"name": name, "reasons": list(reasons[:3])}
                for name, reasons in LETAN_REASON_GROUPS
            ],
        }

    app.state.letan_leave_guard_installed = True
    app.state.letan_leave_guard_release = RELEASE

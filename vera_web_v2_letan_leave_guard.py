"""Lễ tân leave-edit/delete guard for VERA SPA Web V2.

Business rule:
- A ``letan`` account cannot edit or delete any leave registration before today.
- A ``letan`` account cannot delete a registration dated today.
- On today only, ``letan`` may change ``Lý do nghỉ`` only to another reason in
  the same explicitly approved group below.
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


RELEASE = "letan-leave-guard-2026-08-29"

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
            new_group = _reason_group(new_reason, norm)
            if not old_group:
                raise HTTPException(
                    403,
                    "Lý do hiện tại không thuộc Nhóm 1–5 nên Lễ tân không được sửa trong ngày hiện tại.",
                )
            if new_group != old_group:
                raise HTTPException(
                    403,
                    f"Ngày hiện tại Lễ tân chỉ được đổi Lý do nghỉ trong cùng {old_group}.",
                )

            # Keep Nội quy role/day applicability, but intentionally bypass the
            # old cancellation/registration timing rule for this one same-day,
            # same-group exception requested for Lễ tân. Returning True makes
            # the canonical update path skip registration timing while all
            # remaining duplicate/quota/employee validations still run.
            item = api_module._catalog_rule_for_edit(conn, new_reason, target, "letan")
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
        if target == today:
            raise HTTPException(
                403,
                "Tài khoản Lễ tân không được xóa đăng ký của ngày hiện tại; chỉ được đổi Lý do nghỉ trong cùng Nhóm 1–5.",
            )
        return original_delete(conn, row, ident)

    api_module._validate_edit_permission = validate_edit_permission
    api_module._validate_delete_permission = validate_delete_permission

    @app.get("/v2/letan-leave-policy/health")
    def letan_leave_policy_health():
        return {
            "ok": True,
            "release": RELEASE,
            "groups": [
                {"name": name, "reasons": list(reasons[:3])}
                for name, reasons in LETAN_REASON_GROUPS
            ],
        }

    app.state.letan_leave_guard_installed = True
    app.state.letan_leave_guard_release = RELEASE

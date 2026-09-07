"""Admin + Lễ tân/Quản lý leave-operation policy for VERA SPA Web V2.

Admin:
- Admin is never blocked by leave-policy rules when adding, editing or deleting
  leave records. Data-integrity requirements (valid employee/record/catalog
  values required to persist a row) remain, but notice periods, quotas,
  duplicate/same-day locks, cancellation timing and role/day rules do not block
  Admin.
- The Admin reason selector exposes the complete Nội quy reason catalog for any
  selected date; allowed-role and allowed-day filters are not applied to Admin.

Lễ tân / Quản lý (restored from the 2026-08-29 guard):
- Records before today cannot be edited or deleted.
- For records dated today whose current reason belongs to one of the five
  explicitly approved groups below, the editor cannot delete the row and may
  change ``Lý do nghỉ`` only within that same group.
- Other reasons/types dated today keep the existing canonical edit/delete
  behavior from Phân quyền + Nội quy.
- Future-dated records continue through the existing canonical permission and
  cancellation rules unchanged.

The edit/delete guard patches the canonical server-side helpers, so direct API,
Admin archive wrappers and storage-side deletion use the same boundary. The
Admin create/update validator is patched at the shared Web V2 validation layer,
so every route using ``_validate_and_prepare`` receives the same Admin bypass.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import HTTPException


RELEASE = "operations-leave-guard-2026-09-07-v5"
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


def _install_admin_unrestricted_validator() -> None:
    """Remove leave-policy locks for Admin across all shared Web V2 write routes."""
    import vera_web_v2_api_shared as shared_api

    if getattr(shared_api, "_admin_leave_unrestricted_installed", False):
        return

    original_validator = shared_api.validate_leave_registration_request_live

    def admin_unrestricted_validator(payload, live_df, credentials_df, runtime):
        role = str(payload.get("role", "") or "").strip().lower()
        if role != "admin":
            return original_validator(payload, live_df, credentials_df, runtime)

        # Admin bypasses every Nội quy/registration restriction. We still
        # calculate the informational monthly accumulation from historical data
        # so persisted rows and statistics remain coherent.
        accumulated_month = 0.0
        try:
            source = live_df.copy() if isinstance(live_df, pd.DataFrame) else pd.DataFrame()
            quota_rows = runtime.get("leave_rows_counting_toward_quota")
            normalize_name = runtime.get("normalize_login_name")
            start_date = payload.get("start_date")
            employee = str(payload.get("employee", "") or "").strip()
            if callable(quota_rows):
                source = quota_rows(source)
            if (
                isinstance(source, pd.DataFrame)
                and not source.empty
                and callable(normalize_name)
                and {"Ngày", "Tên nhân viên"}.issubset(source.columns)
                and start_date is not None
            ):
                dates = pd.to_datetime(source["Ngày"], errors="coerce", dayfirst=True)
                names = source["Tên nhân viên"].astype(str).apply(normalize_name)
                mask = (
                    names.eq(normalize_name(employee))
                    & dates.dt.month.eq(start_date.month)
                    & dates.dt.year.eq(start_date.year)
                )
                days = pd.to_numeric(source.loc[mask].get("Số ngày tính", 0), errors="coerce")
                if hasattr(days, "fillna"):
                    days = days.fillna(0.0)
                    accumulated_month = float(days.sum())
        except Exception:
            # Accumulation is display/accounting metadata only; it must never
            # become a new policy lock on an Admin write.
            accumulated_month = 0.0

        return {
            "ok": True,
            "errors": [],
            "warnings": [],
            "accumulated_month": accumulated_month,
            "admin_unrestricted": True,
        }

    shared_api.validate_leave_registration_request_live = admin_unrestricted_validator
    shared_api._admin_leave_unrestricted_installed = True


def _install_admin_reason_catalog(app, api_module) -> None:
    """Make GET /v2/leave/reasons return every catalog reason for Admin."""
    if getattr(app.state, "admin_leave_reason_catalog_unrestricted", False):
        return

    for route in getattr(app, "routes", []):
        if getattr(route, "path", "") != "/v2/leave/reasons" or "GET" not in (getattr(route, "methods", set()) or set()):
            continue
        dependant = getattr(route, "dependant", None)
        original_call = getattr(dependant, "call", None)
        if not callable(original_call):
            continue

        def admin_reason_catalog(date_value, ident):
            if _role(ident) != "admin":
                return original_call(date_value=date_value, ident=ident)

            with api_module._engine_instance().connect() as conn:
                api_module._require_feature(conn, ident, "leave")
                can_view_penalty = api_module._feature_allowed(conn, ident, "employee_penalty_view")
                output = []
                for policy_row in api_module._policy_rows(conn):
                    name = str(api_module._field(policy_row, "Lý do nghỉ", default="") or "").strip()
                    if not name:
                        continue
                    item = api_module._reason_item(conn, name)
                    output.append({
                        "name": item["name"],
                        "leave_type": item["leave_type"],
                        "days": item["days"],
                        "penalty": item["penalty"] if can_view_penalty else None,
                        "requires_manual_penalty": item["requires_manual_penalty"],
                    })
            return {"reasons": output}

        route.endpoint = admin_reason_catalog
        route.dependant.call = admin_reason_catalog
        app.state.admin_leave_reason_catalog_unrestricted = True
        return


def install_letan_leave_guard(app, *, api_module, vn_tz) -> None:
    if getattr(app.state, "letan_leave_guard_installed", False):
        return

    _install_admin_unrestricted_validator()
    _install_admin_reason_catalog(app, api_module)

    original_edit = api_module._validate_edit_permission
    original_delete = api_module._validate_delete_permission
    norm = api_module._norm

    def validate_edit_permission(conn, row: dict, new_reason: str, ident):
        role = _role(ident)
        if role not in EDITOR_ROLES:
            # Includes Admin: the canonical helper already bypasses role/day/
            # timing restrictions for Admin before consulting the catalog rule.
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
            # Lễ tân rule and now shared with Quản lý. The replacement reason
            # must exist in Nội quy, but editor-role/day/timing checks do not
            # block switching among the three reasons of the same group.
            item = api_module._reason_item(conn, new_reason)
            return item, True

        # Future-dated rows preserve feature flags, notice/cancellation period,
        # registration rules and all other canonical behavior.
        return original_edit(conn, row, new_reason, ident)

    def validate_delete_permission(conn, row: dict, ident) -> None:
        role = _role(ident)
        if role not in EDITOR_ROLES:
            # Includes Admin: canonical delete already returns immediately.
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
            "admin": "unrestricted_leave_add_edit_delete",
            "admin_reason_catalog": "all_reasons_all_dates",
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

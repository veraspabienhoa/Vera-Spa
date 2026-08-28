"""Payroll 3.8 compatibility layer for Web V2.

This module keeps the complete Payroll 3.7 calculation path intact and adds
legacy-compatible per-employee living-expense / Locker overrides.  The existing
/v2/payroll/calculate route is replaced at application startup with a thin
wrapper that delegates to the original calculator first, then applies the
optional employee overrides and recalculates net pay with the canonical 3.7
_net helper.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

import vera_web_v2_payroll as _payroll


PAYROLL_V38_RELEASE = "3.8-payroll-employee-overrides"
LEGACY_CONFIG_WORKSHEET = "CauHinhLuong"
LEGACY_OVERRIDE_KEY = "employee_payroll_overrides_json"
PG_OVERRIDE_KEY = "employee_overrides"


class PayrollEmployeeOverrideUpdate(BaseModel):
    employees: list[str] = Field(min_length=1, max_length=100)
    living_expense: float = Field(ge=0, le=1_000_000_000)
    locker_support: float = Field(ge=0, le=1_000_000_000)


class PayrollEmployeeOverrideReset(BaseModel):
    employees: list[str] = Field(min_length=1, max_length=100)


def _normalize_overrides(raw: Any, norm) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in raw.items():
        if not isinstance(raw_value, dict):
            continue
        name = str(raw_value.get("name") or raw_key or "").strip()
        key = norm(name or raw_key)
        if not key:
            continue
        cleaned[key] = {
            "name": name or str(raw_key).strip(),
            "living": max(0, _payroll._number(raw_value.get("living", 0))),
            "locker": max(0, _payroll._number(raw_value.get("locker", 0))),
        }
    return cleaned


def _saved_overrides(conn, norm) -> tuple[bool, dict[str, dict[str, Any]]]:
    row = conn.execute(text("""
        SELECT value_json
        FROM vera_app_setting
        WHERE category='payroll' AND setting_key=:key
        LIMIT 1
    """), {"key": PG_OVERRIDE_KEY}).first()
    if row is None:
        return False, {}
    return True, _normalize_overrides(row[0], norm)


def _legacy_overrides(google_client, norm) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Read the old CauHinhLuong JSON once during migration.

    Returns (found_key, overrides).  A temporary Google failure returns
    (False, {}) so a later request can retry instead of permanently persisting
    an empty migration result.
    """
    try:
        spreadsheet = google_client().open_by_key(_payroll.LEGACY_SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(LEGACY_CONFIG_WORKSHEET)
        values = worksheet.get_all_values()
    except Exception:
        return False, {}

    for row in values[1:] if values else []:
        if not row or str(row[0] or "").strip() != LEGACY_OVERRIDE_KEY:
            continue
        raw_text = str(row[1] if len(row) > 1 else "{}").strip() or "{}"
        try:
            payload = json.loads(raw_text)
        except Exception:
            payload = {}
        return True, _normalize_overrides(payload, norm)
    return False, {}


def _load_or_bootstrap_overrides(conn, *, google_client, norm, actor: str) -> tuple[dict[str, dict[str, Any]], int]:
    exists, overrides = _saved_overrides(conn, norm)
    if exists:
        return overrides, 0

    found_legacy, legacy = _legacy_overrides(google_client, norm)
    if not found_legacy:
        return {}, 0

    _payroll._put_setting(conn, PG_OVERRIDE_KEY, legacy, actor or "payroll-v38-migration")
    return legacy, len(legacy)


def _eligible_employees(conn) -> list[dict[str, str]]:
    return [dict(row) for row in conn.execute(text("""
        SELECT username,
               COALESCE(full_name,'') AS full_name,
               lower(COALESCE(role,'')) AS role
        FROM employees
        WHERE lower(COALESCE(role,'')) IN ('nhanvien','leader')
        ORDER BY COALESCE(stt,2147483647), username
    """)).mappings().all()]


def _override_payload(conn, overrides: dict[str, dict[str, Any]], norm) -> dict[str, Any]:
    cfg = _payroll._config(conn)
    employees = []
    for row in _eligible_employees(conn):
        username = str(row.get("username") or "").strip()
        key = norm(username)
        override = overrides.get(key)
        employees.append({
            "employee_name": username,
            "full_name": str(row.get("full_name") or "").strip(),
            "role": str(row.get("role") or "").strip(),
            "has_override": override is not None,
            "living_expense": (
                int(override["living"]) if override is not None else int(cfg["default_living_expense"])
            ),
            "locker_support": (
                int(override["locker"]) if override is not None else int(cfg["default_locker_support"])
            ),
        })
    override_rows = sorted([
        {
            "employee_name": value.get("name") or key,
            "living_expense": int(value.get("living", 0)),
            "locker_support": int(value.get("locker", 0)),
        }
        for key, value in overrides.items()
    ], key=lambda item: norm(item["employee_name"]))
    return {"config": cfg, "employees": employees, "overrides": override_rows}


def _canonical_names(conn, requested: list[str], norm) -> list[str]:
    catalog = _eligible_employees(conn)
    by_key = {norm(row.get("username")): str(row.get("username") or "").strip() for row in catalog}
    output: list[str] = []
    missing: list[str] = []
    for raw in requested:
        name = str(raw or "").strip()
        key = norm(name)
        canonical = by_key.get(key)
        if not key or not canonical:
            missing.append(name or "(trống)")
            continue
        if canonical not in output:
            output.append(canonical)
    if missing:
        raise HTTPException(400, "Tên nhân viên không khớp Nhân viên/Leader: " + ", ".join(missing[:10]))
    if not output:
        raise HTTPException(400, "Chưa chọn Nhân viên/Leader cần cấu hình mức riêng.")
    return output


def _apply_overrides_to_calculation(result: dict[str, Any], overrides: dict[str, dict[str, Any]], norm) -> dict[str, Any]:
    rows = []
    applied_names: list[str] = []
    for source_row in list(result.get("rows") or []):
        row = dict(source_row)
        username = str(row.get("Tên Hệ thống") or "").strip()
        override = overrides.get(norm(username))
        if override is not None:
            row["Chi Phí Sinh Hoạt"] = int(override.get("living", 0))
            row["Tiền hỗ trợ Locker"] = int(override.get("locker", 0))
            # Canonical 3.7 behavior remains authoritative, including the rule
            # that salary=0 clears both deductions before net pay is computed.
            row = _payroll._net(row)
            applied_names.append(username)
        rows.append(row)
    result = dict(result)
    result["rows"] = rows
    result["employee_overrides_applied"] = len(applied_names)
    result["employee_override_names"] = applied_names
    result["release"] = PAYROLL_V38_RELEASE
    return result


def install_payroll_v38_routes(
    app,
    *,
    engine_instance,
    current_identity,
    require_feature,
    norm,
    identity_type,
    google_client,
) -> None:
    """Install Payroll 3.8 routes once and wrap the 3.7 calculator."""
    if getattr(app.state, "payroll_v38_installed", False):
        return

    original_route = None
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == "/v2/payroll/calculate" and "POST" in methods:
            original_route = route
            break
    if original_route is None:
        raise RuntimeError("Payroll 3.8 cannot find the canonical Payroll 3.7 calculate route.")
    original_calculate = original_route.endpoint
    app.router.routes.remove(original_route)

    @app.get("/v2/payroll-v38/health")
    def payroll_v38_health():
        return {"ok": True, "release": PAYROLL_V38_RELEASE}

    @app.get("/v2/payroll-v38/employee-overrides")
    def get_employee_overrides(ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_config_edit")
            overrides, imported = _load_or_bootstrap_overrides(
                conn,
                google_client=google_client,
                norm=norm,
                actor=ident.employee_username,
            )
            payload = _override_payload(conn, overrides, norm)
        payload.update({
            "release": PAYROLL_V38_RELEASE,
            "legacy_imported_count": imported,
        })
        return payload

    @app.put("/v2/payroll-v38/employee-overrides")
    def save_employee_overrides(
        body: PayrollEmployeeOverrideUpdate,
        ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_config_edit")
            canonical_names = _canonical_names(conn, body.employees, norm)
            overrides, _ = _load_or_bootstrap_overrides(
                conn,
                google_client=google_client,
                norm=norm,
                actor=ident.employee_username,
            )
            living = max(0, _payroll._number(body.living_expense))
            locker = max(0, _payroll._number(body.locker_support))
            for name in canonical_names:
                overrides[norm(name)] = {"name": name, "living": living, "locker": locker}
            _payroll._put_setting(conn, PG_OVERRIDE_KEY, overrides, ident.employee_username)
            payload = _override_payload(conn, overrides, norm)
        payload.update({
            "ok": True,
            "release": PAYROLL_V38_RELEASE,
            "message": f"Đã áp dụng mức riêng cho {len(canonical_names)} Nhân viên/Leader.",
        })
        return payload

    @app.post("/v2/payroll-v38/employee-overrides/reset")
    def reset_employee_overrides(
        body: PayrollEmployeeOverrideReset,
        ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_config_edit")
            canonical_names = _canonical_names(conn, body.employees, norm)
            overrides, _ = _load_or_bootstrap_overrides(
                conn,
                google_client=google_client,
                norm=norm,
                actor=ident.employee_username,
            )
            removed = 0
            for name in canonical_names:
                if overrides.pop(norm(name), None) is not None:
                    removed += 1
            _payroll._put_setting(conn, PG_OVERRIDE_KEY, overrides, ident.employee_username)
            payload = _override_payload(conn, overrides, norm)
        payload.update({
            "ok": True,
            "release": PAYROLL_V38_RELEASE,
            "message": f"Đã đưa {len(canonical_names)} Nhân viên/Leader về mức mặc định; xóa {removed} mức riêng.",
        })
        return payload

    @app.post("/v2/payroll/calculate", name=getattr(original_route, "name", "calculate_payroll"))
    async def calculate_payroll_v38(
        month: str = Query(...),
        period_no: int = Query(..., ge=1, le=2),
        payload: bytes = Body(
            ...,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ident: identity_type = Depends(current_identity),
    ):
        # All source validation, Tip matching, accumulation, obligations and
        # default deductions are still calculated by Payroll 3.7 first.
        result = await original_calculate(
            month=month,
            period_no=period_no,
            payload=payload,
            ident=ident,
        )
        with engine_instance().begin() as conn:
            overrides, _ = _load_or_bootstrap_overrides(
                conn,
                google_client=google_client,
                norm=norm,
                actor=ident.employee_username,
            )
        return _apply_overrides_to_calculation(result, overrides, norm)

    app.state.payroll_v38_installed = True
    app.state.payroll_release = PAYROLL_V38_RELEASE

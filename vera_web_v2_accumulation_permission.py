"""Separate personal accumulation access from full payroll permissions.

Admin can grant ``accumulation_view`` without granting payroll history or any
payroll-management feature.  This module also owns Admin-only accumulation
adjustments so historical payroll cleanup never changes an employee's current
accumulation balance.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from typing import Any, Callable

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

import vera_web_v2_permissions as permissions
from vera_web_v2_payroll_timesoft_upload_fix import install_payroll_timesoft_upload_fix


# The API V3.8 imports this module during startup after the canonical Payroll
# routes have been registered.  Patching the module global here means the
# existing calculate route automatically uses the resilient TimeSoft reader.
install_payroll_timesoft_upload_fix()


RELEASE = "accumulation-permission-2026-09-01.2"
ACCUMULATION_FEATURE = "accumulation_view"
ACCUMULATION_LABEL = "Xem Tiền tích lũy cá nhân"
_TRACKED_ROLES = ("leader", "nhanvien")
_ADJUSTMENT_KEY = "accumulation_manual_adjustments"


class AccumulationAdd(BaseModel):
    employee_name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000_000)
    note: str = Field(default="Admin cộng thêm tiền tích lũy", max_length=500)


class AccumulationSet(BaseModel):
    employee_name: str = Field(min_length=1, max_length=200)
    paid_total: float = Field(ge=0, le=1_000_000_000)
    note: str = Field(default="Admin sửa tổng tiền tích lũy", max_length=500)


def _remove_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            app.router.routes.remove(route)
            return route.endpoint
    raise RuntimeError(f"Cannot find {wanted} {path} to wrap")


def _install_permission_catalog(api_module=None) -> None:
    group = permissions.FEATURE_GROUPS.setdefault("Tiền tích lũy", {})
    group[ACCUMULATION_FEATURE] = ACCUMULATION_LABEL
    permissions.FEATURES[ACCUMULATION_FEATURE] = ACCUMULATION_LABEL

    permissions.DEFAULT_ROLE_FEATURES.setdefault("admin", set()).add(ACCUMULATION_FEATURE)
    permissions.EMPLOYEE.discard("payroll_history")
    for role in _TRACKED_ROLES:
        defaults = permissions.DEFAULT_ROLE_FEATURES.setdefault(role, set())
        defaults.discard("payroll_history")
        defaults.discard(ACCUMULATION_FEATURE)

    if api_module is not None:
        features = getattr(api_module, "WEB_V2_FEATURES", None)
        if isinstance(features, dict):
            features[ACCUMULATION_FEATURE] = ACCUMULATION_LABEL
        defaults = getattr(api_module, "WEB_V2_DEFAULT_FEATURES", None)
        if isinstance(defaults, dict):
            defaults.setdefault("admin", set()).add(ACCUMULATION_FEATURE)
            for role in _TRACKED_ROLES:
                role_defaults = defaults.setdefault(role, set())
                role_defaults.discard("payroll_history")
                role_defaults.discard(ACCUMULATION_FEATURE)


def _require_admin(ident) -> None:
    if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
        raise HTTPException(403, "Chỉ Admin được thêm, sửa hoặc xóa tiền tích lũy.")


def _load_adjustments(conn) -> list[dict[str, Any]]:
    value = conn.execute(text("""
        SELECT value_json
        FROM vera_app_setting
        WHERE category='payroll' AND setting_key=:key
        LIMIT 1
    """), {"key": _ADJUSTMENT_KEY}).scalar_one_or_none()
    return [dict(item) for item in (value or []) if isinstance(item, dict)]


def _save_adjustments(conn, rows: list[dict[str, Any]], actor: str) -> None:
    conn.execute(text("""
        INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
        VALUES ('payroll',:key,CAST(:value AS jsonb),'web_v2',:actor,1,NOW(),NOW())
        ON CONFLICT(category,setting_key) DO UPDATE SET
          value_json=EXCLUDED.value_json,
          source='web_v2',
          updated_by=EXCLUDED.updated_by,
          revision=vera_app_setting.revision+1,
          updated_at=NOW()
    """), {
        "key": _ADJUSTMENT_KEY,
        "value": json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
        "actor": actor,
    })


def _employee(conn, employee_name: str, norm) -> dict[str, str]:
    requested = norm(employee_name)
    rows = conn.execute(text("""
        SELECT username, COALESCE(full_name,'') AS full_name, lower(COALESCE(role,'')) AS role
        FROM employees
        WHERE COALESCE(payload->>'__deleted','false') <> 'true'
          AND lower(COALESCE(role,'')) IN ('leader','nhanvien')
    """)).mappings().all()
    for row in rows:
        if requested in {norm(row.get("username")), norm(row.get("full_name"))}:
            return {
                "username": str(row.get("username") or "").strip(),
                "full_name": str(row.get("full_name") or "").strip(),
                "role": str(row.get("role") or "").strip(),
            }
    raise HTTPException(404, "Không tìm thấy Leader/Nhân viên cần điều chỉnh Tích lũy.")


def _source_paid(conn, employee: dict[str, str], norm) -> int:
    payload = conn.execute(text("""
        SELECT payload FROM vera_dataset_cache
        WHERE dataset_key='tichluy'
        LIMIT 1
    """)).scalar_one_or_none()
    keys = {norm(employee.get("username")), norm(employee.get("full_name"))} - {""}
    for item in (payload or []):
        if not isinstance(item, dict) or norm(item.get("Tên nhân viên")) not in keys:
            continue
        raw = str(item.get("Đã tích lũy") or "").strip()
        negative = raw.startswith("-")
        digits = "".join(ch for ch in raw if ch.isdigit())
        return max(0, (-1 if negative else 1) * int(digits or 0))
    return 0


def _manual_delta(rows: list[dict[str, Any]], employee: dict[str, str], norm) -> int:
    keys = {norm(employee.get("username")), norm(employee.get("full_name"))} - {""}
    total = 0
    for item in rows:
        if norm(item.get("employee_name")) not in keys:
            continue
        try:
            total += int(round(float(item.get("delta") or 0)))
        except Exception:
            continue
    return total


def _append_adjustment(conn, *, employee: dict[str, str], delta: int, action: str, note: str, actor: str, norm) -> dict[str, Any]:
    rows = _load_adjustments(conn)
    source_paid = _source_paid(conn, employee, norm)
    current = max(0, source_paid + _manual_delta(rows, employee, norm))
    if delta == 0:
        return {"employee_name": employee["username"], "paid_total": current, "delta": 0}
    record = {
        "id": str(uuid.uuid4()),
        "employee_name": employee["username"],
        "delta": int(delta),
        "action": action,
        "note": str(note or "").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": actor,
    }
    rows.append(record)
    _save_adjustments(conn, rows, actor)
    return {
        "employee_name": employee["username"],
        "paid_total": max(0, current + int(delta)),
        "delta": int(delta),
        "adjustment_id": record["id"],
    }


def _apply_adjustments(payload: dict[str, Any], adjustments: list[dict[str, Any]], norm) -> dict[str, Any]:
    result = dict(payload or {})
    employees = []
    for source in list(result.get("employees") or []):
        row = dict(source)
        keys = {norm(row.get("employee_name")), norm(row.get("full_name"))} - {""}
        delta = 0
        for item in adjustments:
            if norm(item.get("employee_name")) not in keys:
                continue
            try:
                delta += int(round(float(item.get("delta") or 0)))
            except Exception:
                pass
        base_paid = int(round(float(row.get("paid_total") or 0)))
        paid = max(0, base_paid + delta)
        target = max(0, int(round(float(row.get("target") or 0))))
        remaining = max(0, target - paid)
        row.update({
            "base_paid_total": base_paid,
            "manual_adjustment_total": delta,
            "paid_total": paid,
            "remaining": remaining,
            "completed": target > 0 and remaining == 0,
        })
        employees.append(row)
    result["employees"] = employees
    result["totals"] = {
        "employee_count": len(employees),
        "paid_total": sum(int(row.get("paid_total") or 0) for row in employees),
        "remaining_total": sum(int(row.get("remaining") or 0) for row in employees),
        "obligation_total": sum(int(row.get("obligation_total") or 0) for row in employees),
        "obligation_count": sum(int(row.get("obligation_count") or 0) for row in employees),
    }
    result["accumulation_adjustment_release"] = RELEASE
    return result


def install_accumulation_permission(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature,
    identity_type,
    api_module=None,
) -> None:
    """Install permission catalog, personal API guard and Admin adjustments."""
    if getattr(app.state, "accumulation_permission_installed", False):
        return

    _install_permission_catalog(api_module=api_module)
    norm = getattr(api_module, "_norm", lambda value: str(value or "").strip().casefold())

    original_me = _remove_route(app, "/v2/me", "GET")
    original_tracking = _remove_route(app, "/v2/payroll/personal-tracking", "GET")

    # Legacy BangLuong import is retired.  It must not be able to repopulate
    # the old Web V2 history after Admin cleared it.
    try:
        _remove_route(app, "/v2/payroll/history/sync-legacy", "POST")
    except RuntimeError:
        pass

    @app.get("/v2/me")
    def me_with_accumulation_permission(ident: identity_type = Depends(current_identity)):
        payload = dict(original_me(ident=ident) or {})
        feature_map = dict(payload.get("permissions") or {})
        accumulation_allowed = bool(feature_map.get(ACCUMULATION_FEATURE))
        actual_payroll_history = bool(feature_map.get("payroll_history"))
        if accumulation_allowed and not actual_payroll_history:
            feature_map["payroll_history"] = True
            payload["payroll_menu_mode"] = "accumulation_only"
        payload["permissions"] = feature_map
        payload["accumulation_permission_release"] = RELEASE
        return payload

    @app.get("/v2/payroll/personal-tracking")
    def personal_accumulation_guard(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, ACCUMULATION_FEATURE)
            adjustments = _load_adjustments(conn)
        return _apply_adjustments(original_tracking(ident=ident), adjustments, norm)

    @app.post("/v2/payroll/accumulation-adjustments/add")
    def add_accumulation(body: AccumulationAdd, ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        with engine_instance().begin() as conn:
            employee = _employee(conn, body.employee_name, norm)
            result = _append_adjustment(
                conn,
                employee=employee,
                delta=int(round(body.amount)),
                action="add",
                note=body.note,
                actor=ident.employee_username,
                norm=norm,
            )
        return {"ok": True, **result, "message": f"Đã cộng thêm Tích lũy cho {result['employee_name']}."}

    @app.put("/v2/payroll/accumulation-adjustments/set")
    def set_accumulation(body: AccumulationSet, ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        with engine_instance().begin() as conn:
            employee = _employee(conn, body.employee_name, norm)
            rows = _load_adjustments(conn)
            current = max(0, _source_paid(conn, employee, norm) + _manual_delta(rows, employee, norm))
            desired = max(0, int(round(body.paid_total)))
            result = _append_adjustment(
                conn,
                employee=employee,
                delta=desired - current,
                action="set",
                note=body.note,
                actor=ident.employee_username,
                norm=norm,
            )
        return {"ok": True, **result, "message": f"Đã sửa tổng Tích lũy của {result['employee_name']} thành {desired:,}đ."}

    @app.delete("/v2/payroll/accumulation-adjustments")
    def delete_accumulation(employee_name: str = Query(..., min_length=1, max_length=200), ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        with engine_instance().begin() as conn:
            employee = _employee(conn, employee_name, norm)
            rows = _load_adjustments(conn)
            current = max(0, _source_paid(conn, employee, norm) + _manual_delta(rows, employee, norm))
            result = _append_adjustment(
                conn,
                employee=employee,
                delta=-current,
                action="clear",
                note="Admin xóa số tiền Tích lũy đã đóng về 0",
                actor=ident.employee_username,
                norm=norm,
            )
        return {"ok": True, **result, "message": f"Đã đưa Tích lũy đã đóng của {result['employee_name']} về 0đ."}

    @app.post("/v2/payroll/history/sync-legacy")
    def retired_legacy_payroll_sync(ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        raise HTTPException(410, "Lịch sử bảng lương cũ đã được xóa khỏi Web V2 và không còn đồng bộ lại.")

    app.state.accumulation_permission_installed = True
    app.state.accumulation_permission_release = RELEASE

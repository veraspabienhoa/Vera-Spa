"""Persistent salary-advance ledger for Department Payroll.

Each advance is kept as a separate transaction so one employee can receive
multiple advances in the same month. Completing payroll marks pending advances
for that payroll month as settled while preserving the ledger history.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
import uuid

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

import vera_web_v2_department_payroll as department_payroll
import vera_web_v2_payroll as payroll


RELEASE = "department-salary-advance-ledger-2026-09-07-v1"
SETTING_KEY = "department_salary_advance_ledger"


class SalaryAdvanceCreate(BaseModel):
    employee_username: str = Field(min_length=1, max_length=200)
    advance_date: date
    amount: float = Field(gt=0, le=1_000_000_000)
    note: str = Field(default="", max_length=1000)


class SalaryAdvanceUpdate(SalaryAdvanceCreate):
    pass


class SalaryAdvanceSettle(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    history_id: str = Field(default="", max_length=120)
    employees: list[str] = Field(default_factory=list, max_length=1200)


def _money(value: Any) -> int:
    return max(0, payroll._number(value))


def _clean_entry(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    entry_id = str(item.get("id") or "").strip()
    username = str(item.get("employee_username") or "").strip()
    advance_date = str(item.get("advance_date") or "").strip()
    if not entry_id or not username or not advance_date:
        return None
    return {
        "id": entry_id,
        "employee_username": username,
        "employee_name": str(item.get("employee_name") or username).strip(),
        "department": str(item.get("department") or "").strip().lower(),
        "department_label": str(item.get("department_label") or "").strip(),
        "advance_date": advance_date,
        "amount": _money(item.get("amount")),
        "note": str(item.get("note") or "").strip()[:1000],
        "created_at": str(item.get("created_at") or ""),
        "created_by": str(item.get("created_by") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "updated_by": str(item.get("updated_by") or ""),
        "settled_at": str(item.get("settled_at") or ""),
        "settled_by": str(item.get("settled_by") or ""),
        "payroll_history_id": str(item.get("payroll_history_id") or ""),
        "payroll_month": str(item.get("payroll_month") or ""),
    }


def _entries(conn) -> list[dict[str, Any]]:
    raw = payroll._setting(conn, SETTING_KEY, [])
    rows = []
    for item in raw if isinstance(raw, list) else []:
        cleaned = _clean_entry(item)
        if cleaned:
            rows.append(cleaned)
    return rows


def _save(conn, rows: list[dict[str, Any]], actor: str) -> None:
    payroll._put_setting(conn, SETTING_KEY, rows[-5000:], actor)


def _catalog(conn) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("employee_username") or "").strip().casefold(): item
        for item in department_payroll._salary_employee_catalog(conn)
    }


def _employee(conn, username: str) -> dict[str, Any]:
    key = str(username or "").strip().casefold()
    employee = _catalog(conn).get(key)
    if not employee:
        raise HTTPException(400, "Nhân viên không thuộc Quản lý, Locker, Lễ tân hoặc Tạp vụ đang làm việc.")
    return employee


def _month_rows(rows: list[dict[str, Any]], month: str) -> list[dict[str, Any]]:
    department_payroll._month_range(month)
    prefix = f"{month}-"
    return [item for item in rows if str(item.get("advance_date") or "").startswith(prefix)]


def _summary(rows: list[dict[str, Any]], month: str) -> dict[str, Any]:
    items = _month_rows(rows, month)
    by_employee: dict[str, dict[str, Any]] = {}
    total = pending = settled = 0
    for item in items:
        amount = _money(item.get("amount"))
        total += amount
        is_settled = bool(item.get("settled_at"))
        if is_settled:
            settled += amount
        else:
            pending += amount
        username = str(item.get("employee_username") or "")
        bucket = by_employee.setdefault(username, {
            "employee_username": username,
            "employee_name": item.get("employee_name") or username,
            "department": item.get("department") or "",
            "department_label": item.get("department_label") or "",
            "payroll_total": 0,
            "pending_total": 0,
            "settled_total": 0,
            "count": 0,
        })
        bucket["payroll_total"] += amount
        bucket["count"] += 1
        bucket["settled_total" if is_settled else "pending_total"] += amount
    return {
        "month": month,
        "month_total": total,
        "pending_total": pending,
        "settled_total": settled,
        "by_employee": by_employee,
    }


def _public_items(rows: list[dict[str, Any]], month: str) -> list[dict[str, Any]]:
    items = _month_rows(rows, month)
    return sorted(
        [dict(item, status="settled" if item.get("settled_at") else "pending") for item in items],
        key=lambda item: (str(item.get("advance_date") or ""), str(item.get("created_at") or "")),
        reverse=True,
    )


def install_salary_advance_routes(app, *, engine_instance, current_identity, require_feature, identity_type) -> None:
    if getattr(app.state, "salary_advance_routes_installed", False):
        return

    @app.get("/v2/department-payroll/advances")
    def get_advances(month: str = Query(...), ident: identity_type = Depends(current_identity)):
        department_payroll._month_range(month)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            rows = _entries(conn)
            catalog = department_payroll._salary_employee_catalog(conn)
        return {
            "ok": True,
            "release": RELEASE,
            "items": _public_items(rows, month),
            "summary": _summary(rows, month),
            "employee_catalog": catalog,
        }

    @app.post("/v2/department-payroll/advances")
    def create_advance(body: SalaryAdvanceCreate, ident: identity_type = Depends(current_identity)):
        amount = _money(body.amount)
        if amount <= 0:
            raise HTTPException(400, "Số tiền ứng phải lớn hơn 0.")
        now = datetime.now(department_payroll.VN_TZ).isoformat()
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            employee = _employee(conn, body.employee_username)
            rows = _entries(conn)
            rows.append({
                "id": str(uuid.uuid4()),
                "employee_username": employee["employee_username"],
                "employee_name": employee["employee_name"],
                "department": employee["department"],
                "department_label": employee["department_label"],
                "advance_date": body.advance_date.isoformat(),
                "amount": amount,
                "note": str(body.note or "").strip()[:1000],
                "created_at": now,
                "created_by": ident.employee_username,
                "updated_at": "",
                "updated_by": "",
                "settled_at": "",
                "settled_by": "",
                "payroll_history_id": "",
                "payroll_month": "",
            })
            _save(conn, rows, ident.employee_username)
            month = body.advance_date.strftime("%Y-%m")
        return {
            "ok": True,
            "items": _public_items(rows, month),
            "summary": _summary(rows, month),
            "message": f"Đã ghi nhận ứng lương {employee['employee_name']} ngày {body.advance_date.strftime('%d/%m/%Y')}.",
        }

    @app.put("/v2/department-payroll/advances/{advance_id}")
    def update_advance(advance_id: str, body: SalaryAdvanceUpdate, ident: identity_type = Depends(current_identity)):
        amount = _money(body.amount)
        if amount <= 0:
            raise HTTPException(400, "Số tiền ứng phải lớn hơn 0.")
        now = datetime.now(department_payroll.VN_TZ).isoformat()
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            employee = _employee(conn, body.employee_username)
            rows = _entries(conn)
            target = next((item for item in rows if str(item.get("id")) == str(advance_id)), None)
            if not target:
                raise HTTPException(404, "Không tìm thấy khoản ứng lương.")
            if target.get("settled_at"):
                raise HTTPException(409, "Khoản ứng đã đưa vào bảng lương nên không thể sửa. Hãy điều chỉnh bằng một giao dịch mới.")
            target.update({
                "employee_username": employee["employee_username"],
                "employee_name": employee["employee_name"],
                "department": employee["department"],
                "department_label": employee["department_label"],
                "advance_date": body.advance_date.isoformat(),
                "amount": amount,
                "note": str(body.note or "").strip()[:1000],
                "updated_at": now,
                "updated_by": ident.employee_username,
            })
            _save(conn, rows, ident.employee_username)
            month = body.advance_date.strftime("%Y-%m")
        return {"ok": True, "items": _public_items(rows, month), "summary": _summary(rows, month), "message": "Đã cập nhật khoản ứng lương."}

    @app.delete("/v2/department-payroll/advances/{advance_id}")
    def delete_advance(advance_id: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            rows = _entries(conn)
            target = next((item for item in rows if str(item.get("id")) == str(advance_id)), None)
            if not target:
                raise HTTPException(404, "Không tìm thấy khoản ứng lương.")
            if target.get("settled_at"):
                raise HTTPException(409, "Khoản ứng đã đưa vào bảng lương nên không thể xóa.")
            month = str(target.get("advance_date") or "")[:7]
            rows = [item for item in rows if str(item.get("id")) != str(advance_id)]
            _save(conn, rows, ident.employee_username)
        return {"ok": True, "items": _public_items(rows, month), "summary": _summary(rows, month), "message": "Đã xóa khoản ứng lương."}

    @app.post("/v2/department-payroll/advances/settle")
    def settle_advances(body: SalaryAdvanceSettle, ident: identity_type = Depends(current_identity)):
        department_payroll._month_range(body.month)
        allowed = {str(item or "").strip().casefold() for item in body.employees if str(item or "").strip()}
        now = datetime.now(department_payroll.VN_TZ).isoformat()
        settled_count = 0
        settled_amount = 0
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            rows = _entries(conn)
            for item in rows:
                if not str(item.get("advance_date") or "").startswith(f"{body.month}-"):
                    continue
                if item.get("settled_at"):
                    continue
                if allowed and str(item.get("employee_username") or "").casefold() not in allowed:
                    continue
                amount = _money(item.get("amount"))
                item.update({
                    "settled_at": now,
                    "settled_by": ident.employee_username,
                    "payroll_history_id": str(body.history_id or ""),
                    "payroll_month": body.month,
                })
                settled_count += 1
                settled_amount += amount
            if settled_count:
                _save(conn, rows, ident.employee_username)
        return {
            "ok": True,
            "settled_count": settled_count,
            "settled_amount": settled_amount,
            "summary": _summary(rows, body.month),
            "message": f"Đã trừ {settled_count} khoản ứng lương vào bảng lương tháng {body.month}.",
        }

    @app.get("/v2/department-payroll/advances/health")
    def salary_advance_health():
        return {"ok": True, "release": RELEASE, "storage": "PostgreSQL vera_app_setting"}

    app.state.salary_advance_routes_installed = True

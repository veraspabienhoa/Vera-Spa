"""Personal/Admin payroll accumulation tracking for VERA SPA Web V2.

This module is read-only. It derives each employee's accumulation payments from
saved payroll history, combines them with the canonical TichLuy snapshot, and
shows only open violation obligations. Non-admin identities are always scoped
to their own employee account; Admin can review everybody.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import re
from typing import Any, Callable

from fastapi import Depends
from sqlalchemy import text

import vera_web_v2_permissions as permissions


RELEASE = "payroll-personal-tracking-2026-08-31-v1"
_EMPLOYEE_PAYROLL_ROLES = ("nhanvien", "leader", "locker", "tapvu")
_DEFAULT_ACCUMULATION_TARGET = 5_000_000


def _number(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    raw = str(value or "").strip()
    if not raw:
        return 0
    negative = raw.startswith("-")
    digits = re.sub(r"[^0-9]", "", raw)
    return (-1 if negative else 1) * int(digits or 0)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _date_label(value: Any) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else str(value or "").strip()


def _dataset(conn, dataset_key: str) -> list[dict[str, Any]]:
    payload = conn.execute(text("""
        SELECT payload FROM vera_dataset_cache
        WHERE dataset_key=:dataset_key
        LIMIT 1
    """), {"dataset_key": dataset_key}).scalar_one_or_none()
    return [dict(item) for item in (payload or []) if isinstance(item, dict)]


def _setting(conn, key: str) -> list[dict[str, Any]]:
    value = conn.execute(text("""
        SELECT value_json FROM vera_app_setting
        WHERE category='payroll' AND setting_key=:key
        LIMIT 1
    """), {"key": key}).scalar_one_or_none()
    return [dict(item) for item in (value or []) if isinstance(item, dict)]


def _open_status(value: Any, norm: Callable[[Any], str]) -> bool:
    return norm(value or "Chưa hoàn thành") in {"", "chua hoan thanh"}


def _obligation_rows(conn, norm: Callable[[Any], str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    sources = [("web_v2", _setting(conn, "violation_obligations")), ("legacy", _dataset(conn, "violation_debt"))]
    for source, rows in sources:
        for item in rows:
            status = item.get("status") or item.get("Trạng thái") or "Chưa hoàn thành"
            if not _open_status(status, norm):
                continue
            employee_name = str(item.get("employee_name") or item.get("Tên nhân viên") or "").strip()
            amount = max(0, _number(item.get("amount") or item.get("Số tiền")))
            if not employee_name or amount <= 0:
                continue
            period_start = _date_label(item.get("period_start") or item.get("Kỳ phát sinh từ"))
            period_end = _date_label(item.get("period_end") or item.get("Kỳ phát sinh đến"))
            due_from = _date_label(item.get("due_from") or item.get("Bắt đầu trừ từ"))
            content = str(item.get("content") or item.get("Nội dung") or "Chưa hoàn thành nghĩa vụ Vi phạm").strip()
            source_id = str(item.get("id") or item.get("Mã nguồn") or "").strip()
            dedupe = (norm(employee_name), amount, period_start, period_end, due_from, norm(content), source_id or source)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            output.append({
                "employee_name": employee_name,
                "amount": amount,
                "period_start": period_start,
                "period_end": period_end,
                "due_from": due_from,
                "content": content,
                "status": str(status or "Chưa hoàn thành").strip(),
                "source": source,
            })
    output.sort(key=lambda row: (_parse_date(row.get("due_from")) or date.max, norm(row.get("employee_name"))))
    return output


def _period_rows(records: list[dict[str, Any]], employee_keys: set[str], norm: Callable[[Any], str]) -> list[dict[str, Any]]:
    by_period: dict[tuple[str, str], dict[str, Any]] = {}
    for item in records:
        name_key = norm(item.get("Tên Hệ thống"))
        full_key = norm(item.get("Họ và tên"))
        if not ({name_key, full_key} & employee_keys):
            continue
        batch = str(item.get("Mã bản lưu") or "").strip()
        start = _date_label(item.get("Từ ngày"))
        end = _date_label(item.get("Đến ngày"))
        key = (batch or f"{start}|{end}", name_key or full_key)
        row = {
            "batch": batch or (f"{start} – {end}" if start or end else "Kỳ lương"),
            "start": start,
            "end": end,
            "saved_date": _date_label(item.get("Ngày lưu")),
            "contribution": max(0, _number(item.get("Tích lũy"))),
            "refund": max(0, _number(item.get("Hoàn trả tiền tích lũy"))),
            "salary": max(0, _number(item.get("Tiền Lương"))),
            "net": _number(item.get("Số tiền thực nhận")),
        }
        previous = by_period.get(key)
        if previous is None or row["contribution"] >= previous["contribution"]:
            by_period[key] = row
    rows = list(by_period.values())
    rows.sort(key=lambda row: (_parse_date(row.get("start")) or date.min, row.get("batch") or ""), reverse=True)
    return rows


def _tichluy_detail_periods(item: dict[str, Any]) -> dict[str, int]:
    raw = item.get("Chi tiết các kỳ")
    if isinstance(raw, dict):
        source = raw
    else:
        try:
            source = json.loads(str(raw or "{}"))
        except Exception:
            source = {}
    return {str(key): max(0, _number(value)) for key, value in source.items()} if isinstance(source, dict) else {}


def _merge_tichluy_periods(periods: list[dict[str, Any]], tichluy_item: dict[str, Any]) -> list[dict[str, Any]]:
    existing = {(row.get("start"), row.get("end")): row for row in periods}
    for key, amount in _tichluy_detail_periods(tichluy_item).items():
        parts = key.split("|", 1)
        if len(parts) != 2:
            continue
        start, end = (_date_label(parts[0]), _date_label(parts[1]))
        pair = (start, end)
        if pair in existing:
            if existing[pair]["contribution"] <= 0:
                existing[pair]["contribution"] = amount
            continue
        row = {
            "batch": f"{start} – {end}", "start": start, "end": end, "saved_date": "",
            "contribution": amount, "refund": 0, "salary": 0, "net": 0,
        }
        periods.append(row)
        existing[pair] = row
    periods.sort(key=lambda row: (_parse_date(row.get("start")) or date.min, row.get("batch") or ""), reverse=True)
    return periods


def install_payroll_personal_defaults(api_module=None) -> None:
    """Expose the existing payroll menu to employee-like roles, read-only.

    PayrollPageV38 treats payroll_history-only accounts as personal-view users,
    while privileged payroll permissions continue to open the full admin/editor UI.
    """
    for role in _EMPLOYEE_PAYROLL_ROLES:
        permissions.DEFAULT_ROLE_FEATURES.setdefault(role, set()).add("payroll_history")
    permissions.EMPLOYEE.add("payroll_history")
    if api_module is not None:
        defaults = getattr(api_module, "WEB_V2_DEFAULT_FEATURES", None)
        if isinstance(defaults, dict):
            for role in _EMPLOYEE_PAYROLL_ROLES:
                defaults.setdefault(role, set()).add("payroll_history")


def install_payroll_personal_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    identity_type,
    norm: Callable[[Any], str],
) -> None:
    if getattr(app.state, "payroll_personal_tracking_installed", False):
        return

    @app.get("/v2/payroll/personal-tracking")
    def payroll_personal_tracking(ident: identity_type = Depends(current_identity)):
        is_admin = str(getattr(ident, "role", "") or "").strip().lower() == "admin"
        viewer_key = norm(getattr(ident, "employee_username", ""))
        viewer_full_key = norm(getattr(ident, "full_name", ""))

        with engine_instance().connect() as conn:
            employees = [dict(row) for row in conn.execute(text("""
                SELECT username, COALESCE(full_name,'') AS full_name,
                       lower(COALESCE(role,'')) AS role,
                       COALESCE(payload->>'Trạng thái làm việc', payload->>'employment_status', 'Đang làm việc') AS employment_status
                FROM employees
                WHERE COALESCE(payload->>'__deleted','false') <> 'true'
                ORDER BY lower(COALESCE(role,'')), lower(username)
            """)).mappings().all()]
            history = _dataset(conn, "payroll_history")
            tichluy_rows = _dataset(conn, "tichluy")
            obligations = _obligation_rows(conn, norm)

        if not is_admin:
            employees = [
                item for item in employees
                if norm(item.get("username")) == viewer_key or (viewer_full_key and norm(item.get("full_name")) == viewer_full_key)
            ]
            if not employees:
                employees = [{
                    "username": str(getattr(ident, "employee_username", "") or ""),
                    "full_name": str(getattr(ident, "full_name", "") or ""),
                    "role": str(getattr(ident, "role", "") or ""),
                    "employment_status": "Đang làm việc",
                }]

        tichluy_by_key = {norm(item.get("Tên nhân viên")): item for item in tichluy_rows if norm(item.get("Tên nhân viên"))}
        output = []
        for employee in employees:
            username = str(employee.get("username") or "").strip()
            full_name = str(employee.get("full_name") or "").strip()
            keys = {norm(username), norm(full_name)} - {""}
            periods = _period_rows(history, keys, norm)
            tichluy_item = next((tichluy_by_key[key] for key in keys if key in tichluy_by_key), {})
            periods = _merge_tichluy_periods(periods, tichluy_item)
            history_paid = sum(max(0, _number(row.get("contribution"))) for row in periods)
            source_paid = max(0, _number(tichluy_item.get("Đã tích lũy")))
            target = max(0, _number(tichluy_item.get("Mục tiêu tích lũy"))) or _DEFAULT_ACCUMULATION_TARGET
            paid_total = max(history_paid, source_paid)
            remaining = max(0, target - paid_total)
            employee_obligations = [row for row in obligations if norm(row.get("employee_name")) in keys]
            obligation_total = sum(max(0, _number(row.get("amount"))) for row in employee_obligations)
            output.append({
                "employee_name": username,
                "full_name": full_name,
                "role": str(employee.get("role") or ""),
                "employment_status": str(employee.get("employment_status") or ""),
                "target": target,
                "paid_total": paid_total,
                "history_paid_total": history_paid,
                "source_paid_total": source_paid,
                "remaining": remaining,
                "completed": target > 0 and remaining == 0,
                "period_count": len([row for row in periods if max(0, _number(row.get("contribution"))) > 0]),
                "periods": periods,
                "obligation_total": obligation_total,
                "obligation_count": len(employee_obligations),
                "obligations": employee_obligations,
            })

        output.sort(key=lambda row: (norm(row.get("role")), norm(row.get("employee_name"))))
        return {
            "ok": True,
            "release": RELEASE,
            "scope": "all" if is_admin else "self",
            "can_view_all": is_admin,
            "employees": output,
            "totals": {
                "employee_count": len(output),
                "paid_total": sum(row["paid_total"] for row in output),
                "remaining_total": sum(row["remaining"] for row in output),
                "obligation_total": sum(row["obligation_total"] for row in output),
                "obligation_count": sum(row["obligation_count"] for row in output),
            },
        }

    app.state.payroll_personal_tracking_installed = True
    app.state.payroll_personal_tracking_release = RELEASE

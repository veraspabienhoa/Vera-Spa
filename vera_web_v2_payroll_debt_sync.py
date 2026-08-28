"""Automatic legacy NoViPham debt sync for Web V2 Payroll.

The legacy system remains the source of truth for carried violation debt. This
wrapper refreshes only the NoViPham dataset before payroll calculation (and when
the obligation panel is opened), then lets the canonical Payroll 3.7/3.8 path
apply the existing status/due-date rules to the current payroll.

Admin adjustments are persisted separately from the legacy sheet: Admin can add
manual debt rows or hide/delete legacy rows in Web V2. Every automatic refresh
re-applies those adjustments, so deleted rows do not unexpectedly reappear.
"""
from __future__ import annotations

from datetime import date
import hashlib
from typing import Any

from fastapi import Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

import vera_web_v2_payroll as _payroll


PAYROLL_DEBT_SYNC_RELEASE = "3.8-auto-legacy-obligations-admin"
LEGACY_DEBT_DATASET_KEY = "violation_debt"
LEGACY_DEBT_HIDDEN_KEY = "legacy_debt_hidden_keys"
LEGACY_DEBT_MANUAL_KEY = "legacy_debt_manual_rows"
LEGACY_DEBT_TYPES = {"Âm thực nhận", "Tạm hoãn vi phạm"}


class LegacyDebtAdminCreate(BaseModel):
    employee_name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000_000)
    period_start: date
    period_end: date
    due_from: date
    debt_type: str = Field(default="Âm thực nhận", min_length=1, max_length=80)
    content: str = Field(default="Chưa hoàn thành nghĩa vụ Vi phạm", min_length=1, max_length=500)


def _cached_obligation_state(conn) -> tuple[bool, int]:
    row = conn.execute(text("""
        SELECT payload
        FROM vera_dataset_cache
        WHERE dataset_key=:key
        LIMIT 1
    """), {"key": LEGACY_DEBT_DATASET_KEY}).first()
    if row is None:
        return False, 0
    payload = row[0] or []
    count = len([item for item in payload if isinstance(item, dict)]) if isinstance(payload, list) else 0
    return True, count


def _read_cached_obligations(conn) -> list[dict[str, Any]]:
    payload = conn.execute(text("""
        SELECT payload
        FROM vera_dataset_cache
        WHERE dataset_key=:key
        LIMIT 1
    """), {"key": LEGACY_DEBT_DATASET_KEY}).scalar_one_or_none()
    return [dict(item) for item in (payload or []) if isinstance(item, dict)]


def _read_legacy_obligations(google_client) -> list[dict[str, Any]]:
    spreadsheet = google_client().open_by_key(_payroll.LEGACY_SPREADSHEET_ID)
    response = spreadsheet.values_batch_get(
        [f"'{_payroll.LEGACY_OBLIGATION_WORKSHEET}'!A:N"],
        params={"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE"},
    )
    ranges = response.get("valueRanges", []) if isinstance(response, dict) else []
    if len(ranges) != 1:
        raise RuntimeError("Google Sheets không trả dữ liệu NoViPham.")
    values = ranges[0].get("values", []) if isinstance(ranges[0], dict) else []
    records = _payroll._sheet_records_from_values(values, _payroll.LEGACY_OBLIGATION_HEADERS)
    for item in records:
        item.pop("__legacy_sheet_row", None)
    return records


def _date_key(value: Any) -> str:
    parsed = _payroll._parse_date(value)
    return parsed.isoformat() if parsed else str(value or "").strip().casefold()


def _legacy_debt_key(item: dict[str, Any]) -> str:
    employee = str(item.get("employee_name") or item.get("Tên nhân viên") or "").strip().casefold()
    amount = str(max(0, _payroll._number(item.get("amount") or item.get("Số tiền"))))
    period_start = _date_key(item.get("period_start") or item.get("Kỳ phát sinh từ"))
    period_end = _date_key(item.get("period_end") or item.get("Kỳ phát sinh đến"))
    due_from = _date_key(item.get("due_from") or item.get("Bắt đầu trừ từ"))
    debt_type = str(item.get("type") or item.get("Loại") or "").strip().casefold()
    canonical = "|".join((employee, amount, period_start, period_end, due_from, debt_type))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _manual_rows(conn) -> list[dict[str, Any]]:
    raw = _payroll._setting(conn, LEGACY_DEBT_MANUAL_KEY, [])
    return [dict(item) for item in (raw or []) if isinstance(item, dict)]


def _hidden_keys(conn) -> set[str]:
    raw = _payroll._setting(conn, LEGACY_DEBT_HIDDEN_KEY, [])
    if not isinstance(raw, list):
        return set()
    return {str(item or "").strip() for item in raw if str(item or "").strip()}


def _apply_admin_adjustments(conn, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hidden = _hidden_keys(conn)
    manual = _manual_rows(conn)
    merged: dict[str, dict[str, Any]] = {}
    for item in records:
        key = _legacy_debt_key(item)
        if key and key not in hidden:
            merged[key] = dict(item)
    for item in manual:
        key = _legacy_debt_key(item)
        if key and key not in hidden:
            merged[key] = dict(item)
    return list(merged.values())


def _write_adjusted_cache(conn, records: list[dict[str, Any]], source_version: str) -> list[dict[str, Any]]:
    adjusted = _apply_admin_adjustments(conn, records)
    _payroll._write_dataset_cache(
        conn,
        LEGACY_DEBT_DATASET_KEY,
        adjusted,
        source_version,
    )
    return adjusted


def _refresh_legacy_obligations(*, engine_instance, google_client) -> dict[str, Any]:
    """Refresh NoViPham safely; never silently drop carried debt on Google failure."""
    try:
        records = _read_legacy_obligations(google_client)
    except Exception as exc:
        with engine_instance().connect() as conn:
            cache_exists, cached_count = _cached_obligation_state(conn)
        if cache_exists:
            return {
                "status": "cached",
                "count": cached_count,
                "warning": (
                    "Không làm mới được NoViPham; hệ thống đang dùng dữ liệu nợ đã lưu gần nhất. "
                    f"({str(exc)[:180]})"
                ),
            }
        raise HTTPException(
            502,
            "Không tải được Nợ vi phạm kỳ trước từ hệ thống cũ và chưa có dữ liệu cache an toàn. "
            "Đã dừng tính lương để tránh bỏ sót khấu trừ.",
        ) from exc

    with engine_instance().begin() as conn:
        adjusted = _write_adjusted_cache(conn, records, "legacy_google_sheet_auto_admin_adjusted")
    return {"status": "fresh", "count": len(adjusted), "warning": ""}


def _find_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            return route
    return None


def _require_admin(ident) -> None:
    if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
        raise HTTPException(403, "Chỉ Admin được thêm hoặc xóa Nợ vi phạm kỳ trước.")


def _canonical_employee(conn, employee_name: str) -> str:
    canonical = conn.execute(text("""
        SELECT username
        FROM employees
        WHERE lower(btrim(username))=lower(btrim(:username))
          AND lower(COALESCE(role,'')) IN ('nhanvien','leader')
        LIMIT 1
    """), {"username": employee_name.strip()}).scalar_one_or_none()
    if not canonical:
        raise HTTPException(400, "Tên nhân viên không khớp chính xác với hồ sơ Nhân viên/Leader.")
    return str(canonical)


def _admin_debt_rows(conn) -> list[dict[str, Any]]:
    manual_keys = {_legacy_debt_key(item) for item in _manual_rows(conn)}
    output = []
    for item in _read_cached_obligations(conn):
        status_key = str(item.get("Trạng thái") or item.get("status") or "Chưa hoàn thành").strip().lower()
        if status_key not in {"", "chưa hoàn thành", "chua hoan thanh"}:
            continue
        debt_type = str(item.get("Loại") or item.get("type") or "").strip()
        if debt_type not in LEGACY_DEBT_TYPES:
            continue
        output.append({
            "debt_key": _legacy_debt_key(item),
            "employee_name": str(item.get("Tên nhân viên") or item.get("employee_name") or "").strip(),
            "amount": max(0, _payroll._number(item.get("Số tiền") or item.get("amount"))),
            "period_start": str(item.get("Kỳ phát sinh từ") or item.get("period_start") or "").strip(),
            "period_end": str(item.get("Kỳ phát sinh đến") or item.get("period_end") or "").strip(),
            "due_from": str(item.get("Bắt đầu trừ từ") or item.get("due_from") or "").strip(),
            "content": str(item.get("Nội dung") or item.get("content") or "").strip(),
            "type": debt_type,
            "status": str(item.get("Trạng thái") or item.get("status") or "Chưa hoàn thành").strip(),
            "source": "Admin" if _legacy_debt_key(item) in manual_keys else "Hệ thống cũ",
        })
    output.sort(key=lambda item: (item["type"], item["employee_name"].casefold(), item["period_start"]))
    return output


def install_payroll_debt_sync_routes(
    app,
    *,
    engine_instance,
    current_identity,
    require_feature,
    identity_type,
    google_client,
) -> None:
    """Install automatic NoViPham refresh around Payroll 3.8 routes."""
    if getattr(app.state, "payroll_debt_sync_installed", False):
        return

    calculate_route = _find_route(app, "/v2/payroll/calculate", "POST")
    if calculate_route is None:
        raise RuntimeError("Debt sync cannot find the Payroll calculate route.")
    original_calculate = calculate_route.endpoint
    app.router.routes.remove(calculate_route)

    obligations_route = _find_route(app, "/v2/payroll/obligations", "GET")
    original_obligations = obligations_route.endpoint if obligations_route is not None else None
    if obligations_route is not None:
        app.router.routes.remove(obligations_route)

    @app.get("/v2/payroll-debt-sync/health")
    def payroll_debt_sync_health():
        return {"ok": True, "release": PAYROLL_DEBT_SYNC_RELEASE}

    @app.post("/v2/payroll-debt-sync/refresh")
    def refresh_payroll_debt(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
        sync = _refresh_legacy_obligations(
            engine_instance=engine_instance,
            google_client=google_client,
        )
        return {
            "ok": True,
            "release": PAYROLL_DEBT_SYNC_RELEASE,
            "legacy_obligation_source": _payroll.LEGACY_OBLIGATION_WORKSHEET,
            "legacy_obligation_sync": sync["status"],
            "legacy_obligation_count": sync["count"],
            "legacy_obligation_warning": sync["warning"],
        }

    @app.get("/v2/payroll-debt-sync/admin-debts")
    def admin_debts(ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        sync = _refresh_legacy_obligations(
            engine_instance=engine_instance,
            google_client=google_client,
        )
        with engine_instance().connect() as conn:
            rows = _admin_debt_rows(conn)
        return {
            "ok": True,
            "rows": rows,
            "count": len(rows),
            "sync": sync["status"],
            "warning": sync["warning"],
        }

    @app.post("/v2/payroll-debt-sync/admin-debts")
    def create_admin_debt(body: LegacyDebtAdminCreate, ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        debt_type = body.debt_type.strip()
        if debt_type not in LEGACY_DEBT_TYPES:
            raise HTTPException(400, "Loại nợ không hợp lệ.")
        if body.period_end < body.period_start:
            raise HTTPException(400, "Kỳ phát sinh đến không được trước Kỳ phát sinh từ.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_penalty_obligation")
            employee = _canonical_employee(conn, body.employee_name)
            item = {
                "Tên nhân viên": employee,
                "Số tiền": max(0, _payroll._number(body.amount)),
                "Kỳ phát sinh từ": body.period_start.strftime("%d/%m/%Y"),
                "Kỳ phát sinh đến": body.period_end.strftime("%d/%m/%Y"),
                "Bắt đầu trừ từ": body.due_from.strftime("%d/%m/%Y"),
                "Nội dung": body.content.strip(),
                "Loại": debt_type,
                "Trạng thái": "Chưa hoàn thành",
                "Nguồn": "Web V2 Admin",
                "Người cập nhật": ident.employee_username,
            }
            key = _legacy_debt_key(item)
            manual = [row for row in _manual_rows(conn) if _legacy_debt_key(row) != key]
            manual.append(item)
            hidden = _hidden_keys(conn)
            hidden.discard(key)
            _payroll._put_setting(conn, LEGACY_DEBT_MANUAL_KEY, manual, ident.employee_username)
            _payroll._put_setting(conn, LEGACY_DEBT_HIDDEN_KEY, sorted(hidden), ident.employee_username)
            cached = _read_cached_obligations(conn)
            adjusted = _write_adjusted_cache(conn, cached, "legacy_admin_add")
        return {
            "ok": True,
            "debt_key": key,
            "count": len(adjusted),
            "message": f"Đã thêm Nợ vi phạm cho {employee}.",
        }

    @app.delete("/v2/payroll-debt-sync/admin-debts/{debt_key}")
    def delete_admin_debt(debt_key: str, ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        wanted = str(debt_key or "").strip()
        if not wanted:
            raise HTTPException(400, "Thiếu mã khoản nợ cần xóa.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_penalty_obligation")
            cached = _read_cached_obligations(conn)
            if not any(_legacy_debt_key(item) == wanted for item in cached):
                raise HTTPException(404, "Không tìm thấy khoản Nợ vi phạm cần xóa.")
            manual = [row for row in _manual_rows(conn) if _legacy_debt_key(row) != wanted]
            hidden = _hidden_keys(conn)
            hidden.add(wanted)
            _payroll._put_setting(conn, LEGACY_DEBT_MANUAL_KEY, manual, ident.employee_username)
            _payroll._put_setting(conn, LEGACY_DEBT_HIDDEN_KEY, sorted(hidden), ident.employee_username)
            adjusted = _write_adjusted_cache(conn, cached, "legacy_admin_delete")
        return {
            "ok": True,
            "count": len(adjusted),
            "message": "Đã xóa khoản Nợ vi phạm. Khoản này sẽ tiếp tục bị ẩn sau các lần đồng bộ hệ thống cũ.",
        }

    if original_obligations is not None:
        @app.get("/v2/payroll/obligations", name=getattr(obligations_route, "name", "obligations"))
        def obligations_with_legacy_refresh(ident: identity_type = Depends(current_identity)):
            with engine_instance().connect() as conn:
                require_feature(conn, ident, "payroll_penalty_obligation")
            sync = _refresh_legacy_obligations(
                engine_instance=engine_instance,
                google_client=google_client,
            )
            result = original_obligations(ident=ident)
            payload = dict(result or {})
            for group in payload.get("groups") or []:
                for detail in group.get("details") or []:
                    detail["debt_key"] = _legacy_debt_key(detail)
            payload.update({
                "legacy_obligation_source": _payroll.LEGACY_OBLIGATION_WORKSHEET,
                "legacy_obligation_sync": sync["status"],
                "legacy_obligation_count": sync["count"],
                "legacy_obligation_warning": sync["warning"],
            })
            return payload

    @app.post("/v2/payroll/calculate", name=getattr(calculate_route, "name", "calculate_payroll"))
    async def calculate_payroll_with_legacy_debt(
        month: str = Query(...),
        period_no: int = Query(..., ge=1, le=2),
        payload: bytes = Body(
            ...,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")

        sync = _refresh_legacy_obligations(
            engine_instance=engine_instance,
            google_client=google_client,
        )
        result = await original_calculate(
            month=month,
            period_no=period_no,
            payload=payload,
            ident=ident,
        )
        output = dict(result or {})
        output.update({
            "legacy_obligation_source": _payroll.LEGACY_OBLIGATION_WORKSHEET,
            "legacy_obligation_sync": sync["status"],
            "legacy_obligation_count": sync["count"],
            "legacy_obligation_warning": sync["warning"],
            "debt_sync_release": PAYROLL_DEBT_SYNC_RELEASE,
        })
        return output

    app.state.payroll_debt_sync_installed = True
    app.state.payroll_debt_sync_release = PAYROLL_DEBT_SYNC_RELEASE

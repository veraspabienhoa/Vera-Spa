"""Payroll UX/business enhancements layered on top of Payroll 3.8.

Adds saved-payroll management, safe history deletion, completion bookkeeping,
and Admin deferral of current-period penalties into the next payroll period.
"""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import uuid
from typing import Any

from fastapi import Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

import vera_web_v2_payroll as _payroll


PAYROLL_ENHANCEMENTS_RELEASE = "3.8-payroll-completion-history-deferral"
DELETED_BATCHES_KEY = "deleted_payroll_batches"


class PayrollPenaltyDefer(BaseModel):
    employee_name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000_000)
    period_start: date
    period_end: date


def _find_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            return route
    return None


def _deleted_batches(conn) -> set[str]:
    raw = _payroll._setting(conn, DELETED_BATCHES_KEY, [])
    if not isinstance(raw, list):
        return set()
    return {str(item or "").strip() for item in raw if str(item or "").strip()}


def _save_deleted_batches(conn, values: set[str], actor: str) -> None:
    _payroll._put_setting(conn, DELETED_BATCHES_KEY, sorted(values), actor)


def _filter_deleted(records: list[dict[str, Any]], deleted: set[str]) -> list[dict[str, Any]]:
    if not deleted:
        return records
    return [item for item in records if str(item.get("Mã bản lưu") or "").strip() not in deleted]


def _saved_batch_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        batch = str(item.get("Mã bản lưu") or "").strip()
        if batch:
            grouped.setdefault(batch, []).append(item)
    output = []
    for batch, rows in grouped.items():
        saved_dates = [str(row.get("Ngày lưu") or "").strip() for row in rows if str(row.get("Ngày lưu") or "").strip()]
        saved_times = [str(row.get("Giờ lưu") or "").strip() for row in rows if str(row.get("Giờ lưu") or "").strip()]
        output.append({
            "batch": batch,
            "employee_count": len({str(row.get("Tên Hệ thống") or "").strip() for row in rows if str(row.get("Tên Hệ thống") or "").strip()}),
            "row_count": len(rows),
            "total_salary": sum(_payroll._number(row.get("Tiền Lương")) for row in rows),
            "total_net": sum(_payroll._number(row.get("Số tiền thực nhận")) for row in rows),
            "saved_date": saved_dates[0] if saved_dates else "",
            "saved_time": saved_times[0] if saved_times else "",
        })

    def sort_key(item: dict[str, Any]):
        raw = item.get("batch", "")
        # Labels are "Kỳ N - Tháng M/YYYY". Lexical fallback remains stable for legacy labels.
        import re
        match = re.search(r"Kỳ\s*(\d+)\s*-\s*Tháng\s*(\d+)/(\d{4})", str(raw), re.I)
        if match:
            period_no, month, year = map(int, match.groups())
            return (year, month, period_no, str(raw))
        return (0, 0, 0, str(raw))

    output.sort(key=sort_key, reverse=True)
    return output


def _next_period_start(period_start: date, period_end: date) -> date:
    _payroll._period_label(period_start, period_end)
    return period_end + timedelta(days=1)


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


def _defer_source_key(employee_name: str, start: date, end: date, norm) -> str:
    return f"DEFER|{start.isoformat()}|{end.isoformat()}|{norm(employee_name)}"


def _mark_applied_custom_obligations_completed(conn, body: _payroll.PayrollSave, actor: str, norm) -> int:
    employees = {norm(item.get("Tên Hệ thống")) for item in body.rows if isinstance(item, dict)} - {""}
    if not employees:
        return 0
    rows = _payroll._obligations(conn)
    changed = 0
    label = _payroll._period_label(body.start, body.end)
    for item in rows:
        status = norm(item.get("status") or "Chưa hoàn thành")
        if status not in {"", "chua hoan thanh"}:
            continue
        if norm(item.get("employee_name")) not in employees:
            continue
        due = _payroll._parse_date(item.get("due_from"))
        if due and due > body.start:
            continue
        item["status"] = "Đã hoàn thành"
        item["completed_period"] = label
        item["completed_by"] = actor
        item["completed_on"] = body.end.isoformat()
        changed += 1
    if changed:
        _payroll._put_setting(conn, "violation_obligations", rows, actor)
    return changed


def install_payroll_enhancement_routes(
    app,
    *,
    engine_instance,
    current_identity,
    require_feature,
    norm,
    identity_type,
) -> None:
    if getattr(app.state, "payroll_enhancements_installed", False):
        return

    history_route = _find_route(app, "/v2/payroll/history", "GET")
    save_route = _find_route(app, "/v2/payroll/save", "POST")
    if history_route is None or save_route is None:
        raise RuntimeError("Payroll enhancements require history and save routes.")

    original_history = history_route.endpoint
    original_save = save_route.endpoint
    app.router.routes.remove(history_route)
    app.router.routes.remove(save_route)

    @app.get("/v2/payroll-enhancements/health")
    def payroll_enhancements_health():
        return {"ok": True, "release": PAYROLL_ENHANCEMENTS_RELEASE}

    @app.get("/v2/payroll/history", name=getattr(history_route, "name", "payroll_history"))
    def payroll_history_enhanced(
        batch: str = Query(default=""),
        search: str = Query(default=""),
        ident: identity_type = Depends(current_identity),
    ):
        result = dict(original_history(batch=batch, search=search, ident=ident) or {})
        with engine_instance().connect() as conn:
            deleted = _deleted_batches(conn)
        result["records"] = _filter_deleted(list(result.get("records") or []), deleted)
        result["batches"] = [item for item in list(result.get("batches") or []) if str(item) not in deleted]
        result["count"] = len(result["records"])
        return result

    @app.get("/v2/payroll/saved-batches")
    def saved_payroll_batches(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_history")
            records, _checksum, _updated = _payroll._payload(conn)
            deleted = _deleted_batches(conn)
        visible = _payroll._visible(_filter_deleted(records, deleted), ident, norm)
        batches = _saved_batch_summary(visible)
        return {"saved_batches": batches, "count": len(batches)}

    @app.delete("/v2/payroll/history/{batch_id}")
    def delete_payroll_history_batch(batch_id: str, ident: identity_type = Depends(current_identity)):
        wanted = str(batch_id or "").strip()
        if not wanted:
            raise HTTPException(400, "Chưa chọn kỳ lương cần xóa.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_history_edit")
            deleted = _deleted_batches(conn)
            deleted.add(wanted)
            _save_deleted_batches(conn, deleted, ident.employee_username)

            normalized_deleted = conn.execute(
                text("DELETE FROM payroll_history_rows WHERE batch_id=:batch"),
                {"batch": wanted},
            ).rowcount

            cached = conn.execute(text("""
                SELECT payload FROM vera_dataset_cache
                WHERE dataset_key='payroll_history' LIMIT 1
            """)).scalar_one_or_none()
            records = [dict(item) for item in (cached or []) if isinstance(item, dict)]
            kept = [item for item in records if str(item.get("Mã bản lưu") or "").strip() != wanted]
            serialized = json.dumps(kept, ensure_ascii=False, separators=(",", ":"), default=str)
            checksum = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            conn.execute(text("""
                INSERT INTO vera_dataset_cache(dataset_key,payload,row_count,checksum,source_version,updated_at,expires_at)
                VALUES ('payroll_history',CAST(:payload AS jsonb),:count,:checksum,'web_v2_deleted',NOW(),NOW()+INTERVAL '3650 days')
                ON CONFLICT(dataset_key) DO UPDATE SET payload=EXCLUDED.payload,row_count=EXCLUDED.row_count,
                  checksum=EXCLUDED.checksum,source_version=EXCLUDED.source_version,updated_at=NOW(),expires_at=EXCLUDED.expires_at
            """), {"payload": serialized, "count": len(kept), "checksum": checksum})
        return {
            "ok": True,
            "batch": wanted,
            "normalized_deleted": int(normalized_deleted or 0),
            "message": f"Đã xóa lịch sử bảng lương {wanted}.",
        }

    @app.post("/v2/payroll/save", name=getattr(save_route, "name", "save_payroll"))
    def save_payroll_enhanced(
        body: _payroll.PayrollSave,
        ident: identity_type = Depends(current_identity),
    ):
        result = dict(original_save(body=body, ident=ident) or {})
        label = _payroll._period_label(body.start, body.end)
        with engine_instance().begin() as conn:
            deleted = _deleted_batches(conn)
            if label in deleted:
                deleted.remove(label)
                _save_deleted_batches(conn, deleted, ident.employee_username)
            completed_obligations = _mark_applied_custom_obligations_completed(
                conn, body, ident.employee_username, norm
            )
        result.update({
            "completed": True,
            "completed_obligations": completed_obligations,
            "message": f"Đã hoàn thành {label} và lưu vào LỊCH SỬ BẢNG LƯƠNG.",
        })
        return result

    @app.post("/v2/payroll/penalties/defer")
    def defer_current_penalty(
        body: PayrollPenaltyDefer,
        ident: identity_type = Depends(current_identity),
    ):
        amount = max(0, _payroll._number(body.amount))
        if amount <= 0:
            raise HTTPException(400, "Số tiền Vi phạm kỳ này phải lớn hơn 0.")
        due_from = _next_period_start(body.period_start, body.period_end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_penalty_obligation")
            canonical_name = _canonical_employee(conn, body.employee_name)
            rows = _payroll._obligations(conn)
            source_key = _defer_source_key(canonical_name, body.period_start, body.period_end, norm)
            existing = next((item for item in rows if str(item.get("source_key") or "") == source_key), None)
            payload = {
                "employee_name": canonical_name,
                "amount": amount,
                "content": "Vi phạm kỳ trước chuyển từ kỳ lương trước",
                "type": "Tạm hoãn vi phạm",
                "period_start": body.period_start.isoformat(),
                "period_end": body.period_end.isoformat(),
                "due_from": due_from.isoformat(),
                "status": "Chưa hoàn thành",
                "source_key": source_key,
                "updated_by": ident.employee_username,
            }
            if existing is None:
                payload["id"] = str(uuid.uuid4())
                rows.append(payload)
            else:
                existing.update(payload)
                existing.setdefault("id", str(uuid.uuid4()))
                payload = existing
            _payroll._put_setting(conn, "violation_obligations", rows, ident.employee_username)
        return {
            "ok": True,
            "obligation": payload,
            "due_from": due_from.isoformat(),
            "message": (
                f"Đã chuyển {amount:,.0f}đ Vi phạm của {canonical_name} sang kỳ kế tiếp "
                f"(bắt đầu trừ {due_from.strftime('%d/%m/%Y')})."
            ).replace(",", "."),
        }

    app.state.payroll_enhancements_installed = True
    app.state.payroll_enhancements_release = PAYROLL_ENHANCEMENTS_RELEASE

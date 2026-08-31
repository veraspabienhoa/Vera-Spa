"""Operations 4.1: attendance filters and detailed audit export.

- Chấm công supports employee / department / shift filters for display + Excel.
- Thay đổi hệ thống supports exact date ranges, actor search and Excel export.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
import unicodedata
from typing import Any, Callable
from urllib.parse import quote

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

import vera_web_v2_admin_audit_archive as audit_module
import vera_web_v2_snapshot as snapshot_module


RELEASE = "4.1-operations-search-filters-export"


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return " ".join(text.split())


def _matches(value: Any, query: str) -> bool:
    needle = _norm(query)
    return not needle or needle in _norm(value)


def _remove_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def _validate_range(start: date, end: date, *, max_days: int) -> None:
    if end < start:
        raise HTTPException(400, "Đến ngày phải bằng hoặc sau Từ ngày.")
    if (end - start).days > max_days - 1:
        raise HTTPException(400, f"Khoảng thời gian tối đa là {max_days} ngày.")


def _snapshot_filter(records: list[dict[str, Any]], employee: str, department: str, shift: str) -> list[dict[str, Any]]:
    return [
        item for item in records
        if _matches(item.get("employee_name"), employee)
        and _matches(item.get("break_department"), department)
        and _matches(item.get("shift"), shift)
    ]


def _snapshot_options(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    def unique(key: str):
        values = {str(item.get(key) or "").strip() for item in records}
        return sorted((value for value in values if value), key=lambda value: _norm(value))
    return {
        "employees": unique("employee_name"),
        "departments": unique("break_department"),
        "shifts": unique("shift"),
    }


def _snapshot_workbook(records: list[dict[str, Any]]) -> bytes:
    columns = [
        ("date", "Ngày"), ("employee_code", "Mã nhân viên"), ("employee_name", "Nhân viên"),
        ("break_department", "Bộ phận"), ("shift", "Ca"), ("shift_start", "Bắt đầu ca"),
        ("shift_end", "Kết thúc ca"), ("check_in", "Giờ vào"),
        ("faceid_last", "FaceID cuối TimeSoft"), ("check_out", "Check-out cuối ca"),
        ("break_planned_minutes", "Nghỉ giữa ca quy định (phút)"),
        ("break_out", "Giờ ra nghỉ giữa ca"), ("break_in", "Giờ vào lại"),
        ("break_actual_minutes", "Số phút nghỉ giữa ca"), ("break_over_minutes", "Quá quy định (phút)"),
        ("break_source", "Nguồn nghỉ giữa ca"), ("break_method", "Cách xác định"),
        ("break_status", "Trạng thái nghỉ giữa ca"), ("punch_times", "Các lần chấm FaceID"),
        ("arrival_status", "Trạng thái vào"), ("departure_status", "Trạng thái ra"),
        ("late_minutes", "Phút trễ"), ("early_minutes", "Phút về sớm"),
        ("total_minutes", "Tổng phút"), ("punch_count", "Số lần chấm"),
    ]
    wb = Workbook()
    ws = wb.active
    ws.title = "Chấm công"
    ws.append([label for _, label in columns])
    for item in records:
        ws.append([
            " · ".join(str(value) for value in (item.get(key) or [])) if key == "punch_times" else item.get(key, "")
            for key, _ in columns
        ])
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def _audit_serialize(row: dict[str, Any]) -> dict[str, Any]:
    old_data = audit_module._json_dict(row.get("old_data"))
    new_data = audit_module._json_dict(row.get("new_data"))
    event_type = str(row.get("event_type") or "")
    actor = str(row.get("actor") or "")
    return {
        "id": int(row.get("id") or 0),
        "event_type": event_type,
        "record_uid": str(row.get("record_uid") or ""),
        "employee_name": str(row.get("employee_name") or ""),
        "leave_date": str(row.get("leave_date") or ""),
        "actor": actor,
        "source": str(row.get("source") or ""),
        "detail": audit_module._summary(event_type, old_data, new_data, actor),
        "field_changes": audit_module._field_changes(old_data, new_data, event_type),
        "old_data": old_data,
        "new_data": new_data,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "expires_at": row["expires_at"].isoformat() if row.get("expires_at") else "",
    }


def _audit_rows(conn, start: date, end: date, actor: str, *, archive_only: bool = False):
    table = audit_module.ARCHIVE_TABLE
    event_clause = "AND event_type IN ('update','delete') AND expires_at >= NOW()" if archive_only else ""
    rows = conn.execute(audit_module.text(f"""
        SELECT id, event_type, record_uid, employee_name, leave_date,
               actor, source, old_data, new_data, created_at, expires_at
        FROM {table}
        WHERE (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date BETWEEN :start_date AND :end_date
          {event_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT 5000
    """), {"start_date": start, "end_date": end}).mappings().all()
    if actor.strip():
        rows = [row for row in rows if _matches(row.get("actor"), actor)]
    return rows


def _audit_workbook(changes: list[dict[str, Any]]) -> bytes:
    labels = {"insert": "Đăng ký mới", "update": "Sửa lịch nghỉ", "delete": "Xóa lịch nghỉ"}
    wb = Workbook()
    ws = wb.active
    ws.title = "Thay đổi hệ thống"
    ws.append([
        "Thời gian", "Loại thay đổi", "Nhân viên", "Ngày nghỉ", "Người thực hiện",
        "Nội dung", "Chi tiết thay đổi", "Mã bản ghi",
    ])
    for item in changes:
        field_text = "; ".join(
            f"{change.get('label') or change.get('field')}: {change.get('before') or '—'} → {change.get('after') or '—'}"
            for change in item.get("field_changes") or []
        )
        created = item.get("created_at") or ""
        try:
            created = datetime.fromisoformat(str(created).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            pass
        ws.append([
            created,
            labels.get(item.get("event_type"), item.get("event_type") or ""),
            item.get("employee_name") or "",
            item.get("leave_date") or "",
            item.get("actor") or "",
            item.get("detail") or "",
            field_text,
            item.get("record_uid") or "",
        ])
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def install_operations_v41(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature,
    identity_type,
) -> None:
    if getattr(app.state, "operations_v41_installed", False):
        return

    # Replace attendance routes so filters apply consistently to screen + export.
    _remove_route(app, "/v2/snapshot", "GET")
    _remove_route(app, "/v2/snapshot/export.xlsx", "GET")

    @app.get("/v2/snapshot")
    def snapshot_filtered(
        start: date = Query(...),
        end: date = Query(...),
        employee: str = Query(default="", max_length=200),
        department: str = Query(default="", max_length=200),
        shift: str = Query(default="", max_length=200),
        ident: identity_type = Depends(current_identity),
    ):
        _validate_range(start, end, max_days=63)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "snapshot_today")
            all_records = snapshot_module._records(conn, start, end)
        records = _snapshot_filter(all_records, employee, department, shift)
        return {
            "records": records,
            "count": len(records),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "data_scope": "attendance_only",
            "filters": _snapshot_options(all_records),
            "applied": {"employee": employee, "department": department, "shift": shift},
        }

    @app.get("/v2/snapshot/export.xlsx")
    def snapshot_export_filtered(
        start: date = Query(...),
        end: date = Query(...),
        employee: str = Query(default="", max_length=200),
        department: str = Query(default="", max_length=200),
        shift: str = Query(default="", max_length=200),
        ident: identity_type = Depends(current_identity),
    ):
        _validate_range(start, end, max_days=63)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "snapshot_export")
            all_records = snapshot_module._records(conn, start, end)
        records = _snapshot_filter(all_records, employee, department, shift)
        content = _snapshot_workbook(records)
        filename = f"VERA_ChamCong_{start.isoformat()}_{end.isoformat()}.xlsx"
        return StreamingResponse(
            BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    @app.get("/v2/admin/changes-v41")
    def admin_changes_v41(
        start: date = Query(...),
        end: date = Query(...),
        actor: str = Query(default="", max_length=200),
        ident: identity_type = Depends(current_identity),
    ):
        if str(ident.role or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được xem Thay đổi hệ thống.")
        _validate_range(start, end, max_days=366)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "audit_admin_view")
            conn.execute(audit_module.text(
                f"DELETE FROM {audit_module.ARCHIVE_TABLE} WHERE expires_at < NOW()"
            ))
            changes = [_audit_serialize(row) for row in _audit_rows(conn, start, end, actor)]
            archive = [_audit_serialize(row) for row in _audit_rows(conn, start, end, actor, archive_only=True)]
        return {
            "changes": changes,
            "count": len(changes),
            "archive": archive,
            "archive_count": len(archive),
            "archive_days": audit_module.ARCHIVE_DAYS,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "actor": actor,
        }

    @app.get("/v2/admin/changes-v41/export.xlsx")
    def admin_changes_export_v41(
        start: date = Query(...),
        end: date = Query(...),
        actor: str = Query(default="", max_length=200),
        ident: identity_type = Depends(current_identity),
    ):
        if str(ident.role or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được export Thay đổi hệ thống.")
        _validate_range(start, end, max_days=366)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "audit_admin_view")
            changes = [_audit_serialize(row) for row in _audit_rows(conn, start, end, actor)]
        content = _audit_workbook(changes)
        filename = f"VERA_ThayDoiHeThong_{start.isoformat()}_{end.isoformat()}.xlsx"
        return StreamingResponse(
            BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    @app.get("/v2/operations-v41/health")
    def operations_v41_health():
        return {
            "ok": True,
            "release": RELEASE,
            "snapshot_filters": ["employee", "department", "shift"],
            "audit_filters": ["start", "end", "actor"],
            "audit_excel": True,
        }

    app.state.operations_v41_installed = True
    app.state.operations_v41_release = RELEASE

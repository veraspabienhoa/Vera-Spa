"""Saved payroll history for Web V2. Existing payroll data is read without recalculation."""
from __future__ import annotations

from io import BytesIO
from typing import Any, Callable
from urllib.parse import quote

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import text


PUBLIC_FIELDS = [
    "Mã bản lưu", "Từ ngày", "Đến ngày", "Ngày lưu", "Giờ lưu", "Tên Hệ thống", "Họ và tên",
    "Tiền Lương", "Tiền Hỗ Trợ Hoàn Lại", "Tích lũy", "Chi Phí Sinh Hoạt", "Tiền phạt trong tháng",
    "Tiền ứng lương", "Tiền hỗ trợ Locker", "Vi phạm kỳ trước", "Số tiền thực nhận",
]
ADMIN_FIELDS = PUBLIC_FIELDS + ["Email", "Số tài khoản ngân hàng", "Tên ngân hàng", "Người lưu", "Nguồn dữ liệu"]
MONEY_FIELDS = {
    "Tiền Lương", "Tiền Hỗ Trợ Hoàn Lại", "Tích lũy", "Chi Phí Sinh Hoạt", "Tiền phạt trong tháng",
    "Tiền ứng lương", "Tiền hỗ trợ Locker", "Vi phạm kỳ trước", "Số tiền thực nhận",
}


def _number(value: Any) -> int:
    try: return int(float(str(value or "0").replace(",", "")))
    except ValueError: return 0


def _payload(conn) -> tuple[list[dict[str, Any]], str, str]:
    row = conn.execute(text("SELECT payload, checksum, updated_at::text FROM vera_dataset_cache WHERE dataset_key='payroll_history' LIMIT 1")).first()
    if not row: return [], "", ""
    return [dict(item) for item in (row[0] or []) if isinstance(item, dict)], str(row[1] or ""), str(row[2] or "")


def _visible(records, ident, norm):
    if str(ident.role or "").lower() in {"admin", "quanly", "letan"}:
        return records
    keys = {norm(ident.employee_username), norm(ident.full_name)} - {""}
    return [item for item in records if norm(item.get("Tên Hệ thống")) in keys or norm(item.get("Họ và tên")) in keys]


def install_payroll_routes(app, *, engine_instance: Callable[[], Any], current_identity, require_feature, norm, identity_type):
    def filter_rows(records, batch: str, search: str):
        if batch: records = [item for item in records if str(item.get("Mã bản lưu") or "") == batch]
        needle = norm(search)
        if needle: records = [item for item in records if needle in norm(item.get("Tên Hệ thống")) or needle in norm(item.get("Họ và tên"))]
        return records

    @app.get("/v2/payroll/history")
    def payroll_history(batch: str = Query(default=""), search: str = Query(default=""), ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_history")
            records, checksum, updated_at = _payload(conn)
        records = filter_rows(_visible(records, ident, norm), batch, search)
        fields = ADMIN_FIELDS if str(ident.role).lower() == "admin" else PUBLIC_FIELDS
        clean = [{key: (_number(item.get(key)) if key in MONEY_FIELDS else str(item.get(key) or "")) for key in fields} for item in records]
        batches = []
        for item in records:
            value = str(item.get("Mã bản lưu") or "")
            if value and value not in batches: batches.append(value)
        return {"records": clean, "batches": batches, "fields": fields, "count": len(clean), "checksum": checksum, "updated_at": updated_at}

    @app.get("/v2/payroll/history/export.xlsx")
    def payroll_export(batch: str = Query(default=""), search: str = Query(default=""), ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_export")
            records, _checksum, _updated = _payload(conn)
        records = filter_rows(_visible(records, ident, norm), batch, search)
        fields = ADMIN_FIELDS if str(ident.role).lower() == "admin" else PUBLIC_FIELDS
        wb = Workbook(); ws = wb.active; ws.title = "Lịch sử bảng lương"; ws.append(fields)
        for cell in ws[1]: cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="1F513F")
        for item in records: ws.append([_number(item.get(key)) if key in MONEY_FIELDS else item.get(key, "") for key in fields])
        stream = BytesIO(); wb.save(stream); stream.seek(0)
        return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('VERA_BangLuong.xlsx')}"})

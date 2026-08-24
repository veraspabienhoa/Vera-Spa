"""Attendance-only Snapshot routes. Revenue data is intentionally excluded."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Callable
from urllib.parse import quote

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import text


def _day(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw.split(" ", 1)[0]


def _record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": _day(item.get("WorkDateStr")),
        "employee_code": str(item.get("employeeInfo.EmployeeCode") or item.get("EnrollNumber") or ""),
        "employee_name": str(item.get("employeeInfo.Name") or item.get("EmployeeName") or "").strip(),
        "shift": str(item.get("WorkTimeName") or "").strip(),
        "shift_start": str(item.get("StartWorkTime") or "").strip(),
        "shift_end": str(item.get("EndWorkTime") or "").strip(),
        "check_in": str(item.get("MachineTimeCheckInStr") or item.get("LocalTimeCheckInStr") or "").strip(),
        "check_out": str(item.get("MachineTimeCheckOutStr") or item.get("LocalTimeCheckOutStr") or "").strip(),
        "arrival_status": str(item.get("GoWorkTypeName") or "").strip(),
        "departure_status": str(item.get("LastCheckInTypeName") or "").strip(),
        "late_minutes": int(float(item.get("TotalMinuteInGoLate") or 0)),
        "early_minutes": int(float(item.get("TotalMinuteBackHomeEarly") or 0)),
        "total_minutes": int(float(item.get("TotalMinuteInDay") or 0)),
        "punch_count": int(float(item.get("TotalCheckInOneDay") or 0)),
    }


def _records(conn, start: date, end: date) -> list[dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT dataset_key, payload
        FROM vera_dataset_cache
        WHERE dataset_key='timesoft_employee_checkin_today'
           OR dataset_key LIKE 'timesoft_employee_checkin_20%'
        ORDER BY CASE WHEN dataset_key='timesoft_employee_checkin_today' THEN 0 ELSE 1 END, dataset_key DESC
    """)).mappings().all()
    seen: set[tuple[str, str, str, str]] = set()
    output = []
    for dataset in rows:
        for raw in dataset.get("payload") or []:
            if not isinstance(raw, dict):
                continue
            item = _record(raw)
            try:
                item_date = datetime.strptime(item["date"], "%d/%m/%Y").date()
            except ValueError:
                continue
            if not start <= item_date <= end:
                continue
            key = (item["date"], item["employee_code"], item["check_in"], item["check_out"])
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
    return sorted(output, key=lambda item: (datetime.strptime(item["date"], "%d/%m/%Y"), item["employee_name"].casefold()))


def install_snapshot_routes(app, *, engine_instance: Callable[[], Any], current_identity, require_feature, identity_type):
    def dates(start: date, end: date) -> tuple[date, date]:
        if end < start:
            raise HTTPException(400, "Đến ngày phải bằng hoặc sau Từ ngày.")
        if end - start > timedelta(days=62):
            raise HTTPException(400, "Snapshot chỉ cho xem tối đa 63 ngày mỗi lần.")
        return start, end

    @app.get("/v2/snapshot")
    def snapshot(start: date = Query(...), end: date = Query(...), ident: identity_type = Depends(current_identity)):
        dates(start, end)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "snapshot_today")
            records = _records(conn, start, end)
        return {"records": records, "count": len(records), "start": start.isoformat(), "end": end.isoformat(), "data_scope": "attendance_only"}

    @app.get("/v2/snapshot/export.xlsx")
    def snapshot_export(start: date = Query(...), end: date = Query(...), ident: identity_type = Depends(current_identity)):
        dates(start, end)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "snapshot_export")
            records = _records(conn, start, end)
        columns = [
            ("date", "Ngày"), ("employee_code", "Mã nhân viên"), ("employee_name", "Nhân viên"),
            ("shift", "Ca"), ("shift_start", "Bắt đầu ca"), ("shift_end", "Kết thúc ca"),
            ("check_in", "Giờ vào"), ("check_out", "Giờ ra"), ("arrival_status", "Trạng thái vào"),
            ("departure_status", "Trạng thái ra"), ("late_minutes", "Phút trễ"),
            ("early_minutes", "Phút về sớm"), ("total_minutes", "Tổng phút"), ("punch_count", "Số lần chấm"),
        ]
        wb = Workbook(); ws = wb.active; ws.title = "Snapshot chấm công"
        ws.append([label for _, label in columns])
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="1F513F")
        for item in records: ws.append([item.get(key, "") for key, _ in columns])
        stream = BytesIO(); wb.save(stream); stream.seek(0)
        filename = f"VERA_Snapshot_ChamCong_{start.isoformat()}_{end.isoformat()}.xlsx"
        return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})

"""Birthday notifications and read-only TourVera board for Web V2."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import re
import threading
import time
from typing import Any, Callable

import requests
from fastapi import Depends, HTTPException, Query
from openpyxl import load_workbook
from sqlalchemy import text


BANG_TOUR_FILE_ID = "151d1ueCwH2KXX-HPQF1uj340uWSCS2dW"
_tour_cache: dict[str, Any] = {"loaded_at": 0.0, "columns": [], "records": [], "source_updated_at": ""}
_tour_lock = threading.Lock()


def _birthday(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _clean_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return str(value).strip() if not isinstance(value, (int, float, bool)) else value


def _download_tour() -> tuple[list[str], list[dict[str, Any]], str]:
    errors = []
    for url in (
        f"https://drive.usercontent.google.com/download?id={BANG_TOUR_FILE_ID}&export=download&confirm=t",
        f"https://drive.google.com/uc?export=download&id={BANG_TOUR_FILE_ID}&confirm=t",
    ):
        try:
            response = requests.get(url, timeout=25, allow_redirects=True)
            response.raise_for_status()
            if "text/html" in str(response.headers.get("Content-Type", "")).lower():
                raise RuntimeError("Google Drive trả về trang HTML thay vì file XLSM")
            workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
            if "Input" not in workbook.sheetnames:
                raise RuntimeError("File TourVera không có sheet Input")
            sheet = workbook["Input"]
            raw_headers = [cell.value for cell in next(sheet.iter_rows(min_row=20, max_row=20, max_col=24))]
            columns: list[str] = []
            used: dict[str, int] = {}
            for index, value in enumerate(raw_headers, start=1):
                label = str(value or "").strip() or f"Cột {index}"
                used[label] = used.get(label, 0) + 1
                columns.append(label if used[label] == 1 else f"{label} ({used[label]})")
            records = []
            for values in sheet.iter_rows(min_row=21, max_col=24, values_only=True):
                if not any(value not in (None, "") for value in values):
                    continue
                records.append({columns[index]: _clean_cell(value) for index, value in enumerate(values)})
                if len(records) >= 500:
                    break
            workbook.close()
            return columns, records, str(response.headers.get("Last-Modified") or "")
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("Không tải được Bảng tour: " + " | ".join(errors[-2:]))


def install_people_routes(
    app, *, engine_instance: Callable[[], Any], current_identity, require_feature,
    identity_type, vn_tz,
):
    @app.get("/v2/birthdays")
    def birthdays(month: int | None = Query(default=None, ge=1, le=12), ident: identity_type = Depends(current_identity)):
        today = datetime.now(vn_tz).date()
        wanted_month = int(month or today.month)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "birthday")
            rows = conn.execute(text("""
                SELECT username, COALESCE(full_name,'') full_name, COALESCE(birth_date,'') birth_date,
                       lower(COALESCE(role,'')) role
                FROM employees
                WHERE COALESCE(source_sheet_id,'credentials')='credentials'
                  AND COALESCE(login_locked,false)=false
                  AND lower(COALESCE(role,'')) IN ('nhanvien','leader','letan','locker')
                  AND COALESCE(payload->>'Trạng thái làm việc', payload->>'employment_status', 'Đang làm việc')='Đang làm việc'
                ORDER BY lower(COALESCE(full_name,username))
            """)).mappings().all()
        output = []
        for row in rows:
            dob = _birthday(row["birth_date"])
            if not dob or dob.month != wanted_month:
                continue
            output.append({
                "username": row["username"], "full_name": row["full_name"] or row["username"],
                "birth_date": dob.strftime("%d/%m/%Y"), "day": dob.day, "role": row["role"],
                "is_today": wanted_month == today.month and dob.day == today.day,
            })
        output.sort(key=lambda item: (item["day"], str(item["full_name"]).casefold()))
        return {"month": wanted_month, "year": today.year, "birthdays": output, "count": len(output), "today_count": sum(item["is_today"] for item in output)}

    @app.get("/v2/tour")
    def tour(refresh: bool = Query(default=False), ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "tour_refresh" if refresh else "tour")
        with _tour_lock:
            if refresh or not _tour_cache["records"] or time.monotonic() - float(_tour_cache["loaded_at"]) > 300:
                try:
                    columns, records, source_updated_at = _download_tour()
                except Exception as exc:
                    if not _tour_cache["records"]:
                        raise HTTPException(503, str(exc)) from exc
                else:
                    _tour_cache.update({"loaded_at": time.monotonic(), "columns": columns, "records": records, "source_updated_at": source_updated_at})
            records = list(_tour_cache["records"])
            columns = list(_tour_cache["columns"])
            source_updated_at = str(_tour_cache["source_updated_at"])
        status_column = next((column for column in columns if re.sub(r"\s+", " ", column.lower()).strip() in {"trạng thái", "trang thai"}), "")
        available = 0
        if status_column:
            for item in records:
                status = str(item.get(status_column) or "").lower()
                if not status or "rảnh" in status or "ranh" in status or "sắp xong" in status or "sap xong" in status:
                    available += 1
        return {"columns": columns, "records": records, "count": len(records), "available": available, "source_updated_at": source_updated_at}

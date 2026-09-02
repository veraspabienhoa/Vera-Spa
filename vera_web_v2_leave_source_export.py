"""Idempotent Web V2 -> LichNghi_VeraSpa synchronization.

Only leave scheduling data is appended to MainData A:E. Existing scheduling
fields are never overwritten, a blank ``Loại nghỉ`` cell is backfilled from
PostgreSQL, violation records are excluded, and no penalty field is written to
Google Sheets.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from fastapi import Depends, HTTPException
from sqlalchemy import text


RELEASE = "leave-source-sync-2026-09-02.1"
ALLOWED_ROLES = {"admin", "quanly", "letan"}
EXPECTED_HEADERS = ["Ngày", "Thứ ngày", "Tên nhân viên", "Lý do nghỉ", "Loại nghỉ"]


def _date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip().replace(".", "/").replace("-", "/")
    parts = [part.strip() for part in raw.split("/")]
    if len(parts) != 3:
        return raw
    try:
        if len(parts[0]) == 4:
            year, month, day = map(int, parts)
        else:
            day, month, year = map(int, parts)
        return date(year, month, day).isoformat()
    except ValueError:
        return raw


def _record_key(leave_date: Any, employee_name: Any, leave_reason: Any, *, norm: Callable[[Any], str]) -> tuple[str, str, str]:
    return (_date_key(leave_date), norm(employee_name), norm(leave_reason))


def missing_leave_rows(
    records: list[dict[str, Any]],
    sheet_values: list[list[Any]],
    *,
    norm: Callable[[Any], str],
) -> tuple[list[list[Any]], list[tuple[int, str]], int, int]:
    """Plan appended A:E rows and safe ``Loại nghỉ`` backfills.

    Existing A:D values are treated as immutable.  A matching row whose E cell
    is blank receives only an E-cell update, so a repeat sync also repairs rows
    created by the previous A:D-only implementation.
    """
    existing: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row_number, source_row in enumerate(sheet_values[1:], start=2):
        row = list(source_row[:5]) + [""] * max(0, 5 - len(source_row))
        if any(str(value or "").strip() for value in row):
            key = _record_key(row[0], row[2], row[3], norm=norm)
            existing.setdefault(key, []).append({
                "row_number": row_number,
                "leave_type": str(row[4] or "").strip(),
            })

    pending: list[list[Any]] = []
    leave_type_backfills: list[tuple[int, str]] = []
    already_exists = 0
    excluded_violations = 0
    for record in records:
        if norm(record.get("leave_type")) == norm("Vi phạm"):
            excluded_violations += 1
            continue
        leave_date = record.get("leave_date")
        employee = str(record.get("employee_name") or "").strip()
        reason = str(record.get("leave_reason") or "").strip()
        leave_type = str(record.get("leave_type") or "").strip()
        if not isinstance(leave_date, date) or not employee or not reason:
            continue
        if not leave_type:
            raise ValueError(
                f"Bản ghi {employee} ngày {leave_date.strftime('%d/%m/%Y')} "
                "chưa có Loại nghỉ trong PostgreSQL"
            )
        key = _record_key(leave_date, employee, reason, norm=norm)
        if key in existing:
            already_exists += 1
            if leave_type:
                for matching_row in existing[key]:
                    if int(matching_row["row_number"]) >= 2 and not matching_row["leave_type"]:
                        leave_type_backfills.append((int(matching_row["row_number"]), leave_type))
                        matching_row["leave_type"] = leave_type
            continue
        existing[key] = [{"row_number": 0, "leave_type": leave_type}]
        pending.append([
            leave_date.strftime("%d/%m/%Y"),
            ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"][leave_date.weekday()],
            employee,
            reason,
            leave_type,
        ])
    return pending, leave_type_backfills, already_exists, excluded_violations


def install_leave_source_export_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity: Callable[..., Any],
    require_feature: Callable[..., Any],
    identity_type: Any,
    norm: Callable[[Any], str],
    google_client: Callable[[], Any],
    leave_sheet_id: str,
) -> None:
    if getattr(app.state, "leave_source_export_installed", False):
        return

    @app.get("/v2/leave/source-sync/health")
    def leave_source_sync_health():
        return {
            "ok": True,
            "release": RELEASE,
            "target": "LichNghi_VeraSpa/MainData!A:E",
            "write_mode": "append-missing-and-backfill-type",
            "leave_type_column": "E",
            "violation_rows": "excluded",
            "penalty_fields": "never-written",
        }

    @app.post("/v2/leave/source-sync")
    def sync_leave_source(ident: identity_type = Depends(current_identity)):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role not in ALLOWED_ROLES:
            raise HTTPException(403, "Chỉ Admin, Quản lý hoặc Lễ tân được đồng bộ LichNghi_VeraSpa.")

        with engine_instance().begin() as conn:
            require_feature(conn, ident, "leave_export")
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
            records = [dict(row) for row in conn.execute(text("""
                SELECT leave_date, employee_name, leave_reason, leave_type
                FROM leave_records
                ORDER BY leave_date, COALESCE(source_row, 2147483647), id
            """)).mappings().all()]

            try:
                worksheet = google_client().open_by_key(leave_sheet_id).worksheet("MainData")
                # Read through M only to find the true populated edge. This
                # prevents an A:E write from overwriting a row whose A:E is
                # blank but whose legacy metadata columns F:M still contain data.
                sheet_values = worksheet.get("A:M", value_render_option="FORMATTED_VALUE")
                if isinstance(sheet_values, dict):
                    sheet_values = sheet_values.get("values", [])
                sheet_values = [list(row) for row in (sheet_values or [])]
                headers = (sheet_values[0] if sheet_values else [])[:5]
                if [norm(value) for value in headers] != [norm(value) for value in EXPECTED_HEADERS]:
                    raise RuntimeError(
                        "MainData phải có A=Ngày, B=Thứ ngày, C=Tên nhân viên, "
                        "D=Lý do nghỉ, E=Loại nghỉ"
                    )

                rows, leave_type_backfills, already_exists, excluded = missing_leave_rows(
                    records, sheet_values, norm=norm
                )
                for row_number, leave_type in leave_type_backfills:
                    worksheet.update(
                        range_name=f"E{row_number}:E{row_number}",
                        values=[[leave_type]],
                        value_input_option="USER_ENTERED",
                    )
                if rows:
                    last_used_row = max(
                        (index for index, row in enumerate(sheet_values, start=1) if any(str(value or "").strip() for value in row[:13])),
                        default=1,
                    )
                    start_row = last_used_row + 1
                    end_row = start_row + len(rows) - 1
                    worksheet.update(
                        range_name=f"A{start_row}:E{end_row}",
                        values=rows,
                        value_input_option="USER_ENTERED",
                    )
            except Exception as exc:
                raise HTTPException(503, f"Không đồng bộ được LichNghi_VeraSpa: {type(exc).__name__}: {str(exc)[:240]}") from exc

        return {
            "ok": True,
            "release": RELEASE,
            "added": len(rows),
            "leave_type_backfilled": len(leave_type_backfills),
            "already_exists": already_exists,
            "excluded_violations": excluded,
            "message": (
                f"Đã thêm {len(rows)} dòng lịch nghỉ mới và điền Loại nghỉ cho "
                f"{len(leave_type_backfills)} dòng cũ trong LichNghi_VeraSpa; "
                f"bỏ qua {already_exists} dòng đã có và {excluded} dòng Vi phạm."
            ),
        }

    app.state.leave_source_export_installed = True
    app.state.leave_source_export_release = RELEASE

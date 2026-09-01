"""Download Web V2 leave rows in the legacy LichNghi_VeraSpa shape.

This is an intentionally narrow bridge for the reception/manager VBA workflow:
MainData contains leave scheduling rows only.  Violation rows and every penalty
field are excluded from the download.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Callable
from urllib.parse import quote

from fastapi import Depends, HTTPException
from openpyxl import Workbook
from starlette.responses import Response


RELEASE = "leave-source-export-2026-09-01.1"
ALLOWED_ROLES = {"admin", "quanly", "letan"}
MAIN_HEADERS = ["Ngày", "Thứ ngày", "Tên nhân viên", "Lý do nghỉ"]


def _is_violation(value: Any, norm: Callable[[Any], str]) -> bool:
    return norm(value) == norm("Vi phạm")


def build_leave_source_workbook(
    main_values: list[list[Any]],
    catalog_values: list[list[Any]],
    *,
    norm: Callable[[Any], str],
) -> bytes:
    """Create an XLSX understood by the existing LichNghi_VeraSpa VBA."""
    workbook = Workbook()
    main = workbook.active
    main.title = "MainData"
    main.append(MAIN_HEADERS)

    reason_types: dict[str, str] = {}
    for row in catalog_values[1:]:
        reason = row[1] if len(row) > 1 else ""
        leave_type = row[2] if len(row) > 2 else ""
        key = norm(reason)
        if key and key not in reason_types:
            reason_types[key] = str(leave_type or "")

    seen_rows: set[tuple[str, str, str, str]] = set()
    for source_row in main_values[1:]:
        values = list(source_row[:4]) + [""] * max(0, 4 - len(source_row))
        if not any(str(value or "").strip() for value in values):
            continue
        if _is_violation(reason_types.get(norm(values[3]), ""), norm):
            continue
        row_key = tuple(norm(value) for value in values[:4])
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        main.append(values[:4])

    catalog = workbook.create_sheet("LoaiNghi")
    for source_row in catalog_values:
        catalog.append(list(source_row))

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


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

    @app.get("/v2/leave/source-export/health")
    def leave_source_export_health():
        return {"ok": True, "release": RELEASE, "violation_rows": "excluded", "penalty_fields": "excluded"}

    @app.get("/v2/leave/source-export.xlsx")
    def export_leave_source(
        ident: identity_type = Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role not in ALLOWED_ROLES:
            raise HTTPException(403, "Chỉ Admin, Quản lý hoặc Lễ tân được tải LichNghi_VeraSpa.")
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "leave_export")

        try:
            spreadsheet = google_client().open_by_key(leave_sheet_id)
            main_values = spreadsheet.worksheet("MainData").get_all_values()
            catalog_values = spreadsheet.worksheet("LoaiNghi").get_all_values()
        except Exception as exc:
            raise HTTPException(503, f"Không đọc được file LichNghi_VeraSpa: {type(exc).__name__}: {str(exc)[:200]}") from exc

        payload = build_leave_source_workbook(main_values, catalog_values, norm=norm)
        filename = "LichNghi_VeraSpa.xlsx"
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    app.state.leave_source_export_installed = True
    app.state.leave_source_export_release = RELEASE

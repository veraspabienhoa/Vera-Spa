"""Saved-payroll edit workflow for Web V2 Payroll 3.8.

A completed payroll remains the official history record. This module lets an
Admin/history editor reopen one completed batch as the editable draft for the
same payroll period. Completing the draft again uses the canonical save route,
which atomically replaces that batch instead of creating duplicate rows.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy import text

import vera_web_v2_payroll as _payroll


PAYROLL_SAVED_EDIT_RELEASE = "3.8-saved-payroll-edit"


def _period_dates(records: list[dict[str, Any]]) -> tuple[Any, Any]:
    for item in records:
        start = _payroll._parse_date(item.get("Từ ngày"))
        end = _payroll._parse_date(item.get("Đến ngày"))
        if start and end:
            return start, end
    return None, None


def install_payroll_saved_edit_routes(
    app,
    *,
    engine_instance,
    current_identity,
    require_feature,
    norm,
    identity_type,
) -> None:
    if getattr(app.state, "payroll_saved_edit_installed", False):
        return

    @app.get("/v2/payroll-saved-edit/health")
    def saved_edit_health():
        return {"ok": True, "release": PAYROLL_SAVED_EDIT_RELEASE}

    @app.post("/v2/payroll/saved-batches/{batch_id}/edit")
    def reopen_saved_payroll(batch_id: str, ident: identity_type = Depends(current_identity)):
        wanted = str(batch_id or "").strip()
        if not wanted:
            raise HTTPException(400, "Chưa chọn bảng lương đã lưu cần chỉnh sửa.")

        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_history_edit")
            require_feature(conn, ident, "payroll_save")
            records, _checksum, _updated = _payroll._payload(conn)
            batch_rows = [
                dict(item) for item in records
                if str(item.get("Mã bản lưu") or "").strip() == wanted
            ]
            if not batch_rows:
                raise HTTPException(404, "Không tìm thấy bảng lương đã lưu hoặc bảng lương đã bị xóa.")

            start, end = _period_dates(batch_rows)
            if not start or not end:
                row = conn.execute(
                    text("""
                        SELECT period_start,period_end
                        FROM payroll_history_rows
                        WHERE batch_id=:batch
                        ORDER BY saved_at DESC,id DESC
                        LIMIT 1
                    """),
                    {"batch": wanted},
                ).first()
                if row:
                    start, end = row[0], row[1]
            if not start or not end:
                raise HTTPException(400, "Bảng lương đã lưu không có ngày kỳ lương hợp lệ.")

            label = _payroll._period_label(start, end)
            if label != wanted:
                raise HTTPException(400, "Tên kỳ lương và ngày kỳ lương không khớp nhau.")

            clean_rows = _payroll._clean_draft_rows(conn, batch_rows, norm)
            _payroll._put_setting(conn, _payroll._draft_key(start, end), {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "source_name": f"Chỉnh sửa từ {wanted}",
                "rows": clean_rows,
            }, ident.employee_username)
            draft = _payroll._saved_draft(conn, start, end)

        return {
            "ok": True,
            "release": PAYROLL_SAVED_EDIT_RELEASE,
            "batch": wanted,
            "month": f"{start.year:04d}-{start.month:02d}",
            "period_no": 1 if start.day == 1 else 2,
            "draft": draft,
            "message": (
                f"Đã mở {wanted} để chỉnh sửa. Sau khi sửa, bấm Hoàn thành bảng lương "
                "để cập nhật lại bản đã lưu."
            ),
        }

    app.state.payroll_saved_edit_installed = True
    app.state.payroll_saved_edit_release = PAYROLL_SAVED_EDIT_RELEASE

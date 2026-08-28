"""Admin approval workflow for Phép năm / Nghỉ làm đẹp / Nghỉ việc.

The Web V2 approval panel works on the same Phase-14 PostgreSQL records and
NghiDaiHan compatibility worksheet as the legacy application.  Approving an
annual-leave request additionally creates the daily ``Nghỉ Phép năm`` rows
through the canonical shared leave validator so annual quota and duplicate
rules cannot diverge from normal leave registration.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from typing import Any, Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_web_v2_long_leave import (
    LONG_LEAVE_DATASET,
    LONG_LEAVE_HEADERS,
    REQUEST_TYPE_ANNUAL,
    REQUEST_TYPE_RESIGNATION,
    STATUS_APPROVED,
    STATUS_PENDING,
    _display_request_type,
    _parse_vn_date,
    _payload_value,
    _worksheet,
)


LONG_LEAVE_ADMIN_RELEASE = "long-leave-admin-approval-v1"
STATUS_REJECTED = "Không duyệt"


class LongLeaveDecision(BaseModel):
    decision: str = Field(min_length=1, max_length=30)
    rejection_reason: str = Field(default="", max_length=2000)


def _require_admin(ident) -> None:
    if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
        raise HTTPException(403, "Chỉ Admin được duyệt Phép năm / Nghỉ làm đẹp / Nghỉ việc.")


def _request_row(conn, request_id: str, *, lock: bool = False):
    suffix = " FOR UPDATE" if lock else ""
    return conn.execute(text("""
        SELECT logical_id, source_row, employee_key, record_type, record_status,
               date_from, date_to, payload, revision, updated_at
        FROM vera_phase14_record
        WHERE dataset=:dataset AND logical_id=:logical_id
        LIMIT 1
    """ + suffix), {
        "dataset": LONG_LEAVE_DATASET,
        "logical_id": f"long:{str(request_id or '').strip()}",
    }).mappings().first()


def _date_text(value: Any) -> str:
    parsed = _parse_vn_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else ""


def _sheet_request_row(ws, request_id: str, source_row: Any) -> tuple[int, list[list[str]]]:
    values = ws.get_all_values()
    try:
        row_number = int(source_row or 0)
    except Exception:
        row_number = 0
    if 2 <= row_number <= len(values):
        candidate = values[row_number - 1][0] if values[row_number - 1] else ""
        if str(candidate or "").strip() == request_id:
            return row_number, values
    for index, row in enumerate(values[1:], start=2):
        if str(row[0] if row else "").strip() == request_id:
            return index, values
    raise RuntimeError(f"Không tìm thấy đơn {request_id} trong NghiDaiHan để đồng bộ.")


def _pending_rows(conn) -> list[dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT logical_id, source_row, employee_key, record_type, record_status,
               date_from, date_to, payload, updated_at
        FROM vera_phase14_record
        WHERE dataset=:dataset AND record_status=:pending
        ORDER BY updated_at, source_row NULLS LAST
        LIMIT 500
    """), {"dataset": LONG_LEAVE_DATASET, "pending": STATUS_PENDING}).mappings().all()

    employees = conn.execute(text("""
        SELECT username, COALESCE(full_name,'') full_name, COALESCE(email,'') email,
               employment_start_date, COALESCE(annual_leave,0) annual_leave
        FROM employees
    """)).mappings().all()
    by_employee = {str(row["username"] or "").strip().casefold(): dict(row) for row in employees}
    output = []
    for raw in rows:
        row = dict(raw)
        payload = _payload_value(row.get("payload"))
        request_id = str(payload.get("ID") or str(row.get("logical_id") or "").split(":", 1)[-1]).strip()
        employee = str(payload.get("Tên nhân viên") or "").strip()
        profile = by_employee.get(employee.casefold(), {})
        start = _parse_vn_date(row.get("date_from") or payload.get("Từ ngày"))
        end = _parse_vn_date(row.get("date_to") or payload.get("Đến ngày"))
        days = (end - start).days + 1 if start and end and end >= start else 0
        output.append({
            "id": request_id,
            "employee_name": employee,
            "full_name": str(profile.get("full_name") or ""),
            "email": str(profile.get("email") or ""),
            "role": str(payload.get("Vai trò") or ""),
            "request_type": _display_request_type(row.get("record_type") or payload.get("Loại đơn") or ""),
            "start_date": start.isoformat() if start else "",
            "end_date": end.isoformat() if end else "",
            "days": days,
            "reason": str(payload.get("Lý do nghỉ dài hạn") or ""),
            "detail": str(payload.get("Chi tiết") or ""),
            "submitted_date": str(payload.get("Ngày gửi") or ""),
            "submitted_time": str(payload.get("Giờ gửi") or ""),
            "source": str(payload.get("Nguồn") or ""),
            "email_cc": str(payload.get("Email CC") or ""),
            "document_json": str(payload.get("Tài liệu JSON") or ""),
            "document_reminder": str(payload.get("Nhắc tải tài liệu") or ""),
            "employment_start_date": _date_text(profile.get("employment_start_date")),
            "annual_leave_balance": float(profile.get("annual_leave") or 0),
        })
    return output


def install_long_leave_admin_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    identity_type,
    norm: Callable[[Any], str],
    google_client: Callable[[], Any],
    leave_sheet_id: str,
    vn_tz,
    validate_and_prepare: Callable[..., Any],
    leave_create_type,
    sheet_row_for_record: Callable[..., Any],
    insert_record: Callable[..., Any],
) -> None:
    if getattr(app.state, "long_leave_admin_routes_installed", False):
        return

    @app.get("/v2/long-leave/admin/health")
    def long_leave_admin_health():
        return {"ok": True, "release": LONG_LEAVE_ADMIN_RELEASE}

    @app.get("/v2/long-leave/admin/pending")
    def pending_long_leave_requests(ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        with engine_instance().connect() as conn:
            rows = _pending_rows(conn)
        return {"ok": True, "release": LONG_LEAVE_ADMIN_RELEASE, "requests": rows, "count": len(rows)}

    @app.post("/v2/long-leave/admin/requests/{request_id}/decision")
    def decide_long_leave_request(
        request_id: str,
        body: LongLeaveDecision,
        ident: identity_type = Depends(current_identity),
    ):
        _require_admin(ident)
        decision_key = norm(body.decision)
        approve = decision_key in {norm("approve"), norm("duyệt"), norm("Đã duyệt")}
        reject = decision_key in {norm("reject"), norm("không duyệt"), norm("từ chối")}
        if not approve and not reject:
            raise HTTPException(400, "Quyết định chỉ được là Duyệt hoặc Không duyệt.")
        rejection_reason = str(body.rejection_reason or "").strip()
        if reject and not rejection_reason:
            raise HTTPException(400, "Vui lòng nhập lý do không duyệt.")

        request_id = str(request_id or "").strip()
        if not request_id:
            raise HTTPException(400, "Mã yêu cầu đang trống.")

        conn = engine_instance().connect()
        tx = conn.begin()
        request_ws = None
        request_sheet_row = 0
        request_backup: list[Any] | None = None
        leave_ws = None
        inserted_leave_rows: list[int] = []
        annual_created = 0
        try:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase14:long_leave'))"))
            row = _request_row(conn, request_id, lock=True)
            if not row:
                raise HTTPException(404, "Không tìm thấy đơn cần duyệt.")
            row = dict(row)
            if str(row.get("record_status") or "").strip() != STATUS_PENDING:
                raise HTTPException(409, f"Đơn {request_id} không còn ở trạng thái Chờ duyệt.")

            payload = _payload_value(row.get("payload"))
            employee = str(payload.get("Tên nhân viên") or "").strip()
            request_type = str(row.get("record_type") or payload.get("Loại đơn") or "").strip()
            start_date = _parse_vn_date(row.get("date_from") or payload.get("Từ ngày"))
            end_date = _parse_vn_date(row.get("date_to") or payload.get("Đến ngày"))
            if not employee or not start_date or not end_date:
                raise HTTPException(409, "Đơn thiếu Tên nhân viên hoặc khoảng ngày; chưa thể duyệt an toàn.")

            now = datetime.now(vn_tz)
            next_status = STATUS_APPROVED if approve else STATUS_REJECTED
            payload["Trạng thái"] = next_status
            payload["Lý do không duyệt"] = "" if approve else rejection_reason
            payload["Người duyệt"] = ident.employee_username
            payload["Ngày duyệt"] = now.strftime("%d/%m/%Y")
            payload["Giờ duyệt"] = now.strftime("%H:%M:%S")
            payload["Người cập nhật"] = ident.employee_username
            payload["Cập nhật lúc"] = now.strftime("%d/%m/%Y %H:%M:%S")

            # Mirror the decision to the exact legacy NghiDaiHan row before the
            # PostgreSQL transaction commits.  On any later failure we restore it.
            request_ws = _worksheet(google_client, leave_sheet_id)
            request_sheet_row, request_values = _sheet_request_row(request_ws, request_id, row.get("source_row"))
            old_row = request_values[request_sheet_row - 1] if request_sheet_row <= len(request_values) else []
            request_backup = list(old_row[:len(LONG_LEAVE_HEADERS)]) + [""] * max(0, len(LONG_LEAVE_HEADERS) - len(old_row))
            request_ws.update(
                range_name=f"A{request_sheet_row}:W{request_sheet_row}",
                values=[[payload.get(header, "") for header in LONG_LEAVE_HEADERS]],
                value_input_option="USER_ENTERED",
            )

            if approve and norm(request_type) == norm(REQUEST_TYPE_ANNUAL):
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
                leave_ws = google_client().open_by_key(leave_sheet_id).get_worksheet(0)
                cursor = start_date
                while cursor <= end_date:
                    request_body = leave_create_type(
                        leave_date=cursor,
                        employee_name=employee,
                        leave_reason=REQUEST_TYPE_ANNUAL,
                        detail=f"Phép năm được Admin duyệt từ đơn {request_id}",
                    )
                    record, _warnings = validate_and_prepare(
                        conn,
                        request_body,
                        ident,
                        skip_registration_timing=True,
                    )
                    sheet_row, row_values = sheet_row_for_record(leave_ws, record)
                    insert_record(conn, record, sheet_row)
                    leave_ws.update(
                        range_name=f"A{sheet_row}:M{sheet_row}",
                        values=[row_values],
                        value_input_option="USER_ENTERED",
                    )
                    inserted_leave_rows.append(int(sheet_row))
                    annual_created += 1
                    cursor += timedelta(days=1)

            conn.execute(text("""
                UPDATE vera_phase14_record
                SET record_status=:status,
                    payload=CAST(:payload AS jsonb),
                    updated_by=:updated_by,
                    revision=revision + 1,
                    updated_at=NOW()
                WHERE dataset=:dataset AND logical_id=:logical_id
            """), {
                "status": next_status,
                "payload": json.dumps(payload, ensure_ascii=False),
                "updated_by": ident.employee_username,
                "dataset": LONG_LEAVE_DATASET,
                "logical_id": f"long:{request_id}",
            })
            tx.commit()
            return {
                "ok": True,
                "release": LONG_LEAVE_ADMIN_RELEASE,
                "request_id": request_id,
                "status": next_status,
                "annual_leave_rows_created": annual_created,
                "message": (
                    f"Đã duyệt đơn {request_id}."
                    if approve else f"Đã không duyệt đơn {request_id}."
                ),
            }
        except HTTPException:
            if tx.is_active:
                tx.rollback()
            if leave_ws is not None and inserted_leave_rows:
                for row_number in sorted(inserted_leave_rows, reverse=True):
                    try:
                        leave_ws.delete_rows(row_number)
                    except Exception:
                        pass
            if request_ws is not None and request_sheet_row >= 2 and request_backup is not None:
                try:
                    request_ws.update(
                        range_name=f"A{request_sheet_row}:W{request_sheet_row}",
                        values=[request_backup],
                        value_input_option="USER_ENTERED",
                    )
                except Exception:
                    pass
            raise
        except Exception as exc:
            if tx.is_active:
                tx.rollback()
            if leave_ws is not None and inserted_leave_rows:
                for row_number in sorted(inserted_leave_rows, reverse=True):
                    try:
                        leave_ws.delete_rows(row_number)
                    except Exception:
                        pass
            if request_ws is not None and request_sheet_row >= 2 and request_backup is not None:
                try:
                    request_ws.update(
                        range_name=f"A{request_sheet_row}:W{request_sheet_row}",
                        values=[request_backup],
                        value_input_option="USER_ENTERED",
                    )
                except Exception:
                    pass
            raise HTTPException(500, f"Không duyệt được đơn an toàn: {type(exc).__name__}: {exc}") from exc
        finally:
            conn.close()

    app.state.long_leave_admin_routes_installed = True
    app.state.long_leave_admin_release = LONG_LEAVE_ADMIN_RELEASE

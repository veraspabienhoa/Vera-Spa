"""Annual-leave and long-leave request routes for VERA SPA Web V2.

The existing Phase-14 ``long_leave`` dataset in PostgreSQL remains canonical.
Every successful request is mirrored synchronously to the legacy ``NghiDaiHan``
worksheet so the current Streamlit approval workflow keeps seeing the same data.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
import json
import os
import re
import secrets
import smtplib
import time
import hashlib
from typing import Any, Callable

import gspread
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text


LONG_LEAVE_DATASET = "long_leave"
LONG_LEAVE_WORKSHEET = "NghiDaiHan"
LONG_LEAVE_HEADERS = [
    "ID", "Tên nhân viên", "Vai trò", "Từ ngày", "Đến ngày",
    "Lý do nghỉ dài hạn", "Chi tiết", "Trạng thái", "Lý do không duyệt",
    "Ngày gửi", "Giờ gửi", "Người duyệt", "Ngày duyệt", "Giờ duyệt",
    "Nguồn", "Người cập nhật", "Cập nhật lúc", "Tài liệu JSON",
    "Nhắc tải tài liệu", "Ngày nhắc", "Người nhắc", "Email CC", "Loại đơn",
]
REQUEST_TYPE_LONG = "Nghỉ dài hạn"
REQUEST_TYPE_ANNUAL = "Nghỉ Phép năm"
STATUS_PENDING = "Chờ duyệt"
STATUS_APPROVED = "Đã duyệt"
PAUSE_KEY = "long_leave_request_pause_v905"
PAUSE_WORKSHEET = "CauHinhGiaoDien"
DEFAULT_PAUSE_MESSAGE = "Admin đang tạm dừng nhận đơn Nghỉ dài hạn và Nghỉ Phép năm."
ADMIN_EMAIL = "veraspabienhoa@gmail.com"


class LongLeaveRequestCreate(BaseModel):
    request_type: str = Field(min_length=1, max_length=80)
    start_date: date
    end_date: date
    reason: str = Field(default="", max_length=1000)
    detail: str = Field(default="", max_length=5000)


def _parse_vn_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + value.month - 1 + int(months)
    year, month_zero = divmod(total, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _request_type(value: Any, norm: Callable[[Any], str]) -> str:
    key = norm(value)
    if key == norm(REQUEST_TYPE_ANNUAL):
        return REQUEST_TYPE_ANNUAL
    if key == norm(REQUEST_TYPE_LONG):
        return REQUEST_TYPE_LONG
    raise HTTPException(400, "Loại đơn chỉ được chọn Nghỉ Phép năm hoặc Nghỉ dài hạn.")


def _request_id(employee: str, request_type: str, now: datetime) -> str:
    raw = f"{employee}|{request_type}|{now.isoformat()}|{secrets.token_hex(4)}"
    prefix = "AL-" if request_type == REQUEST_TYPE_ANNUAL else "LL-"
    return prefix + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12].upper()


def _payload_value(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    try:
        parsed = json.loads(str(payload or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _active_request(rows: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    active = []
    for row in rows:
        payload = _payload_value(row.get("payload"))
        status = str(row.get("record_status") or payload.get("Trạng thái") or "").strip()
        if status not in {STATUS_PENDING, STATUS_APPROVED}:
            continue
        end_date = _parse_vn_date(row.get("date_to") or payload.get("Đến ngày"))
        if end_date is not None and end_date < today:
            continue
        start_date = _parse_vn_date(row.get("date_from") or payload.get("Từ ngày"))
        active.append((start_date or date.min, row, payload))
    if not active:
        return None
    _, row, payload = sorted(active, key=lambda item: item[0], reverse=True)[0]
    return {
        "id": str(payload.get("ID") or str(row.get("logical_id") or "").split(":", 1)[-1]),
        "request_type": str(row.get("record_type") or payload.get("Loại đơn") or REQUEST_TYPE_LONG),
        "start_date": _parse_vn_date(row.get("date_from") or payload.get("Từ ngày")),
        "end_date": _parse_vn_date(row.get("date_to") or payload.get("Đến ngày")),
        "status": str(row.get("record_status") or payload.get("Trạng thái") or ""),
    }


def _eligibility(conn, employee: str, today: date, norm: Callable[[Any], str]) -> dict[str, Any]:
    employee_row = conn.execute(text("""
        SELECT username, employment_start_date
        FROM employees
        WHERE lower(btrim(username))=lower(btrim(:username))
          AND COALESCE(login_locked, false)=false
        LIMIT 1
    """), {"username": employee}).mappings().first()
    if not employee_row:
        return {"allowed": False, "message": "Không tìm thấy hồ sơ nhân viên đang hoạt động.", "employment_start_date": None}

    start_work = _parse_vn_date(employee_row.get("employment_start_date"))
    if start_work is None:
        return {
            "allowed": False,
            "message": "Hồ sơ chưa có Ngày bắt đầu làm. Vui lòng liên hệ Admin cập nhật trước khi tạo đơn.",
            "employment_start_date": None,
        }
    eligible_on = _add_months(start_work, 3)
    if today < eligible_on:
        return {
            "allowed": False,
            "message": (
                f"Chưa đủ 3 tháng làm việc. Ngày bắt đầu làm: {start_work.strftime('%d/%m/%Y')} · "
                f"được tạo đơn từ {eligible_on.strftime('%d/%m/%Y')}."
            ),
            "employment_start_date": start_work.isoformat(),
        }

    rows = conn.execute(text("""
        SELECT logical_id, record_type, record_status, date_from, date_to, payload
        FROM vera_phase14_record
        WHERE dataset=:dataset
          AND lower(btrim(COALESCE(payload->>'Tên nhân viên','')))=lower(btrim(:employee))
        ORDER BY updated_at DESC, source_row DESC NULLS LAST
    """), {"dataset": LONG_LEAVE_DATASET, "employee": employee}).mappings().all()
    active = _active_request([dict(row) for row in rows], today)
    if active:
        start_text = active["start_date"].strftime("%d/%m/%Y") if active["start_date"] else ""
        end_text = active["end_date"].strftime("%d/%m/%Y") if active["end_date"] else ""
        return {
            "allowed": False,
            "message": (
                f"Bạn đang có {active['request_type']} {active['id']} "
                f"({start_text} → {end_text}) ở trạng thái {active['status']}. "
                "Mỗi lần chỉ được có 1 đơn Phép năm hoặc Nghỉ dài hạn đang hoạt động."
            ),
            "employment_start_date": start_work.isoformat(),
            "active_request": {
                **active,
                "start_date": active["start_date"].isoformat() if active["start_date"] else None,
                "end_date": active["end_date"].isoformat() if active["end_date"] else None,
            },
        }
    return {
        "allowed": True,
        "message": f"Đủ điều kiện tạo đơn · Ngày bắt đầu làm {start_work.strftime('%d/%m/%Y')}.",
        "employment_start_date": start_work.isoformat(),
    }


_pause_cache: dict[str, Any] = {"at": 0.0, "value": None}


def _pause_state(google_client: Callable[[], Any], leave_sheet_id: str) -> dict[str, Any]:
    now = time.monotonic()
    if _pause_cache.get("value") is not None and now - float(_pause_cache.get("at") or 0) < 20:
        return dict(_pause_cache["value"])
    output = {"enabled": False, "message": DEFAULT_PAUSE_MESSAGE}
    try:
        ws = google_client().open_by_key(leave_sheet_id).worksheet(PAUSE_WORKSHEET)
        for row in ws.get_all_values()[1:]:
            if row and str(row[0]).strip() == PAUSE_KEY:
                raw = json.loads(str(row[1] or "{}")) if len(row) > 1 else {}
                if isinstance(raw, dict):
                    output["enabled"] = bool(raw.get("enabled", False))
                    output["message"] = str(raw.get("message") or DEFAULT_PAUSE_MESSAGE).strip()
                break
    except Exception:
        # Match the current app: a configuration read failure does not invent a pause.
        pass
    _pause_cache.update({"at": now, "value": dict(output)})
    return output


def _approved_rows(conn) -> list[dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT logical_id, record_type, record_status, date_from, date_to,
               payload, updated_at
        FROM vera_phase14_record
        WHERE dataset=:dataset AND record_status=:approved
        ORDER BY
          CASE WHEN to_date(NULLIF(date_from,''), 'DD/MM/YYYY') >= CURRENT_DATE THEN 0 ELSE 1 END,
          to_date(NULLIF(date_from,''), 'DD/MM/YYYY') DESC NULLS LAST,
          source_row DESC NULLS LAST
        LIMIT 300
    """), {"dataset": LONG_LEAVE_DATASET, "approved": STATUS_APPROVED}).mappings().all()
    output = []
    for row in rows:
        payload = _payload_value(row.get("payload"))
        start_date = _parse_vn_date(row.get("date_from") or payload.get("Từ ngày"))
        end_date = _parse_vn_date(row.get("date_to") or payload.get("Đến ngày"))
        days = (end_date - start_date).days + 1 if start_date and end_date and end_date >= start_date else 0
        request_type = str(row.get("record_type") or payload.get("Loại đơn") or REQUEST_TYPE_LONG).strip()
        output.append({
            "id": str(payload.get("ID") or str(row.get("logical_id") or "").split(":", 1)[-1]),
            "employee_name": str(payload.get("Tên nhân viên") or "").strip(),
            "request_type": request_type or REQUEST_TYPE_LONG,
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
            "days": days,
            "reason": str(payload.get("Lý do nghỉ dài hạn") or "").strip(),
            "detail": str(payload.get("Chi tiết") or "").strip(),
            "status": STATUS_APPROVED,
            "approved_by": str(payload.get("Người duyệt") or "").strip(),
            "approved_date": str(payload.get("Ngày duyệt") or "").strip(),
        })
    return output


def _cc_emails(conn) -> list[str]:
    rows = conn.execute(text("""
        SELECT email
        FROM employees
        WHERE lower(COALESCE(role,'')) IN ('quanly','letan','leader')
          AND COALESCE(login_locked,false)=false
          AND position('@' in COALESCE(email,'')) > 1
    """)).scalars().all()
    return sorted({str(value or "").strip() for value in rows if str(value or "").strip()})


def _worksheet(google_client: Callable[[], Any], leave_sheet_id: str):
    spreadsheet = google_client().open_by_key(leave_sheet_id)
    try:
        ws = spreadsheet.worksheet(LONG_LEAVE_WORKSHEET)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=LONG_LEAVE_WORKSHEET,
            rows=2000,
            cols=len(LONG_LEAVE_HEADERS),
        )
    if int(getattr(ws, "col_count", 0) or 0) < len(LONG_LEAVE_HEADERS):
        ws.resize(cols=len(LONG_LEAVE_HEADERS))
    header = ws.row_values(1)
    if header[:len(LONG_LEAVE_HEADERS)] != LONG_LEAVE_HEADERS:
        ws.update(
            range_name=f"A1:W1",
            values=[LONG_LEAVE_HEADERS],
            value_input_option="USER_ENTERED",
        )
    return ws


def _appended_row_number(response: Any, fallback: int) -> int:
    try:
        updated_range = str((response or {}).get("updates", {}).get("updatedRange") or "")
        match = re.search(r"![A-Z]+(\d+):[A-Z]+(\d+)$", updated_range)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return int(fallback)


def _send_email(payload: dict[str, Any], cc_emails: list[str]) -> tuple[bool, str]:
    sender = str(os.getenv("SMTP_SENDER_EMAIL", ADMIN_EMAIL) or ADMIN_EMAIL).strip()
    password = str(os.getenv("SMTP_APP_PASSWORD", "") or "").strip()
    if not password:
        return False, "Máy chủ chưa cấu hình SMTP; đơn vẫn đã được lưu để Admin duyệt."
    request_type = str(payload.get("Loại đơn") or REQUEST_TYPE_LONG)
    subject = (
        f"[VERA SPA] Đơn xin {request_type} - {payload.get('Tên nhân viên','')} - "
        f"{payload.get('Từ ngày','')} đến {payload.get('Đến ngày','')}"
    )
    detail = html.escape(str(payload.get("Chi tiết") or "")).replace("\n", "<br>")
    body = f"""
    <html><body style="font-family:Arial,sans-serif">
      <h3>Đơn xin {html.escape(request_type)}</h3>
      <p><b>Mã yêu cầu:</b> {html.escape(str(payload.get('ID') or ''))}</p>
      <p><b>Nhân viên:</b> {html.escape(str(payload.get('Tên nhân viên') or ''))}</p>
      <p><b>Vai trò:</b> {html.escape(str(payload.get('Vai trò') or ''))}</p>
      <p><b>Thời gian:</b> {html.escape(str(payload.get('Từ ngày') or ''))} - {html.escape(str(payload.get('Đến ngày') or ''))}</p>
      <p><b>Nội dung:</b> {html.escape(str(payload.get('Lý do nghỉ dài hạn') or ''))}</p>
      <p><b>Chi tiết:</b><br>{detail}</p>
      <p>Yêu cầu đang chờ Admin duyệt trên hệ thống VERA SPA.</p>
    </body></html>
    """
    recipients = [ADMIN_EMAIL] + [email for email in cc_emails if email.casefold() != ADMIN_EMAIL.casefold()]
    message = MIMEMultipart()
    message["From"] = f"Vera Spa <{sender}>"
    message["To"] = ADMIN_EMAIL
    if len(recipients) > 1:
        message["Cc"] = ", ".join(recipients[1:])
    message["Subject"] = subject
    message.attach(MIMEText(body, "html", "utf-8"))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        server.starttls()
        server.login(sender, password)
        server.send_message(message, from_addr=sender, to_addrs=recipients)
        server.quit()
        return True, "Đã gửi email tới Admin và người phụ trách."
    except Exception as exc:
        return False, f"Đơn đã lưu nhưng email chưa gửi được: {type(exc).__name__}."


def install_long_leave_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    feature_allowed: Callable[[Any, Any, str], bool],
    norm: Callable[[Any], str],
    google_client: Callable[[], Any],
    leave_sheet_id: str,
    identity_type,
    vn_tz,
):
    """Install leave-request routes into the authenticated Web V2 API."""

    def permissions(conn, ident) -> tuple[bool, bool, bool]:
        can_form = bool(feature_allowed(conn, ident, "long_leave_form"))
        can_stats = bool(feature_allowed(conn, ident, "long_leave_stats"))
        can_open = bool(feature_allowed(conn, ident, "long_leave")) or can_form or can_stats
        return can_open, can_form, can_stats

    @app.get("/v2/long-leave/overview")
    def long_leave_overview(ident: identity_type = Depends(current_identity)):
        today = datetime.now(vn_tz).date()
        with engine_instance().connect() as conn:
            can_open, can_form, can_stats = permissions(conn, ident)
            if not can_open:
                raise HTTPException(403, "Tài khoản hiện tại chưa được cấp quyền Phép năm / Nghỉ dài hạn.")
            eligibility = _eligibility(conn, ident.employee_username, today, norm) if can_form else {
                "allowed": False,
                "message": "Tài khoản chưa được cấp quyền gửi đơn.",
                "employment_start_date": None,
            }
            approved = _approved_rows(conn) if can_stats else []
        pause = _pause_state(google_client, leave_sheet_id)
        can_submit = can_form and bool(eligibility.get("allowed")) and not bool(pause.get("enabled"))
        return {
            "can_submit": can_submit,
            "can_view_approved": can_stats,
            "eligibility": eligibility,
            "paused": bool(pause.get("enabled")),
            "pause_message": str(pause.get("message") or DEFAULT_PAUSE_MESSAGE),
            "approved_requests": approved,
        }

    @app.post("/v2/long-leave/requests")
    def create_long_leave_request(
        body: LongLeaveRequestCreate,
        ident: identity_type = Depends(current_identity),
    ):
        request_type = _request_type(body.request_type, norm)
        today = datetime.now(vn_tz).date()
        if body.start_date < today:
            raise HTTPException(400, "Ngày bắt đầu không được là ngày trong quá khứ.")
        if body.end_date < body.start_date:
            raise HTTPException(400, "Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.")
        day_count = (body.end_date - body.start_date).days + 1
        if request_type == REQUEST_TYPE_ANNUAL and day_count > 7:
            raise HTTPException(400, "Đơn Phép năm chỉ được chọn tối đa 7 ngày liên tiếp.")
        reason = str(body.reason or "").strip()
        detail = str(body.detail or "").strip()
        if request_type == REQUEST_TYPE_LONG and not reason:
            raise HTTPException(400, "Vui lòng nhập Lý do nghỉ dài hạn.")
        if request_type == REQUEST_TYPE_LONG and not detail:
            raise HTTPException(400, "Vui lòng nhập Chi tiết lý do nghỉ dài hạn.")
        if request_type == REQUEST_TYPE_ANNUAL:
            reason = REQUEST_TYPE_ANNUAL

        pause = _pause_state(google_client, leave_sheet_id)
        if pause.get("enabled"):
            raise HTTPException(409, str(pause.get("message") or DEFAULT_PAUSE_MESSAGE))

        conn = engine_instance().connect()
        tx = conn.begin()
        worksheet = None
        appended_row = None
        payload: dict[str, Any] = {}
        cc_emails: list[str] = []
        try:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase14:long_leave'))"))
            can_open, can_form, _can_stats = permissions(conn, ident)
            if not can_open or not can_form:
                raise HTTPException(403, "Tài khoản hiện tại chưa được cấp quyền gửi đơn.")
            eligibility = _eligibility(conn, ident.employee_username, today, norm)
            if not eligibility.get("allowed"):
                raise HTTPException(409, str(eligibility.get("message") or "Chưa đủ điều kiện tạo đơn."))

            now = datetime.now(vn_tz)
            request_id = _request_id(ident.employee_username, request_type, now)
            cc_emails = _cc_emails(conn)
            payload = {
                "ID": request_id,
                "Tên nhân viên": ident.employee_username.strip(),
                "Vai trò": str(ident.role or "").strip().lower(),
                "Từ ngày": body.start_date.strftime("%d/%m/%Y"),
                "Đến ngày": body.end_date.strftime("%d/%m/%Y"),
                "Lý do nghỉ dài hạn": reason,
                "Chi tiết": detail,
                "Trạng thái": STATUS_PENDING,
                "Lý do không duyệt": "",
                "Ngày gửi": now.strftime("%d/%m/%Y"),
                "Giờ gửi": now.strftime("%H:%M:%S"),
                "Người duyệt": "",
                "Ngày duyệt": "",
                "Giờ duyệt": "",
                "Nguồn": "Web V2 gửi yêu cầu" if request_type == REQUEST_TYPE_LONG else "Web V2 gửi yêu cầu Phép năm",
                "Người cập nhật": ident.employee_username.strip(),
                "Cập nhật lúc": now.strftime("%d/%m/%Y %H:%M:%S"),
                "Tài liệu JSON": "",
                "Nhắc tải tài liệu": "",
                "Ngày nhắc": "",
                "Người nhắc": "",
                "Email CC": ", ".join(cc_emails),
                "Loại đơn": request_type,
            }

            worksheet = _worksheet(google_client, leave_sheet_id)
            fallback_row = len(worksheet.get_all_values()) + 1
            response = worksheet.append_row(
                [payload.get(header, "") for header in LONG_LEAVE_HEADERS],
                value_input_option="USER_ENTERED",
            )
            appended_row = _appended_row_number(response, fallback_row)
            payload["__row"] = appended_row

            conn.execute(text("""
                INSERT INTO vera_phase14_record(
                    dataset, logical_id, source_row, employee_key, record_type,
                    record_status, date_from, date_to, payload, source,
                    updated_by, revision, updated_at
                ) VALUES (
                    :dataset, :logical_id, :source_row, :employee_key, :record_type,
                    :record_status, :date_from, :date_to, CAST(:payload AS jsonb),
                    :source, :updated_by, 1, NOW()
                )
            """), {
                "dataset": LONG_LEAVE_DATASET,
                "logical_id": f"long:{request_id}",
                "source_row": appended_row,
                "employee_key": norm(ident.employee_username),
                "record_type": request_type,
                "record_status": STATUS_PENDING,
                "date_from": payload["Từ ngày"],
                "date_to": payload["Đến ngày"],
                "payload": json.dumps(payload, ensure_ascii=False),
                "source": "postgres_primary_confirmed",
                "updated_by": ident.employee_username,
            })
            conn.execute(text("""
                INSERT INTO vera_phase14_dataset_state(dataset, seeded, source, revision, updated_at)
                VALUES (:dataset, true, 'postgres_primary_confirmed', 1, NOW())
                ON CONFLICT (dataset) DO UPDATE
                SET seeded=true, source=EXCLUDED.source,
                    revision=vera_phase14_dataset_state.revision + 1,
                    updated_at=NOW()
            """), {"dataset": LONG_LEAVE_DATASET})
            tx.commit()
        except HTTPException:
            if tx.is_active:
                tx.rollback()
            if worksheet is not None and appended_row:
                try:
                    worksheet.delete_rows(int(appended_row))
                except Exception:
                    pass
            raise
        except Exception as exc:
            if tx.is_active:
                tx.rollback()
            if worksheet is not None and appended_row:
                try:
                    worksheet.delete_rows(int(appended_row))
                except Exception:
                    pass
            raise HTTPException(
                500,
                f"Không gửi được đơn an toàn: {type(exc).__name__}: {exc}",
            ) from exc
        finally:
            conn.close()

        email_ok, email_message = _send_email(payload, cc_emails)
        return {
            "ok": True,
            "message": f"Đã gửi đơn {request_type} THÀNH CÔNG.",
            "request_id": str(payload.get("ID") or ""),
            "email_sent": email_ok,
            "warnings": [] if email_ok else [email_message],
        }

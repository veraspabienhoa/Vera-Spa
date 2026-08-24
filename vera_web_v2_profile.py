"""Self-service employee profile and legacy-login password updates."""
from __future__ import annotations

from datetime import datetime
import hmac
import json
import os
from typing import Any, Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text


CREDENTIAL_SHEET_ID = os.getenv(
    "VERA_CREDENTIAL_SHEET_ID", "1DGXy3kPyMPwtz-3CnG8i6BiQbXFDApasoXVFzSmUe24"
)
HEADERS = [
    "STT", "Tên nhân viên", "Mật khẩu", "Phân quyền", "Họ và tên đầy đủ", "Ngày sinh",
    "Điện thoại", "Email", "Địa chỉ", "Số tài khoản ngân hàng", "Tên ngân hàng",
    "Phát sinh tháng", "Có phép tháng", "Phép năm", "Ca làm việc", "Ngày bắt đầu ca",
    "Chu kỳ", "Khóa đăng nhập", "Remember Token Hash", "Remember Token Expiry", "Ngày bắt đầu làm",
]


class ProfileUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=300)
    new_password: str = Field(default="", max_length=300)
    full_name: str = Field(default="", max_length=300)
    birth_date: str = Field(default="", max_length=30)
    phone: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=300)
    address: str = Field(default="", max_length=1000)
    bank_account: str = Field(default="", max_length=100)
    bank_name: str = Field(default="", max_length=300)


def _date_text(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    raise HTTPException(400, "Ngày sinh không hợp lệ. Dùng định dạng DD/MM/YYYY.")


def _credential_values(row: dict[str, Any]) -> list[Any]:
    return [
        row.get("stt") or "", row.get("username") or "", row.get("password_value") or "",
        row.get("role") or "", row.get("full_name") or "", row.get("birth_date") or "",
        row.get("phone") or "", row.get("email") or "", row.get("address") or "",
        row.get("bank_account") or "", row.get("bank_name") or "", float(row.get("monthly_generated") or 0),
        float(row.get("monthly_leave") or 0), float(row.get("annual_leave") or 0), row.get("work_shift") or "",
        row.get("shift_start_date") or "", row.get("rotation_cycle") or "",
        "TRUE" if row.get("login_locked") else "FALSE", row.get("remember_token_hash") or "",
        row.get("remember_token_expiry") or "", row.get("employment_start_date") or "",
    ]


def install_profile_routes(
    app, *, engine_instance: Callable[[], Any], current_identity,
    require_feature: Callable[[Any, Any, str], None], google_client: Callable[[], Any], identity_type,
):
    @app.get("/v2/profile")
    def get_profile(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "profile")
            row = conn.execute(text("""
                SELECT username, COALESCE(full_name,'') full_name, COALESCE(birth_date,'') birth_date,
                       COALESCE(phone,'') phone, COALESCE(email,'') email, COALESCE(address,'') address,
                       COALESCE(bank_account,'') bank_account, COALESCE(bank_name,'') bank_name,
                       COALESCE(role,'') role, COALESCE(employment_start_date,'') employment_start_date
                FROM employees WHERE lower(btrim(username))=lower(btrim(:username)) LIMIT 1
            """), {"username": ident.employee_username}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy hồ sơ nhân viên.")
        return {"profile": dict(row)}

    @app.patch("/v2/profile")
    def update_profile(body: ProfileUpdate, ident: identity_type = Depends(current_identity)):
        new_password = str(body.new_password or "")
        if new_password and len(new_password) < 8:
            raise HTTPException(400, "Mật khẩu mới phải có ít nhất 8 ký tự.")
        birth_date = _date_text(body.birth_date)
        conn = engine_instance().connect()
        tx = conn.begin()
        ws = None
        source_row = 0
        backup: list[Any] | None = None
        try:
            require_feature(conn, ident, "profile_edit")
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:v2:profile:' || lower(:username)))"), {"username": ident.employee_username})
            current = conn.execute(text("""
                SELECT * FROM employees
                WHERE lower(btrim(username))=lower(btrim(:username))
                FOR UPDATE
            """), {"username": ident.employee_username}).mappings().first()
            if not current:
                raise HTTPException(404, "Không tìm thấy hồ sơ nhân viên.")
            if not hmac.compare_digest(str(current.get("password_value") or ""), str(body.current_password)):
                raise HTTPException(400, "Mật khẩu hiện tại không đúng.")

            updated = dict(current)
            updated.update({
                "full_name": body.full_name.strip(), "birth_date": birth_date, "phone": body.phone.strip(),
                "email": body.email.strip(), "address": body.address.strip(),
                "bank_account": body.bank_account.strip(), "bank_name": body.bank_name.strip(),
            })
            if new_password:
                updated.update({"password_value": new_password, "remember_token_hash": "", "remember_token_expiry": ""})
            payload = dict(updated.get("payload") or {})
            payload.update({
                "Họ và tên đầy đủ": updated["full_name"], "Ngày sinh": updated["birth_date"],
                "Điện thoại": updated["phone"], "Email": updated["email"], "Địa chỉ": updated["address"],
                "Số tài khoản ngân hàng": updated["bank_account"], "Tên ngân hàng": updated["bank_name"],
            })
            updated["payload"] = payload

            ws = google_client().open_by_key(CREDENTIAL_SHEET_ID).get_worksheet(0)
            values = ws.get_all_values()
            source_row = int(current.get("source_row") or 0)
            if source_row < 2 or source_row > len(values) or str(values[source_row - 1][1] if len(values[source_row - 1]) > 1 else "").strip().casefold() != ident.employee_username.strip().casefold():
                source_row = next((index for index, row in enumerate(values[1:], 2) if len(row) > 1 and str(row[1]).strip().casefold() == ident.employee_username.strip().casefold()), 0)
            if source_row < 2:
                raise RuntimeError("Không tìm thấy dòng hồ sơ tương ứng trong bảng tài khoản.")
            backup = list(values[source_row - 1][:len(HEADERS)])
            ws.update(range_name=f"A{source_row}:U{source_row}", values=[_credential_values(updated)], value_input_option="USER_ENTERED")

            conn.execute(text("""
                UPDATE employees SET full_name=:full_name, birth_date=:birth_date, phone=:phone,
                    email=:email, address=:address, bank_account=:bank_account, bank_name=:bank_name,
                    password_value=:password_value, remember_token_hash=:remember_token_hash,
                    remember_token_expiry=:remember_token_expiry, payload=CAST(:payload AS jsonb), updated_at=NOW()
                WHERE username=:username
            """), {
                **{key: updated.get(key) for key in (
                    "username", "full_name", "birth_date", "phone", "email", "address", "bank_account", "bank_name",
                    "password_value", "remember_token_hash", "remember_token_expiry",
                )},
                "payload": json.dumps(payload, ensure_ascii=False),
            })
            conn.execute(text("""
                INSERT INTO vera_sync_event(dataset_key,event_type,detail,created_at)
                VALUES ('employees','profile_updated',:detail,NOW())
            """), {"detail": f"Web V2: {ident.employee_username} tự cập nhật hồ sơ" + (" và mật khẩu" if new_password else "")})
            tx.commit()
            return {"ok": True, "password_changed": bool(new_password), "message": "Đã cập nhật hồ sơ THÀNH CÔNG"}
        except HTTPException:
            if tx.is_active: tx.rollback()
            raise
        except Exception as exc:
            if tx.is_active: tx.rollback()
            if ws is not None and backup is not None and source_row:
                try:
                    ws.update(range_name=f"A{source_row}:U{source_row}", values=[backup], value_input_option="USER_ENTERED")
                except Exception:
                    pass
            raise HTTPException(500, f"Không cập nhật được hồ sơ an toàn: {type(exc).__name__}: {exc}") from exc
        finally:
            conn.close()

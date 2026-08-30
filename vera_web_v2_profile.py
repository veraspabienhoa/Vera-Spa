"""Self-service employee profile and password updates in PostgreSQL."""
from __future__ import annotations

from datetime import datetime
import hmac
import json
import time
from typing import Any, Callable

import requests
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_web_v2_security import password_policy_error


class ProfileUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=300)
    new_password: str = Field(default="", max_length=300)
    full_name: str = Field(default="", max_length=300)
    birth_date: str = Field(default="", max_length=30)
    phone: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=300)
    address: str = Field(default="", max_length=1000)
    province: str = Field(default="", max_length=200)
    ward: str = Field(default="", max_length=200)
    address_detail: str = Field(default="", max_length=700)
    bank_account: str = Field(default="", max_length=100)
    bank_name: str = Field(default="", max_length=300)


FALLBACK_PROVINCES = [
    "An Giang", "Bắc Ninh", "Cà Mau", "Cao Bằng", "Cần Thơ", "Đà Nẵng",
    "Đắk Lắk", "Điện Biên", "Đồng Nai", "Đồng Tháp", "Gia Lai", "Hà Nội",
    "Hà Tĩnh", "Hải Phòng", "Huế", "Hưng Yên", "Khánh Hòa", "Lai Châu",
    "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Nghệ An", "Ninh Bình", "Phú Thọ",
    "Quảng Ngãi", "Quảng Ninh", "Quảng Trị", "Sơn La", "Tây Ninh",
    "Thái Nguyên", "Thanh Hóa", "Thành phố Hồ Chí Minh", "Tuyên Quang", "Vĩnh Long",
]
FALLBACK_BANKS = [
    "Agribank", "Vietcombank", "VietinBank", "BIDV", "MB", "Techcombank",
    "ACB", "VPBank", "TPBank", "Sacombank", "HDBank", "VIB", "MSB",
    "SHB", "OCB", "SeABank", "Eximbank", "LPBank", "Nam A Bank", "PVcomBank",
    "Bac A Bank", "ABBank", "NCB", "VietABank", "VietBank", "KienlongBank",
    "Saigonbank", "BVBank", "BaoViet Bank", "PGBank", "GPBank", "Co-opBank",
    "Shinhan Bank Việt Nam", "Woori Bank Việt Nam", "UOB Việt Nam", "CIMB Việt Nam",
]
_reference_cache: dict[str, Any] = {"loaded_at": 0.0, "provinces": [], "banks": [], "wards": {}}


def _reference_catalogs() -> tuple[list[dict[str, Any]], list[str]]:
    if _reference_cache["provinces"] and time.monotonic() - float(_reference_cache["loaded_at"]) < 12 * 3600:
        return list(_reference_cache["provinces"]), list(_reference_cache["banks"])
    provinces: list[dict[str, Any]] = []
    banks: list[str] = []
    try:
        response = requests.get("https://provinces.open-api.vn/api/v2/", timeout=15)
        response.raise_for_status()
        provinces = [
            {"code": int(item["code"]), "name": str(item["name"]).strip()}
            for item in response.json() if item.get("code") is not None and str(item.get("name") or "").strip()
        ]
    except Exception:
        provinces = [{"code": -(index + 1), "name": name} for index, name in enumerate(FALLBACK_PROVINCES)]
    try:
        response = requests.get("https://api.vietqr.io/v2/banks", timeout=15)
        response.raise_for_status()
        banks = sorted({
            str(item.get("shortName") or item.get("name") or "").strip()
            for item in (response.json().get("data") or [])
            if str(item.get("shortName") or item.get("name") or "").strip()
        }, key=str.casefold)
    except Exception:
        banks = list(FALLBACK_BANKS)
    _reference_cache.update({"loaded_at": time.monotonic(), "provinces": provinces, "banks": banks})
    return list(provinces), list(banks)


def _wards(province_code: int) -> list[str]:
    cached = _reference_cache["wards"].get(province_code)
    if cached is not None:
        return list(cached)
    if province_code < 0:
        return []
    try:
        response = requests.get(f"https://provinces.open-api.vn/api/v2/p/{province_code}", params={"depth": 2}, timeout=15)
        response.raise_for_status()
        values = sorted({
            str(item.get("name") or "").strip()
            for item in (response.json().get("wards") or []) if str(item.get("name") or "").strip()
        }, key=str.casefold)
    except Exception:
        values = []
    _reference_cache["wards"][province_code] = values
    return list(values)


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


def install_profile_routes(
    app, *, engine_instance: Callable[[], Any], current_identity,
    require_feature: Callable[[Any, Any, str], None], identity_type,
):
    @app.get("/v2/profile")
    def get_profile(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "profile")
            row = conn.execute(text("""
                SELECT username, COALESCE(full_name,'') full_name, COALESCE(birth_date,'') birth_date,
                       COALESCE(phone,'') phone, COALESCE(email,'') email, COALESCE(address,'') address,
                       COALESCE(bank_account,'') bank_account, COALESCE(bank_name,'') bank_name,
                       COALESCE(role,'') role, COALESCE(employment_start_date,'') employment_start_date,
                       COALESCE(payload,'{}'::jsonb) payload
                FROM employees WHERE lower(btrim(username))=lower(btrim(:username)) LIMIT 1
            """), {"username": ident.employee_username}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy hồ sơ nhân viên.")
        profile = dict(row)
        payload = profile.pop("payload", {}) if isinstance(profile.get("payload"), dict) else {}
        profile.update({
            "province": str(payload.get("Tỉnh/Thành phố") or ""),
            "ward": str(payload.get("Xã/Phường") or ""),
            "address_detail": str(payload.get("Địa chỉ chi tiết") or profile.get("address") or ""),
        })
        return {"profile": profile}

    @app.get("/v2/profile/reference-data")
    def profile_reference_data(
        province_code: int | None = Query(default=None),
        ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "profile")
        provinces, banks = _reference_catalogs()
        return {
            "provinces": provinces,
            "banks": banks,
            "wards": _wards(province_code) if province_code is not None else [],
            "province_code": province_code,
        }

    @app.patch("/v2/profile")
    def update_profile(body: ProfileUpdate, ident: identity_type = Depends(current_identity)):
        new_password = str(body.new_password or "")
        birth_date = _date_text(body.birth_date)
        conn = engine_instance().connect()
        tx = conn.begin()
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
            must_change_password = bool((current.get("payload") or {}).get("must_change_password"))
            if must_change_password and not new_password:
                raise HTTPException(400, "Bạn phải đặt mật khẩu mới trước khi tiếp tục sử dụng Web V2.")
            if new_password:
                policy_error = password_policy_error(
                    new_password,
                    username=ident.employee_username,
                    full_name=body.full_name or str(current.get("full_name") or ""),
                )
                if policy_error:
                    raise HTTPException(400, policy_error)
                if hmac.compare_digest(str(current.get("password_value") or ""), new_password):
                    raise HTTPException(400, "Mật khẩu mới phải khác mật khẩu hiện tại.")

            updated = dict(current)
            province = body.province.strip()
            ward = body.ward.strip()
            address_detail = body.address_detail.strip() or body.address.strip()
            composed_address = ", ".join(part for part in (address_detail, ward, province) if part)
            updated.update({
                "full_name": body.full_name.strip(), "birth_date": birth_date, "phone": body.phone.strip(),
                "email": body.email.strip(), "address": composed_address,
                "bank_account": body.bank_account.strip(), "bank_name": body.bank_name.strip(),
            })
            if new_password:
                updated.update({"password_value": new_password, "remember_token_hash": "", "remember_token_expiry": ""})
            payload = dict(updated.get("payload") or {})
            payload.update({
                "Họ và tên đầy đủ": updated["full_name"], "Ngày sinh": updated["birth_date"],
                "Điện thoại": updated["phone"], "Email": updated["email"], "Địa chỉ": updated["address"],
                "Số tài khoản ngân hàng": updated["bank_account"], "Tên ngân hàng": updated["bank_name"],
                "Tỉnh/Thành phố": province, "Xã/Phường": ward, "Địa chỉ chi tiết": address_detail,
            })
            if new_password:
                payload["must_change_password"] = False
            updated["payload"] = payload

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
            raise HTTPException(500, f"Không cập nhật được hồ sơ an toàn: {type(exc).__name__}: {exc}") from exc
        finally:
            conn.close()

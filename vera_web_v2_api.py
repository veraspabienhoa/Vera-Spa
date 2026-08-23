"""VERA SPA Web V2 Python API.

This service is the server-side write boundary for the React/Web V2 pilot.
The browser never writes leave_records directly.  The API validates the
Supabase session, resolves the mapped VERA employee, derives leave days and
penalty from the canonical LoaiNghi policy, applies the same safety invariants
used by the Streamlit leave registration flow, writes PostgreSQL with a
record_uid, and mirrors the row to the legacy MainData Google Sheet.

The API deliberately fails closed when policy data is missing or a rule cannot
be interpreted.  That is safer than allowing Web V2 to bypass a legacy rule.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
import re
import unicodedata
import uuid
from typing import Any

import google.auth
import gspread
import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

VN_TZ = timezone(timedelta(hours=7))
LEAVE_SHEET_ID = os.getenv(
    "VERA_LEAVE_SHEET_ID", "1Kz0aw-JatptAN9G7YSwZ6rJO09urOPaD-rS-18eZSY0"
)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://nunxfjhrszmlyyrvphuq.supabase.co").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
CORS_ORIGINS = [
    x.strip()
    for x in os.getenv(
        "VERA_V2_CORS_ORIGINS",
        "https://veraspabienhoa.github.io,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if x.strip()
]

app = FastAPI(title="VERA SPA Web V2 API", version="2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

_engine = None
_gspread = None


def _engine_instance():
    global _engine
    if _engine is None:
        host = os.getenv("DB_HOST", "").strip()
        user = os.getenv("DB_USER", "").strip()
        password = os.getenv("DB_PASS", "")
        database = os.getenv("DB_NAME", "postgres")
        port = int(os.getenv("DB_PORT", "5432"))
        if not host or not user or not password:
            raise RuntimeError("PostgreSQL environment is incomplete")
        url = URL.create(
            "postgresql+psycopg", username=user, password=password,
            host=host, port=port, database=database,
        )
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=int(os.getenv("DB_POOL_SIZE", "2")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "0")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "600")),
        )
    return _engine


def _google_client():
    global _gspread
    if _gspread is None:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds, _ = google.auth.default(scopes=scopes)
        _gspread = gspread.authorize(creds)
    return _gspread


def _norm(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    return re.sub(r"\s+", " ", s).strip()


def _num(value: Any, default=0.0, money=False) -> float:
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value or "").strip()
        if not s or s.lower() in {"nan", "none", "-"}:
            return float(default)
        if money:
            s = re.sub(r"[^0-9-]", "", s)
        else:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return float(default)


def _policy_payload(conn) -> dict:
    # Preferred official policy introduced by the Nội quy page.
    row = conn.execute(text("""
        SELECT value_json FROM vera_app_setting
        WHERE category='official_policy' AND setting_key='leave_rules'
        LIMIT 1
    """)).scalar_one_or_none()
    if isinstance(row, dict) and (row.get("rows") or row.get("columns")):
        return row

    # Production-safe fallback to the PostgreSQL LoaiNghi snapshot.  It is still
    # PostgreSQL data, not a browser-provided rule set.
    row = conn.execute(text("""
        SELECT value_json FROM vera_app_setting
        WHERE category='leave_rules' AND setting_key='loai_nghi_snapshot_v2'
        LIMIT 1
    """)).scalar_one_or_none()
    if isinstance(row, dict) and row.get("rows"):
        return row
    raise HTTPException(503, "Chưa có Nội quy/LoaiNghi trong PostgreSQL; Web V2 không được phép ghi.")


def _policy_rows(conn) -> list[dict]:
    payload = _policy_payload(conn)
    headers = payload.get("columns") or payload.get("headers") or []
    rows = payload.get("rows") or []
    if rows and isinstance(rows[0], dict):
        return [dict(r) for r in rows]
    if not headers:
        headers = [
            "STT", "Lý do nghỉ", "Loại nghỉ", "Chi tiết", "Số ngày tính phép",
            "Phạt vi phạm", "Chỉ nhập được cuối tuần", "User có quyền được nhập",
            "Kiều đăng ký", "Giá trị", "Ngoại trừ đăng ký", "Kiểu hủy",
            "Số ngày hủy trước", "Ngoại trừ hủy", "Ghi chú",
        ]
    return [dict(zip(headers, list(r) + [""] * max(0, len(headers) - len(r)))) for r in rows]


def _field(row: dict, *names: str, default=""):
    by_norm = {_norm(k): v for k, v in row.items()}
    for name in names:
        key = _norm(name)
        if key in by_norm:
            return by_norm[key]
    return default


def _reason_item(conn, reason: str) -> dict:
    wanted = _norm(reason)
    for row in _policy_rows(conn):
        name = str(_field(row, "Lý do nghỉ", default="") or "").strip()
        if _norm(name) == wanted:
            detail = str(_field(row, "Chi tiết", default="") or "").strip()
            return {
                "name": name,
                "leave_type": str(_field(row, "Loại nghỉ", default="") or "").strip(),
                "detail_config": detail,
                "days": _num(_field(row, "Số ngày tính phép", "Số ngày tính", default=0)),
                "penalty": _num(_field(row, "Phạt vi phạm", default=0), money=True),
                "allowed_days": str(_field(row, "Chỉ nhập được cuối tuần", "Ngày được phép nhập", default="") or "").strip(),
                "allowed_roles": str(_field(row, "User có quyền được nhập", default="") or "").strip(),
                "register_type": str(_field(row, "Kiểu đăng ký", "Kiều đăng ký", default="") or "").strip(),
                "register_value": str(_field(row, "Giá trị", "Giá trị đăng ký", default="") or "").strip(),
                "register_exceptions": str(_field(row, "Ngoại trừ đăng ký", default="") or "").strip(),
                "requires_manual_penalty": "can nhap so tien" in _norm(detail),
            }
    raise HTTPException(400, f"Không tìm thấy Lý do nghỉ '{reason}' trong Nội quy/LoaiNghi.")


def _role_tokens(value: str) -> set[str]:
    n = _norm(value)
    roles = {"admin", "quanly", "letan", "leader", "nhanvien", "locker", "tapvu", "auto update"}
    return {r for r in roles if r in n}


def _weekday_label(d: date) -> str:
    return ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"][d.weekday()]


def _day_allowed(rule: str, d: date) -> bool:
    n = _norm(rule)
    if not n or n in {"tat ca", "all", "none", "nan"}:
        return True
    tokens = {
        0: ("thu hai", "t2"), 1: ("thu ba", "t3"), 2: ("thu tu", "t4"),
        3: ("thu nam", "t5"), 4: ("thu sau", "t6"),
        5: ("thu bay", "thu bay", "t7", "cuoi tuan"), 6: ("chu nhat", "cn", "cuoi tuan"),
    }[d.weekday()]
    return any(t in n for t in tokens)


def _parse_first_number(value: str):
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def _registration_rule(item: dict, role: str, target: date):
    if role == "admin":
        return
    allowed = _role_tokens(item["allowed_roles"])
    if allowed and role not in allowed:
        raise HTTPException(403, f"Tài khoản {role} không được dùng lý do '{item['name']}'.")
    if not _day_allowed(item["allowed_days"], target):
        raise HTTPException(400, f"'{item['name']}' không được nhập vào {_weekday_label(target)} {target.strftime('%d/%m/%Y')}.")

    now = datetime.now(VN_TZ)
    today = now.date()
    if target < today:
        raise HTTPException(400, "Không được đăng ký lịch ở ngày quá khứ.")
    if role in _role_tokens(item["register_exceptions"]):
        return

    typ = _norm(item["register_type"])
    val = item["register_value"]
    if "khong gioi han" in typ:
        return
    if "truoc n ngay" in typ or typ in {"truoc ngay", "before days"}:
        n = _parse_first_number(val)
        if n is None:
            raise HTTPException(400, f"Giá trị đăng ký của '{item['name']}' không hợp lệ.")
        earliest = today + timedelta(days=max(0, int(n)))
        if target < earliest:
            raise HTTPException(400, f"'{item['name']}' phải đăng ký trước ít nhất {int(n)} ngày. Ngày sớm nhất: {earliest.strftime('%d/%m/%Y')}.")
        return
    if "ngay hien tai tu gio" in typ:
        m = re.search(r"(\d{1,2})\s*(?::|h)?\s*(\d{1,2})?", str(val or ""))
        if not m:
            raise HTTPException(400, f"Giờ đăng ký của '{item['name']}' không hợp lệ.")
        hh, mm = int(m.group(1)), int(m.group(2) or 0)
        if target != today or now.time() < now.replace(hour=hh, minute=mm, second=0, microsecond=0).time():
            raise HTTPException(400, f"'{item['name']}' chỉ được đăng ký cho ngày hiện tại từ {hh:02d}:{mm:02d}.")
        return
    if "khong cho phep" in typ or "khong duoc dang ky" in typ:
        raise HTTPException(400, f"'{item['name']}' đang được cấu hình không cho phép đăng ký.")
    raise HTTPException(400, f"Không nhận diện được Kiểu đăng ký '{item['register_type']}' của '{item['name']}'.")


def _group(reason: str) -> str:
    n = _norm(reason)
    if "khong phep" in n:
        return "khong_phep"
    if "phat sinh" in n:
        return "phat_sinh"
    excluded = ("di tre", "ve som", "ra som", "qua tour", "loi vi pham", "khong don", "xuong phong", "ho tro")
    if "co phep" in n and not any(x in n for x in excluded):
        return "co_phep"
    return ""


def _is_video(reason: str) -> bool:
    return _norm(reason) == "nghi phep quay video"


def _is_long_sick(reason: str) -> bool:
    return _norm(reason) == "nghi benh co giay kham hoac duoc quan ly duyet"


def _is_annual(reason: str) -> bool:
    return "phep nam" in _norm(reason)


def _progressive_key(reason: str) -> str:
    n = _norm(reason)
    if "nghi" in n and "khong phep" in n:
        return "nghi_khong_phep"
    if "di tre" in n and "khong phep" in n:
        return "di_tre_khong_phep"
    if ("ve som" in n or "ra som" in n) and "khong phep" in n:
        return "ve_som_khong_phep"
    return ""


class Identity(BaseModel):
    auth_user_id: str
    employee_username: str
    role: str
    full_name: str = ""
    email: str = ""


async def current_identity(authorization: str | None = Header(default=None)) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Thiếu phiên đăng nhập Supabase.")
    token = authorization.split(" ", 1)[1].strip()
    if not token or not SUPABASE_ANON_KEY:
        raise HTTPException(503, "API Auth chưa được cấu hình.")
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(503, f"Không xác minh được phiên đăng nhập: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
    user = resp.json()
    auth_uid = str(user.get("id") or "")
    if not auth_uid:
        raise HTTPException(401, "Không xác định được tài khoản Supabase.")

    with _engine_instance().connect() as conn:
        row = conn.execute(text("""
            SELECT p.auth_user_id::text, p.employee_username, p.role,
                   COALESCE(e.full_name,''), COALESCE(e.email,'')
            FROM vera_v2_user_profile p
            JOIN employees e ON e.username=p.employee_username
            WHERE p.auth_user_id=CAST(:uid AS uuid)
              AND p.is_active=true
              AND COALESCE(e.login_locked,false)=false
            LIMIT 1
        """), {"uid": auth_uid}).first()
    if not row:
        raise HTTPException(403, "Tài khoản chưa được liên kết với nhân viên VERA đang hoạt động.")
    return Identity(
        auth_user_id=row[0], employee_username=row[1], role=str(row[2] or "").lower(),
        full_name=row[3], email=row[4],
    )


class LeaveCreate(BaseModel):
    leave_date: date
    employee_name: str = Field(min_length=1, max_length=200)
    leave_reason: str = Field(min_length=1, max_length=300)
    detail: str = Field(default="", max_length=3000)
    manual_penalty: float | None = Field(default=None, ge=0)


def _validate_and_prepare(conn, body: LeaveCreate, ident: Identity) -> tuple[dict, list[str]]:
    employee = body.employee_name.strip()
    role = ident.role
    employee_like = {"nhanvien", "leader", "locker", "tapvu"}
    if role in employee_like and _norm(employee) != _norm(ident.employee_username):
        raise HTTPException(403, "Tài khoản hiện tại chỉ được đăng ký lịch nghỉ của chính mình.")

    emp = conn.execute(text("""
        SELECT username, monthly_generated, monthly_leave, annual_leave
        FROM employees WHERE lower(btrim(username))=lower(btrim(:u))
          AND COALESCE(login_locked,false)=false LIMIT 1
    """), {"u": employee}).mappings().first()
    if not emp:
        raise HTTPException(400, "Không tìm thấy nhân viên đang hoạt động.")
    employee = emp["username"]

    item = _reason_item(conn, body.leave_reason)
    _registration_rule(item, role, body.leave_date)
    days = float(item["days"])
    if days not in {0.0, 0.5, 1.0}:
        raise HTTPException(400, "Số ngày tính trong 1 ngày chỉ được 0, 0.5 hoặc 1.")
    if item["requires_manual_penalty"]:
        if body.manual_penalty is None:
            raise HTTPException(400, "Lý do này bắt buộc nhập Mức phạt vi phạm.")
        base_penalty = float(body.manual_penalty)
    else:
        base_penalty = float(item["penalty"])

    if "loi vi pham khac" in _norm(item["name"]) and not body.detail.strip():
        raise HTTPException(400, "Chưa có Chi tiết vi phạm cho 'Lỗi vi phạm khác'.")
    if "nghi ly do khac" in _norm(item["name"]) and not body.detail.strip():
        raise HTTPException(400, "Bắt buộc nhập Chi tiết/Ghi chú đối với 'Nghỉ lý do khác'.")

    today = datetime.now(VN_TZ).date()
    if role != "admin":
        last_next_month = (date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if body.leave_date < today:
            raise HTTPException(400, "Không được đăng ký lịch nghỉ cho ngày trong quá khứ.")
        if not _is_long_sick(item["name"]) and body.leave_date > last_next_month:
            raise HTTPException(400, f"Chỉ được đăng ký lịch nghỉ đến hết {last_next_month.strftime('%d/%m/%Y')}.")

    existing = conn.execute(text("""
        SELECT record_uid, leave_reason, calculated_days, penalty
        FROM leave_records
        WHERE leave_date=:d AND lower(btrim(employee_name))=lower(btrim(:e))
        FOR SHARE
    """), {"d": body.leave_date, "e": employee}).mappings().all()
    if any(_norm(r["leave_reason"]) == _norm(item["name"]) for r in existing):
        raise HTTPException(409, f"{employee} đã có đúng lý do '{item['name']}' ngày {body.leave_date.strftime('%d/%m/%Y')}.")

    if role != "admin":
        if days > 0 and any(float(r["calculated_days"] or 0) > 0 for r in existing):
            raise HTTPException(400, "Trong cùng 1 ngày, mỗi nhân viên chỉ được có 1 dòng có Số ngày tính > 0; không cho phép 0.5 + 0.5.")
        new_group = _group(item["name"])
        if new_group and any(_group(r["leave_reason"]) == new_group for r in existing):
            raise HTTPException(400, "Trong cùng 1 ngày, một nhân viên không được đăng ký 2 lần cùng nhóm Có phép/Không phép/Phát sinh.")

        if body.leave_date.weekday() >= 5 and not (_is_annual(item["name"]) or _is_long_sick(item["name"]) or "khong phep" in _norm(item["name"])):
            weekend_count = conn.execute(text("""
                SELECT count(DISTINCT leave_date) FROM leave_records
                WHERE lower(btrim(employee_name))=lower(btrim(:e))
                  AND extract(year from leave_date)=:y AND extract(month from leave_date)=:m
                  AND extract(isodow from leave_date) IN (6,7)
                  AND lower(leave_reason) NOT LIKE '%không phép%'
                  AND lower(leave_reason) NOT LIKE '%quay video%'
                  AND lower(leave_reason) NOT LIKE '%giấy khám%'
            """), {"e": employee, "y": body.leave_date.year, "m": body.leave_date.month}).scalar() or 0
            if int(weekend_count) >= 2:
                raise HTTPException(400, f"{employee} chỉ được đăng ký tối đa 2 lần cuối tuần trong tháng đối với lý do chịu giới hạn.")

        if not _is_video(item["name"]):
            month_rows = conn.execute(text("""
                SELECT leave_reason, calculated_days FROM leave_records
                WHERE lower(btrim(employee_name))=lower(btrim(:e))
                  AND extract(year from leave_date)=:y AND extract(month from leave_date)=:m
            """), {"e": employee, "y": body.leave_date.year, "m": body.leave_date.month}).mappings().all()
            if _is_annual(item["name"]):
                year_used = conn.execute(text("""
                    SELECT COALESCE(sum(calculated_days),0) FROM leave_records
                    WHERE lower(btrim(employee_name))=lower(btrim(:e))
                      AND extract(year from leave_date)=:y AND lower(leave_reason) LIKE '%phép năm%'
                """), {"e": employee, "y": body.leave_date.year}).scalar() or 0
                limit = float(emp["annual_leave"] or 0)
                if limit > 0 and float(year_used) + days > limit:
                    raise HTTPException(400, f"Vượt quá số ngày Phép năm; quỹ còn {max(0, limit-float(year_used)):g} ngày.")
            elif "phat sinh" in _norm(item["name"]):
                used = sum(1 for r in month_rows if "phat sinh" in _norm(r["leave_reason"]))
                limit = float(emp["monthly_generated"] or 0)
                if limit > 0 and used >= limit:
                    raise HTTPException(400, f"Vượt giới hạn Phát sinh {limit:g} lần/tháng.")
            elif _group(item["name"]) == "co_phep" and days > 0 and not _is_long_sick(item["name"]):
                used = sum(float(r["calculated_days"] or 0) for r in month_rows if _group(r["leave_reason"]) == "co_phep" and not _is_long_sick(r["leave_reason"]))
                limit = float(emp["monthly_leave"] or 0)
                if limit > 0 and used + days > limit:
                    raise HTTPException(400, f"Vượt số ngày Có phép trong tháng; tối đa {limit:g} ngày/tháng.")

        # Current legacy group quota: 4 Có phép and 1 Phát sinh/day. KHÔNG phép is not capped.
        group = _group(item["name"])
        if group in {"co_phep", "phat_sinh"} and not (_is_video(item["name"]) or _is_long_sick(item["name"])):
            day_reasons = conn.execute(text("SELECT leave_reason FROM leave_records WHERE leave_date=:d"), {"d": body.leave_date}).scalars().all()
            count = sum(1 for r in day_reasons if _group(r) == group)
            limit = 4 if group == "co_phep" else 1
            if count >= limit:
                label = "CÓ phép" if group == "co_phep" else "PHÁT SINH"
                raise HTTPException(400, f"Ngày {body.leave_date.strftime('%d/%m/%Y')} đã đủ {limit} người {label}.")

    progressive = _progressive_key(item["name"])
    warnings = []
    ordinal = None
    extra = 0.0
    if progressive:
        day_reasons = conn.execute(text("SELECT leave_reason FROM leave_records WHERE leave_date=:d"), {"d": body.leave_date}).scalars().all()
        ordinal = sum(1 for r in day_reasons if _progressive_key(r) == progressive) + 1
        extra = max(0, ordinal - 2) * 100000.0
        warnings.append(f"Người Thứ {ordinal} · phạt lũy tiến cộng thêm {extra:,.0f} VNĐ.")

    # Monthly accumulated value mirrors the existing main-data convention.
    accumulated = conn.execute(text("""
        SELECT COALESCE(sum(calculated_days),0) FROM leave_records
        WHERE lower(btrim(employee_name))=lower(btrim(:e))
          AND extract(year from leave_date)=:y AND extract(month from leave_date)=:m
          AND lower(leave_reason) NOT LIKE '%quay video%'
          AND lower(leave_reason) NOT LIKE '%giấy khám%'
    """), {"e": employee, "y": body.leave_date.year, "m": body.leave_date.month}).scalar() or 0
    if not (_is_video(item["name"]) or _is_long_sick(item["name"])):
        accumulated = float(accumulated) + days

    detail = body.detail.strip()
    if ordinal:
        prefix = f"Người Thứ {ordinal} {item['name'].lower()}"
        detail = f"{prefix} | {detail}" if detail else prefix
    now = datetime.now(VN_TZ)
    record_uid = str(uuid.uuid4())
    record = {
        "record_uid": record_uid,
        "leave_date": body.leave_date,
        "employee_name": employee,
        "leave_reason": item["name"],
        "leave_type": item["leave_type"],
        "detail": detail,
        "calculated_days": days,
        "accumulated_leave": float(accumulated),
        "penalty": base_penalty + extra,
        "update_date": now.strftime("%d/%m/%Y"),
        "update_time": now.strftime("%H:%M:%S"),
        "updated_by": ident.employee_username,
        "weekday_label": _weekday_label(body.leave_date),
    }
    return record, warnings


def _sheet_row_for_record(ws, record: dict) -> tuple[int, list[Any]]:
    all_values = ws.get_all_values()
    headers = all_values[0][:13] if all_values else []
    if not headers:
        raise RuntimeError("MainData chưa có header A:M")
    target_row = 2
    for idx, row in enumerate(all_values[1:], start=2):
        if any(str(x).strip() for x in row[:13]):
            target_row = idx + 1
    mapping = {
        "stt": target_row - 1,
        "ngay": record["leave_date"].strftime("%d/%m/%Y"),
        "thu ngay": record["weekday_label"],
        "ten nhan vien": record["employee_name"],
        "ly do nghi": record["leave_reason"],
        "loai nghi": record["leave_type"],
        "chi tiet": record["detail"],
        "so ngay tinh": record["calculated_days"],
        "so ngay tinh phep": record["calculated_days"],
        "so ngay phep cong don": record["accumulated_leave"],
        "phat vi pham": record["penalty"],
        "ngay cap nhat": record["update_date"],
        "gio cap nhat": record["update_time"],
        "nguoi cap nhat": record["updated_by"],
    }
    return target_row, [mapping.get(_norm(h), "") for h in headers]


def _insert_record(conn, record: dict, source_row: int):
    payload = {
        "Ngày": record["leave_date"].strftime("%d/%m/%Y"),
        "Thứ ngày": record["weekday_label"], "Tên nhân viên": record["employee_name"],
        "Lý do nghỉ": record["leave_reason"], "Loại nghỉ": record["leave_type"],
        "Chi tiết": record["detail"], "Số ngày tính": record["calculated_days"],
        "Số ngày phép cộng dồn": record["accumulated_leave"], "Phạt vi phạm": record["penalty"],
        "Ngày cập nhật": record["update_date"], "Giờ cập nhật": record["update_time"],
        "Người cập nhật": record["updated_by"], "record_uid": record["record_uid"],
    }
    conn.execute(text("""
        INSERT INTO leave_records(
            source_sheet_id, source_row, leave_date, employee_name, leave_reason,
            leave_type, detail, calculated_days, accumulated_leave, penalty,
            update_date, update_time, updated_by, weekday_label, payload, record_uid,
            created_at, updated_at
        ) VALUES (
            :sid, :srow, :leave_date, :employee_name, :leave_reason,
            :leave_type, :detail, :calculated_days, :accumulated_leave, :penalty,
            :update_date, :update_time, :updated_by, :weekday_label, CAST(:payload AS jsonb), :record_uid,
            NOW(), NOW()
        )
    """), {**record, "sid": LEAVE_SHEET_ID, "srow": source_row, "payload": json.dumps(payload, ensure_ascii=False)})
    # Operational trace; this is additive and does not replace the legacy activity log.
    try:
        conn.execute(text("""
            INSERT INTO vera_sync_event(dataset_key,event_type,detail,created_at)
            VALUES ('leave_primary','web_v2_leave_create',:detail,NOW())
        """), {"detail": f"record_uid={record['record_uid']}; employee={record['employee_name']}; actor={record['updated_by']}"})
    except Exception:
        # Do not make leave registration depend on an optional telemetry table shape.
        pass


@app.get("/v2/health")
def health():
    with _engine_instance().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True, "service": "vera-web-v2-api", "version": "2.1"}


@app.get("/v2/me")
def me(ident: Identity = Depends(current_identity)):
    return ident.model_dump()


@app.get("/v2/employees")
def employees(ident: Identity = Depends(current_identity)):
    with _engine_instance().connect() as conn:
        rows = conn.execute(text("""
            SELECT username, COALESCE(full_name,'') full_name, COALESCE(role,'') role
            FROM employees WHERE COALESCE(login_locked,false)=false ORDER BY username
        """)).mappings().all()
    return {"employees": [dict(r) for r in rows]}


@app.get("/v2/leave/reasons")
def reasons(ident: Identity = Depends(current_identity)):
    with _engine_instance().connect() as conn:
        output = []
        for row in _policy_rows(conn):
            name = str(_field(row, "Lý do nghỉ", default="") or "").strip()
            if not name:
                continue
            item = _reason_item(conn, name)
            allowed = _role_tokens(item["allowed_roles"])
            if ident.role != "admin" and allowed and ident.role not in allowed:
                continue
            output.append({
                "name": item["name"], "days": item["days"], "penalty": item["penalty"],
                "requires_manual_penalty": item["requires_manual_penalty"],
            })
    return {"reasons": output}


@app.get("/v2/leave/records")
def leave_records(date_value: date = Query(alias="date"), ident: Identity = Depends(current_identity)):
    with _engine_instance().connect() as conn:
        rows = conn.execute(text("""
            SELECT record_uid, employee_name, leave_reason, detail, penalty, updated_by, updated_at
            FROM leave_records WHERE leave_date=:d ORDER BY employee_name, record_uid
        """), {"d": date_value}).mappings().all()
    return {"records": [dict(r) for r in rows]}


@app.get("/v2/leave/summary")
def leave_summary(date_value: date = Query(alias="date"), ident: Identity = Depends(current_identity)):
    with _engine_instance().connect() as conn:
        active = conn.execute(text("SELECT count(*) FROM employees WHERE COALESCE(login_locked,false)=false")).scalar() or 0
        rows = conn.execute(text("SELECT employee_name, leave_reason, calculated_days FROM leave_records WHERE leave_date=:d"), {"d": date_value}).mappings().all()
    full = len({r["employee_name"] for r in rows if _norm(r["leave_reason"]).startswith("nghi") and float(r["calculated_days"] or 0) > 0})
    return {
        "working": max(int(active) - full, 0), "leave": len(rows),
        "paid": sum(1 for r in rows if _group(r["leave_reason"]) == "co_phep"),
        "unpaid": sum(1 for r in rows if _group(r["leave_reason"]) == "khong_phep"),
    }


@app.post("/v2/leave/records")
def create_leave(body: LeaveCreate, ident: Identity = Depends(current_identity)):
    engine = _engine_instance()
    conn = engine.connect()
    tx = conn.begin()
    ws = None
    sheet_row = None
    try:
        # Same advisory lock key used by Phase 4, so Web V2 and Streamlit serialize writes.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
        record, warnings = _validate_and_prepare(conn, body, ident)

        ws = _google_client().open_by_key(LEAVE_SHEET_ID).get_worksheet(0)
        sheet_row, row_values = _sheet_row_for_record(ws, record)
        record["source_row"] = sheet_row
        _insert_record(conn, record, sheet_row)

        # Mirror before committing PG.  If Google fails, transaction rolls back.
        ws.update(range_name=f"A{sheet_row}:M{sheet_row}", values=[row_values], value_input_option="USER_ENTERED")
        try:
            tx.commit()
        except Exception:
            # Commit failure after a successful mirror: best-effort compensation of the new Sheet row.
            try:
                ws.delete_rows(sheet_row)
            except Exception:
                pass
            raise
        return {
            "ok": True, "record_uid": record["record_uid"], "record": record,
            "warnings": warnings,
            "message": "Đã ghi lịch nghỉ qua Python API, PostgreSQL và MainData mirror.",
        }
    except HTTPException:
        if tx.is_active:
            tx.rollback()
        raise
    except Exception as exc:
        if tx.is_active:
            tx.rollback()
        raise HTTPException(500, f"Không ghi được lịch nghỉ an toàn: {type(exc).__name__}: {exc}") from exc
    finally:
        conn.close()

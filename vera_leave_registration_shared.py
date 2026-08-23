"""Framework-independent leave registration rules shared by Streamlit/Web V2.

Keep browser/API/UI layers thin: this module contains only deterministic policy
helpers and raises LeaveRuleError instead of importing FastAPI or Streamlit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
import unicodedata
from typing import Any

VN_TZ = timezone(timedelta(hours=7))


@dataclass(frozen=True)
class LeaveRuleError(Exception):
    status_code: int
    message: str

    def __str__(self) -> str:
        return self.message


def norm(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    return re.sub(r"\s+", " ", s).strip()


def number(value: Any, default: float = 0.0, money: bool = False) -> float:
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


def field(row: dict, *names: str, default=""):
    by_norm = {norm(k): v for k, v in row.items()}
    for name in names:
        key = norm(name)
        if key in by_norm:
            return by_norm[key]
    return default


def reason_item(rows: list[dict], reason: str) -> dict:
    wanted = norm(reason)
    for row in rows:
        name = str(field(row, "Lý do nghỉ", default="") or "").strip()
        if norm(name) != wanted:
            continue
        detail = str(field(row, "Chi tiết", default="") or "").strip()
        return {
            "name": name,
            "leave_type": str(field(row, "Loại nghỉ", default="") or "").strip(),
            "detail_config": detail,
            "days": number(field(row, "Số ngày tính phép", "Số ngày tính", default=0)),
            "penalty": number(field(row, "Phạt vi phạm", default=0), money=True),
            "allowed_days": str(field(row, "Chỉ nhập được cuối tuần", "Ngày được phép nhập", default="") or "").strip(),
            "allowed_roles": str(field(row, "User có quyền được nhập", default="") or "").strip(),
            "register_type": str(field(row, "Kiểu đăng ký", "Kiều đăng ký", default="") or "").strip(),
            "register_value": str(field(row, "Giá trị", "Giá trị đăng ký", default="") or "").strip(),
            "register_exceptions": str(field(row, "Ngoại trừ đăng ký", default="") or "").strip(),
            "requires_manual_penalty": "can nhap so tien" in norm(detail),
        }
    raise LeaveRuleError(400, f"Không tìm thấy Lý do nghỉ '{reason}' trong Nội quy/LoaiNghi.")


def role_tokens(value: str) -> set[str]:
    n = norm(value)
    roles = {"admin", "quanly", "letan", "leader", "nhanvien", "locker", "tapvu", "auto update"}
    return {r for r in roles if r in n}


def weekday_label(d: date) -> str:
    return ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"][d.weekday()]


def day_allowed(rule: str, d: date) -> bool:
    n = norm(rule)
    if not n or n in {"tat ca", "all", "none", "nan"}:
        return True
    tokens = {
        0: ("thu hai", "t2"), 1: ("thu ba", "t3"), 2: ("thu tu", "t4"),
        3: ("thu nam", "t5"), 4: ("thu sau", "t6"),
        5: ("thu bay", "t7", "cuoi tuan"), 6: ("chu nhat", "cn", "cuoi tuan"),
    }[d.weekday()]
    return any(t in n for t in tokens)


def parse_first_number(value: str):
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def validate_registration_rule(item: dict, role: str, target: date, now: datetime | None = None) -> None:
    role = str(role or "").strip().lower()
    if role == "admin":
        return
    allowed = role_tokens(item.get("allowed_roles", ""))
    if allowed and role not in allowed:
        raise LeaveRuleError(403, f"Tài khoản {role} không được dùng lý do '{item['name']}'.")
    if not day_allowed(item.get("allowed_days", ""), target):
        raise LeaveRuleError(400, f"'{item['name']}' không được nhập vào {weekday_label(target)} {target.strftime('%d/%m/%Y')}.")

    now = now or datetime.now(VN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    today = now.astimezone(VN_TZ).date()
    if target < today:
        raise LeaveRuleError(400, "Không được đăng ký lịch ở ngày quá khứ.")
    if role in role_tokens(item.get("register_exceptions", "")):
        return

    typ = norm(item.get("register_type", ""))
    val = item.get("register_value", "")
    if "khong gioi han" in typ:
        return
    if "truoc n ngay" in typ or typ in {"truoc ngay", "before days"}:
        n = parse_first_number(val)
        if n is None:
            raise LeaveRuleError(400, f"Giá trị đăng ký của '{item['name']}' không hợp lệ.")
        earliest = today + timedelta(days=max(0, int(n)))
        if target < earliest:
            raise LeaveRuleError(400, f"'{item['name']}' phải đăng ký trước ít nhất {int(n)} ngày. Ngày sớm nhất: {earliest.strftime('%d/%m/%Y')}.")
        return
    if "ngay hien tai tu gio" in typ:
        m = re.search(r"(\d{1,2})\s*(?::|h)?\s*(\d{1,2})?", str(val or ""))
        if not m:
            raise LeaveRuleError(400, f"Giờ đăng ký của '{item['name']}' không hợp lệ.")
        hh, mm = int(m.group(1)), int(m.group(2) or 0)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise LeaveRuleError(400, f"Giờ đăng ký của '{item['name']}' không hợp lệ.")
        local_now = now.astimezone(VN_TZ)
        if target != today or local_now.time() < local_now.replace(hour=hh, minute=mm, second=0, microsecond=0).time():
            raise LeaveRuleError(400, f"'{item['name']}' chỉ được đăng ký cho ngày hiện tại từ {hh:02d}:{mm:02d}.")
        return
    if "khong cho phep" in typ or "khong duoc dang ky" in typ:
        raise LeaveRuleError(400, f"'{item['name']}' đang được cấu hình không cho phép đăng ký.")
    raise LeaveRuleError(400, f"Không nhận diện được Kiểu đăng ký '{item.get('register_type', '')}' của '{item['name']}'.")


def group(reason: str) -> str:
    n = norm(reason)
    if "khong phep" in n:
        return "khong_phep"
    if "phat sinh" in n:
        return "phat_sinh"
    excluded = ("di tre", "ve som", "ra som", "qua tour", "loi vi pham", "khong don", "xuong phong", "ho tro")
    if "co phep" in n and not any(x in n for x in excluded):
        return "co_phep"
    return ""


def is_video(reason: str) -> bool:
    return norm(reason) == "nghi phep quay video"


def is_long_sick(reason: str) -> bool:
    return norm(reason) == "nghi benh co giay kham hoac duoc quan ly duyet"


def is_annual(reason: str) -> bool:
    return "phep nam" in norm(reason)


def progressive_key(reason: str) -> str:
    n = norm(reason)
    if "nghi" in n and "khong phep" in n:
        return "nghi_khong_phep"
    if "di tre" in n and "khong phep" in n:
        return "di_tre_khong_phep"
    if ("ve som" in n or "ra som" in n) and "khong phep" in n:
        return "ve_som_khong_phep"
    return ""

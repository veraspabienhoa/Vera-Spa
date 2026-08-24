"""Shared password policy for VERA Web V2 write endpoints."""
from __future__ import annotations

import re
import unicodedata


COMMON_PASSWORDS = {
    "12345678", "123456789", "1234567890", "password", "password1",
    "qwerty123", "qwertyui", "abc12345", "11111111", "00000000",
    "admin123", "admin1234", "veraspa", "veraspa123", "matkhau",
}
SEQUENCES = ("0123456789", "9876543210", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop")


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9]", "", text)


def password_policy_error(password: str, *, username: str = "", full_name: str = "") -> str:
    value = str(password or "")
    if len(value) < 8:
        return "Mật khẩu mới phải có ít nhất 8 ký tự."
    groups = sum((
        bool(re.search(r"[a-z]", value)), bool(re.search(r"[A-Z]", value)),
        bool(re.search(r"\d", value)), bool(re.search(r"[^A-Za-z0-9]", value)),
    ))
    if groups < 3:
        return "Mật khẩu phải kết hợp ít nhất 3 nhóm: chữ thường, chữ hoa, số và ký tự đặc biệt."
    folded = _fold(value)
    if folded in COMMON_PASSWORDS or len(set(value)) <= 3:
        return "Mật khẩu này quá dễ đoán. Vui lòng chọn mật khẩu khác."
    if any(len(folded) >= 6 and folded in sequence for sequence in SEQUENCES):
        return "Mật khẩu không được là một chuỗi ký tự hoặc chuỗi số dễ đoán."
    for personal in (_fold(username), _fold(full_name)):
        if len(personal) >= 4 and personal in folded:
            return "Mật khẩu không được chứa tên đăng nhập hoặc họ tên của nhân viên."
    return ""

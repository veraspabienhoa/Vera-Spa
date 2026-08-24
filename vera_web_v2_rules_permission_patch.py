"""Expose Web V2 Nội quy rights in the legacy permission editor.

The V92.6.99 core stays immutable.  This source patch only extends its existing
feature catalog/defaults so Streamlit's Phân quyền page and the Web V2 API use
the same four permission keys.
"""
from __future__ import annotations


def _replace_once(source: str, old: str, new: str, label: str, warnings: list[str]) -> str:
    count = source.count(old)
    if count != 1:
        warnings.append(f"{label}:{count}")
        return source
    return source.replace(old, new, 1)


def apply(source: str):
    warnings: list[str] = []

    feature_marker = '''    "guide_manage": "📘 Hướng dẫn sử dụng · Tải/Sửa/Xóa tài liệu",

    # ===== BẢNG TOUR ====='''
    feature_replacement = '''    "guide_manage": "📘 Hướng dẫn sử dụng · Tải/Sửa/Xóa tài liệu",

    # ===== NỘI QUY =====
    "official_rules_view": "📜 Nội quy · Xem Bảng nội quy",
    "official_rules_edit": "✏️ Nội quy · Sửa và áp dụng",
    "official_rules_export": "📥 Nội quy · Export Excel",
    "official_rules_import": "📤 Nội quy · Import Excel",

    # ===== BẢNG TOUR ====='''
    source = _replace_once(source, feature_marker, feature_replacement, "feature_catalog", warnings)

    group_marker = '''    "💰 Bảng lương": ['''
    group_replacement = '''    "📜 Nội quy": [
        "official_rules_view", "official_rules_edit",
        "official_rules_export", "official_rules_import",
    ],
    "💰 Bảng lương": ['''
    source = _replace_once(source, group_marker, group_replacement, "feature_group", warnings)

    frontdesk_marker = '''    "profile", "profile_edit", "birthday", "birthday_check",
}
_DEFAULT_EMPLOYEE = {'''
    frontdesk_replacement = '''    "profile", "profile_edit", "birthday", "birthday_check",
    "official_rules_view", "official_rules_export",
}
_DEFAULT_EMPLOYEE = {'''
    source = _replace_once(source, frontdesk_marker, frontdesk_replacement, "frontdesk_defaults", warnings)

    employee_marker = '''    "profile", "profile_edit", "birthday", "birthday_check",
}
DEFAULT_ROLE_FEATURES = {'''
    employee_replacement = '''    "profile", "profile_edit", "birthday", "birthday_check",
    "official_rules_view", "official_rules_export",
}
DEFAULT_ROLE_FEATURES = {'''
    source = _replace_once(source, employee_marker, employee_replacement, "employee_defaults", warnings)

    source = _replace_once(
        source,
        '    "quanly": set(_DEFAULT_FRONTDESK),',
        '    "quanly": set(_DEFAULT_FRONTDESK) | {"official_rules_edit", "official_rules_import"},',
        "manager_edit_default",
        warnings,
    )
    source = _replace_once(
        source,
        '    "locker": {"tour", "tour_refresh", "profile", "profile_edit", "birthday", "birthday_check"},',
        '    "locker": {"tour", "tour_refresh", "profile", "profile_edit", "birthday", "birthday_check", "official_rules_view", "official_rules_export"},',
        "locker_view_default",
        warnings,
    )
    source = _replace_once(
        source,
        '    "tapvu": {"birthday", "birthday_check"},',
        '    "tapvu": {"birthday", "birthday_check", "official_rules_view", "official_rules_export"},',
        "cleaner_view_default",
        warnings,
    )
    return source, warnings

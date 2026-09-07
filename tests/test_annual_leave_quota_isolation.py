from datetime import date, datetime, timezone, timedelta

import pandas as pd

from vera_leave_registration_live_shared import (
    clean_display,
    daily_employee_registration_rule,
    daily_group_quota,
    employee_registration_window,
    is_annual_reason,
    is_long_sick_reason,
    is_special_day_rule_exempt,
    is_video_reason,
    leave_exists,
    monthly_weekend_registration_limit,
    normalize_reason,
    progressive_ordinal_and_bonus,
    progressive_penalty_reason,
    rows_counting_toward_quota,
    validate_leave_registration_request_live,
)
from vera_leave_registration_shared import norm

VN_TZ = timezone(timedelta(hours=7))


def _runtime():
    return {
        "clean_leave_reason_display": clean_display,
        "is_annual_leave_range_reason": is_annual_reason,
        "is_long_sick_leave_range_reason": is_long_sick_reason,
        "normalize_leave_reason": normalize_reason,
        "employee_registration_window": employee_registration_window,
        "validate_leave_registration_notice": lambda *args, **kwargs: (True, ""),
        "employee_like_roles": {"nhanvien", "leader", "locker", "tapvu"},
        "validate_monthly_weekend_registration_limit": monthly_weekend_registration_limit,
        "is_video_leave_reason": is_video_reason,
        "leave_rows_counting_toward_quota": rows_counting_toward_quota,
        "normalize_login_name": norm,
        "is_special_day_rule_exempt": is_special_day_rule_exempt,
        "leave_exists_in_sources": leave_exists,
        "validate_daily_employee_registration_rule": daily_employee_registration_rule,
        "validate_daily_group_quota": daily_group_quota,
        "get_progressive_penalty_reason": progressive_penalty_reason,
        "progressive_ordinal_and_bonus": progressive_ordinal_and_bonus,
        "now_vn": lambda: datetime(2026, 9, 7, 14, 0, tzinfo=VN_TZ),
    }


def _credentials():
    return pd.DataFrame([
        {
            "Tên nhân viên": "Minh Anh",
            "Phát sinh tháng": 2,
            "Có phép tháng": 5,
            "Phép năm": 12,
        }
    ])


def _request(reason="Nghỉ CÓ phép", when=date(2026, 10, 14)):
    return {
        "role": "nhanvien",
        "start_date": when,
        "end_date": when,
        "employee": "Minh Anh",
        "reason": reason,
        "detail": "",
        "days": 1,
        "penalty": 0,
        "requires_manual_penalty": False,
        "is_loi_vi_pham": False,
        "is_nghi_ly_do_khac": False,
        "is_zero_day_co_phep": False,
        "default_penalty": 0,
    }


def _annual_rows():
    return pd.DataFrame([
        {
            "Ngày": date(2026, 10, day),
            "Tên nhân viên": "Minh Anh",
            "Lý do nghỉ": "Nghỉ Phép năm",
            "Số ngày tính": 1,
        }
        for day in range(15, 22)
    ])


def test_annual_leave_rows_do_not_count_toward_ordinary_paid_quota():
    filtered = rows_counting_toward_quota(_annual_rows())
    assert filtered.empty

    result = validate_leave_registration_request_live(
        _request(),
        _annual_rows(),
        _credentials(),
        _runtime(),
    )
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["accumulated_month"] == 0


def test_monthly_paid_quota_still_blocks_after_five_non_annual_days():
    ordinary = pd.DataFrame([
        {
            "Ngày": date(2026, 10, day),
            "Tên nhân viên": "Minh Anh",
            "Lý do nghỉ": "Nghỉ CÓ phép",
            "Số ngày tính": 1,
        }
        for day in (1, 2, 5, 6, 7)
    ])
    history = pd.concat([_annual_rows(), ordinary], ignore_index=True)

    result = validate_leave_registration_request_live(
        _request(when=date(2026, 10, 14)),
        history,
        _credentials(),
        _runtime(),
    )
    assert result["ok"] is False
    assert any("Vượt số ngày Có phép trong tháng" in message for message in result["errors"])


def test_annual_leave_does_not_consume_daily_paid_headcount():
    same_day_annual = pd.DataFrame([
        {"Ngày": date(2026, 10, 14), "Tên nhân viên": f"Annual {index}", "Lý do nghỉ": "Nghỉ Phép năm", "Số ngày tính": 1}
        for index in range(1, 6)
    ])
    ok, message = daily_group_quota(
        same_day_annual,
        date(2026, 10, 14),
        "Nghỉ CÓ phép",
        weekday_limit=5,
    )
    assert ok is True
    assert message == ""

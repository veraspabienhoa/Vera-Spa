from datetime import date, datetime

from vera_web_v2_outside_leave_rule import (
    _mark_final_early_checkout,
    _scheduled_early_checkout,
)


def _bich_nhu_item():
    return {
        "date": "31/08/2026",
        "employee_name": "Bích Nhu",
        "departure_status": "Làm về sớm đúng quy định",
        "early_minutes": 359,
        "break_source": "TimeSoft FaceID",
        "faceid_last": "17:00:24",
        "break_out": "17:00:22",
        "break_in": "",
    }


def test_scheduled_early_leave_checkout_is_not_break():
    item = _bich_nhu_item()
    checkout = _scheduled_early_checkout(
        item,
        work_day=date(2026, 8, 31),
        reasons=["Về sớm CÓ phép"],
        early_leave_registered_at=datetime(2026, 8, 28, 10, 2, 6),
        break_out=datetime(2026, 8, 31, 17, 0, 22),
    )
    assert checkout == datetime(2026, 8, 31, 17, 0, 24)

    _mark_final_early_checkout(
        item,
        checkout=checkout,
        restriction_text="Về sớm CÓ phép",
    )
    assert item["break_out"] == ""
    assert item["break_in"] == ""
    assert item["break_started"] is False
    assert item["check_out"] == "17:00:24"
    assert item["break_final_early_checkout"] is True
    assert "KHÔNG NGHỈ GIỮA CA" in item["break_status"]


def test_late_entered_early_leave_keeps_outside_event_for_penalty():
    item = _bich_nhu_item()
    checkout = _scheduled_early_checkout(
        item,
        work_day=date(2026, 8, 31),
        reasons=["Về sớm KHÔNG phép"],
        early_leave_registered_at=datetime(2026, 8, 31, 17, 10, 0),
        break_out=datetime(2026, 8, 31, 17, 0, 22),
    )
    assert checkout is None


def test_before_1700_remains_outside_even_when_early_leave_preexists():
    item = _bich_nhu_item()
    item["faceid_last"] = "16:40:00"
    checkout = _scheduled_early_checkout(
        item,
        work_day=date(2026, 8, 31),
        reasons=["Về sớm CÓ phép"],
        early_leave_registered_at=datetime(2026, 8, 28, 10, 2, 6),
        break_out=datetime(2026, 8, 31, 16, 40, 0),
    )
    assert checkout is None

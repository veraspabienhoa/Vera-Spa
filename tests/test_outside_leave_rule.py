from datetime import date, datetime

import vera_auto_check as auto_check
from vera_web_v2_outside_leave_rule import (
    RESTRICTED_LEAVE_REASONS,
    _restricted_leave_reason,
    _violation_for,
)


def _catalog():
    names = [
        "Ra ngoài vào muộn dưới 30 phút",
        "Ra ngoài vào muộn dưới 60 phút",
        "Ra ngoài vào muộn dưới 120 phút",
        "Ra ngoài vào muộn trên 120 phút",
        "Ra ngoài chỉ có dữ liệu một lần",
    ]
    return {
        auto_check._norm(name): {
            "name": name,
            "type": "Vi phạm",
            "days": 0,
            "penalty": 100000,
        }
        for name in names
    }


def test_only_the_twelve_registered_reasons_block_outside_break():
    assert len(RESTRICTED_LEAVE_REASONS) == 12
    for reason in RESTRICTED_LEAVE_REASONS:
        assert _restricted_leave_reason(reason), reason


def test_linh_dan_automatic_lateness_keeps_mid_shift_break():
    assert not _restricted_leave_reason("Đi trễ nhỏ hơn hoặc bằng 30 phút")
    assert not _restricted_leave_reason("Đi trễ nhỏ hơn hoặc bằng 60 phút")
    assert not _restricted_leave_reason("Đi trễ nhỏ hơn hoặc bằng 120 phút")
    assert not _restricted_leave_reason("Nghỉ CÓ phép")


def test_recognized_support_shift_reasons_keep_mid_shift_break():
    for reason in (
        "Hỗ trợ Ca 1 sau 23H đi trễ 2 tiếng",
        "Hỗ trợ Ca 1 sau 0:0H đi trễ 3 tiếng",
        "Hỗ trợ Ca 2 sau 0:0H đi trễ 1 tiếng",
    ):
        assert not _restricted_leave_reason(reason), reason

    # Unlisted support labels also keep the break: restriction is an exact
    # allow-list of the twelve business reasons above.
    assert not _restricted_leave_reason("Hỗ trợ đi trễ không xác định")


def test_outside_before_1700_is_penalized_from_break_out_to_1700():
    item, minutes, calculation = _violation_for(
        catalog=_catalog(),
        work_day=date(2026, 8, 31),
        break_out=datetime(2026, 8, 31, 16, 20, 0),
    )
    assert item is not None
    assert item["name"] == "Ra ngoài vào muộn dưới 60 phút"
    assert minutes == 40
    assert calculation == "Tính từ Giờ ra đến 17:00"


def test_outside_after_1700_uses_single_side_reason():
    item, minutes, calculation = _violation_for(
        catalog=_catalog(),
        work_day=date(2026, 8, 31),
        break_out=datetime(2026, 8, 31, 17, 10, 0),
    )
    assert item is not None
    assert item["name"] == "Ra ngoài chỉ có dữ liệu một lần"
    assert minutes == 0
    assert calculation == "Giờ ra sau 17:00"

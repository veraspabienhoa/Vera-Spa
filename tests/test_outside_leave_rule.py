from datetime import date, datetime

import vera_auto_check as auto_check
from vera_web_v2_outside_leave_rule import _restricted_leave_reason, _violation_for


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


def test_all_late_and_early_leave_variants_block_outside_break():
    for reason in (
        "Đi trễ CÓ phép",
        "Đi trễ KHÔNG phép",
        "Về sớm CÓ phép",
        "Về sớm KHÔNG phép",
    ):
        assert _restricted_leave_reason(reason), reason
    assert not _restricted_leave_reason("Nghỉ CÓ phép")


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

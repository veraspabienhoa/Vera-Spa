from vera_web_v2_support_shift_break import (
    _remove_late_restriction,
    is_break_preserving_support,
)


def test_exact_support_reasons_are_break_preserving():
    for reason in (
        "Hỗ trợ Ca 1 sau 23H đi trễ 2 tiếng",
        "Hỗ trợ Ca 1 sau 0:0H đi trễ 3 tiếng",
        "Hỗ trợ Ca 2 sau 0:0H đi trễ 1 tiếng",
    ):
        assert is_break_preserving_support(reason)
    assert not is_break_preserving_support("Đi trễ CÓ phép")


def test_support_reason_is_removed_without_removing_other_restrictions():
    item = {
        "break_enabled": True,
        "break_planned_minutes": 90,
        "break_restricted_reason": "Hỗ trợ Ca 1 sau 23H đi trễ 2 tiếng",
        "break_alert_suppressed": True,
    }
    _remove_late_restriction(item)
    assert item["break_restricted_reason"] == ""
    assert item["break_alert_suppressed"] is False
    assert item["break_status"] == "Chưa ghi nhận FaceID nghỉ"

    mixed = {
        "break_enabled": True,
        "break_planned_minutes": 90,
        "break_restricted_reason": "Hỗ trợ Ca 2 sau 0:0H đi trễ 1 tiếng / Về sớm CÓ phép",
        "break_alert_suppressed": True,
    }
    _remove_late_restriction(mixed)
    assert mixed["break_restricted_reason"] == "Về sớm CÓ phép"
    assert mixed["break_alert_suppressed"] is True

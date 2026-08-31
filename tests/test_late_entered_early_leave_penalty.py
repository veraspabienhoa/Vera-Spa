from datetime import date, datetime

import vera_auto_check as auto_check
import vera_web_v2_attendance_policy_patch as policy_patch
import vera_web_v2_outside_leave_rule as outside_rule


def _catalog():
    return {
        auto_check._norm("Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút"): {
            "name": "Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút",
            "type": "Vi phạm",
            "days": 0,
            "penalty": 50000,
        },
        auto_check._norm("Ra ngoài vào muộn nhỏ hơn hoặc bằng 60 phút"): {
            "name": "Ra ngoài vào muộn nhỏ hơn hoặc bằng 60 phút",
            "type": "Vi phạm",
            "days": 0,
            "penalty": 100000,
        },
        auto_check._norm("Ra ngoài vào muộn nhỏ hơn hoặc bằng 120 phút"): {
            "name": "Ra ngoài vào muộn nhỏ hơn hoặc bằng 120 phút",
            "type": "Vi phạm",
            "days": 0,
            "penalty": 200000,
        },
    }


def test_thuy_vy_shape_is_67_minutes_and_200k_tier():
    policy_patch.install_attendance_policy_patch()
    item, minutes, detail = outside_rule._violation_for(
        catalog=_catalog(),
        work_day=date(2026, 8, 31),
        break_out=datetime(2026, 8, 31, 15, 53, 31),
    )

    assert minutes == 67
    assert item is not None
    assert item["name"] == "Ra ngoài vào muộn nhỏ hơn hoặc bằng 120 phút"
    assert item["penalty"] == 200000
    assert "66 phút 29 giây" in detail
    assert "Quy đổi 67 phút" in detail


def test_late_entered_early_leave_does_not_turn_outside_event_into_checkout():
    policy_patch.install_attendance_policy_patch()
    break_out = datetime(2026, 8, 31, 15, 53, 31)
    entered_later = datetime(2026, 8, 31, 17, 19, 6)

    checkout = outside_rule._scheduled_early_checkout(
        {
            "break_source": "TimeSoft FaceID",
            "punch_times": ["12:58:59", "15:53:31"],
            "departure_status": "Làm về sớm đúng quy định",
            "early_minutes": 1,
        },
        work_day=date(2026, 8, 31),
        reasons=["Về sớm KHÔNG phép"],
        early_leave_registered_at=entered_later,
        break_out=break_out,
    )

    assert checkout is None


def test_pre_registered_two_group_early_leave_remains_final_checkout():
    policy_patch.install_attendance_policy_patch()
    break_out = datetime(2026, 8, 31, 17, 0, 24)
    entered_before = datetime(2026, 8, 31, 16, 30, 0)

    checkout = outside_rule._scheduled_early_checkout(
        {
            "break_source": "TimeSoft FaceID",
            "punch_times": ["12:52:10", "17:00:24"],
            "departure_status": "Làm về sớm đúng quy định",
            "early_minutes": 1,
        },
        work_day=date(2026, 8, 31),
        reasons=["Về sớm CÓ phép"],
        early_leave_registered_at=entered_before,
        break_out=break_out,
    )

    assert checkout == break_out

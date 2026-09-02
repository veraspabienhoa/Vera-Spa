from datetime import date
from pathlib import Path

import vera_auto_check as auto_check
from vera_web_v2_break_return_penalty import confirmed_break_return_fact


def _item(**updates):
    item = {
        "date": "02/09/2026",
        "employee_name": "Nhân viên A",
        "break_enabled": True,
        "break_restricted_reason": "",
        "break_out": "18:29:00",
        "break_in": "20:07:01",
        "break_planned_minutes": 90,
        "break_return_deadline": "19:59:00",
    }
    item.update(updates)
    return item


def test_confirmed_late_return_is_eligible_after_return_faceid():
    fact = confirmed_break_return_fact(_item(), date(2026, 9, 2))

    assert fact is not None
    assert fact["employee"] == "Nhân viên A"
    assert fact["late_minutes"] == 9
    assert fact["break_out"].strftime("%H:%M:%S") == "18:29:00"
    assert fact["deadline"].strftime("%H:%M:%S") == "19:59:00"
    assert fact["break_in"].strftime("%H:%M:%S") == "20:07:01"


def test_open_on_time_disabled_or_restricted_break_is_not_penalized():
    today = date(2026, 9, 2)

    assert confirmed_break_return_fact(_item(break_in=""), today) is None
    assert confirmed_break_return_fact(_item(break_in="19:59:00"), today) is None
    assert confirmed_break_return_fact(_item(break_enabled=False), today) is None
    assert confirmed_break_return_fact(_item(break_restricted_reason="Đi trễ không phép"), today) is None


def test_canonical_penalty_deadline_never_exceeds_2000():
    fact = confirmed_break_return_fact(_item(
        break_out="18:41:02",
        break_in="21:04:41",
        break_return_deadline="20:11:02",
    ), date(2026, 9, 2))

    assert fact is not None
    assert fact["deadline"].strftime("%H:%M:%S") == "20:00:00"
    assert fact["late_minutes"] == 65


def test_current_outside_policy_names_use_inclusive_boundaries():
    names = (
        "Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút",
        "Ra ngoài vào muộn nhỏ hơn hoặc bằng 60 phút",
        "Ra ngoài vào muộn nhỏ hơn hoặc bằng 120 phút",
        "Ra ngoài vào muộn trên 120 phút",
    )
    catalog = {auto_check._norm(name): {"name": name} for name in names}

    assert auto_check.outside_reason(catalog, 30)["name"] == names[0]
    assert auto_check.outside_reason(catalog, 31)["name"] == names[1]
    assert auto_check.outside_reason(catalog, 60)["name"] == names[1]
    assert auto_check.outside_reason(catalog, 61)["name"] == names[2]
    assert auto_check.outside_reason(catalog, 120)["name"] == names[2]
    assert auto_check.outside_reason(catalog, 121)["name"] == names[3]


def test_timesoft_sync_runs_break_return_penalty_directly():
    root = Path(__file__).resolve().parents[1]
    sync = (root / "timesoft_sync_job.py").read_text(encoding="utf-8")
    snapshot = (root / "timesoft_snapshot_job.py").read_text(encoding="utf-8")

    assert "def process_break_return_penalties" in sync
    assert "break_return_result = process_break_return_penalties(engine, catalog)" in sync
    assert "ĐỒNG BỘ TIMESOFT - NGHỈ GIỮA CA" in sync
    assert "timesoft-direct-attendance-penalty-2026-09-02-v2" in snapshot

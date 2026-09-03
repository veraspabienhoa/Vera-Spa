from datetime import date, datetime
from pathlib import Path

import pandas as pd

import vera_missing_checkin_notifications as alerts


ROOT = Path(__file__).resolve().parents[1]


def test_faceid_employee_alias_is_canonicalized():
    frame = pd.DataFrame([{
        "EmployeeName": "Lễ Tân A",
        "MachineTimeStr": "03/09/2026 09:29:58",
    }])
    assert alerts._faceid_employees(frame, {"le tan a": "letan.a"}) == {"letan.a"}


def test_blank_summary_row_does_not_count_as_faceid():
    frame = pd.DataFrame([{"EmployeeName": "Locker A", "MachineTimeCheckInStr": ""}])
    assert alerts._faceid_employees(frame, {"locker a": "locker.a"}) == set()


def test_clock_and_event_key_are_stable():
    work_day = date(2026, 9, 3)
    assert alerts._clock(work_day, "09:30").isoformat() == "2026-09-03T09:30:00"
    assert alerts._clock(work_day, "không có") is None
    assert alerts._event_key(work_day, "Locker A", "Ca 1") == alerts._event_key(work_day, " locker a ", "ca 1")


def test_alert_is_wired_before_auto_check_and_into_fast_tail():
    sync_source = (ROOT / "timesoft_sync_job.py").read_text(encoding="utf-8")
    snapshot_source = (ROOT / "timesoft_snapshot_job.py").read_text(encoding="utf-8")
    call = "missing_checkin_notifications.notify_missing_scheduled_checkins"
    assert sync_source.index(call) < sync_source.index("# Auto Check PostgreSQL-only")
    assert call in snapshot_source
    assert "THRESHOLD_MINUTES = 15" in (ROOT / "vera_missing_checkin_notifications.py").read_text(encoding="utf-8")


def test_timezone_aware_now_can_be_compared_to_schedule_clock():
    # Production passes datetime.now(VN_TZ); the notifier intentionally makes
    # it naive because TimeSoft and work-schedule clocks are local wall time.
    aware = datetime.fromisoformat("2026-09-03T09:45:00+07:00")
    assert aware.replace(tzinfo=None) >= alerts._clock(date(2026, 9, 3), "09:30")

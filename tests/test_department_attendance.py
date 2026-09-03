from pathlib import Path

from vera_department_attendance_rules import schedule_late_minutes


ROOT = Path(__file__).resolve().parents[1]


def test_schedule_late_minutes_uses_web_v2_shift_start():
    assert schedule_late_minutes("09:29:59", "09:30") == 0
    assert round(schedule_late_minutes("09:37:30", "09:30")) == 8
    assert schedule_late_minutes("00:35:00", "17:30") == 425


def test_locker_letan_attendance_is_schedule_only_without_break_policy():
    source = (ROOT / "vera_web_v2_department_attendance.py").read_text(encoding="utf-8")
    assert "vera_work_schedule" in source
    assert "vera_work_shift_definition" in source
    assert '"break_enabled": False' in source
    assert '"break_out": ""' in source
    assert '"break_in": ""' in source


def test_department_switches_and_notification_audience_are_wired():
    control = (ROOT / "vera_web_v2_department_attendance.py").read_text(encoding="utf-8")
    notify = (ROOT / "vera_auto_penalty_notifications.py").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/SnapshotPage.jsx").read_text(encoding="utf-8")
    assert "attendance_enabled" in control
    assert "notifications_enabled" in control
    assert "IN ('admin','quanly')" in notify
    assert "CHẤM CÔNG THEO BỘ PHẬN" in page

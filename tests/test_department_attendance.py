from pathlib import Path
from datetime import date

from vera_department_attendance_rules import schedule_late_minutes
import vera_web_v2_department_attendance as department


ROOT = Path(__file__).resolve().parents[1]


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _LockerScheduleConnection:
    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM vera_work_schedule ws" in sql:
            return _Rows([{
                "department": "locker", "shift_code": "Ca 1",
                "start_time": "09:30", "end_time": "18:30",
                "overtime_shift": "", "overtime_start_time": "", "overtime_end_time": "",
            }])
        if "FROM vera_app_setting" in sql:
            return _Rows([])
        raise AssertionError(sql)


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


def test_schedule_department_overrides_generic_employee_role_for_locker():
    item = {
        "check_in": "09:59:43", "break_enabled": True,
        "break_out": "17:14:27", "break_status": "Đang nghỉ giữa ca",
    }
    result = department.apply_schedule_to_record(
        _LockerScheduleConnection(), item, date(2026, 9, 3), "Lê Sơn", "nhanvien",
    )
    assert result is not None
    assert result["break_department"] == "Locker"
    assert result["break_enabled"] is False
    assert result["break_out"] == ""
    assert result["break_status"] == "Locker không áp dụng chính sách nghỉ giữa ca"


def test_department_switches_and_notification_audience_are_wired():
    control = (ROOT / "vera_web_v2_department_attendance.py").read_text(encoding="utf-8")
    notify = (ROOT / "vera_auto_penalty_notifications.py").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/SnapshotPage.jsx").read_text(encoding="utf-8")
    assert "attendance_enabled" in control
    assert "notifications_enabled" in control
    assert "IN ('admin','quanly')" in notify
    assert "CHẤM CÔNG THEO BỘ PHẬN" in page

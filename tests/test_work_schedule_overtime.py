from datetime import date
from pathlib import Path

from vera_web_v2_work_schedule import ScheduleRow, _validate_row


ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = {
    "locker": {"Ca 1": {}, "Ca 2": {}},
    "letan": {"Ca 1": {}, "Ca 2": {}},
}


def row(department, **updates):
    values = {
        "work_date": date(2026, 9, 3),
        "employee_username": "Test",
        "employee_name": "Test",
        "department": department,
        "shift_code": "Giờ làm" if department == "quanly" else "Ca 1",
        "start_time": "09:00" if department == "quanly" else "",
        "end_time": "17:00" if department == "quanly" else "",
    }
    values.update(updates)
    return ScheduleRow(**values)


def test_all_three_departments_accept_shift_overtime():
    for department in ("quanly", "locker", "letan"):
        normalized = _validate_row(row(department, overtime_shift="TC Ca 2"), DEFINITIONS)
        assert normalized[2] == "TC Ca 2"


def test_all_three_departments_accept_custom_overtime_range():
    for department in ("quanly", "locker", "letan"):
        normalized = _validate_row(row(
            department,
            overtime_shift="Từ giờ tới giờ",
            overtime_start_time="20:00",
            overtime_end_time="01:00",
        ), DEFINITIONS)
        assert normalized[2:] == ("Từ giờ tới giờ", "20:00", "01:00")


def test_schedule_page_has_monthly_statistics_and_clickable_total_highlight():
    source = (ROOT / "web-v2/src/pages/WorkSchedulePage.jsx").read_text(encoding="utf-8")
    assert "THỐNG KÊ THÁNG" in source
    assert "employeeMatchesTotal" in source
    assert "Từ giờ tới giờ" in source
    assert "Tổng bộ phận" in source

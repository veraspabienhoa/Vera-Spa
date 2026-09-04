from datetime import date
from pathlib import Path

from vera_web_v2_work_schedule import ScheduleRow, _validate_row


ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = {
    "locker": {"Ca 1": {}, "Ca 2": {}},
    "letan": {"Ca 1": {}, "Ca 2": {}},
    "tapvu": {"Ca 1": {}, "Ca 2": {}},
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


def test_all_four_departments_accept_shift_overtime():
    for department in ("quanly", "locker", "letan", "tapvu"):
        normalized = _validate_row(row(department, overtime_shift="TC Ca 2"), DEFINITIONS)
        assert normalized[2] == "TC Ca 2"


def test_all_four_departments_accept_custom_overtime_range():
    for department in ("quanly", "locker", "letan", "tapvu"):
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
    assert "row.work_date <= yesterdayIso" in source
    assert "mobile-cell-summary ${mobileShiftClass}" in source
    assert "BÁN COMBO" in source
    assert "combo_customer_phone" in source


def test_schedule_persists_combo_sale_details_for_management_and_reception():
    source = (ROOT / "vera_web_v2_work_schedule.py").read_text(encoding="utf-8")
    for field in (
        "combo_sold", "combo_sale_date", "combo_customer_name",
        "combo_customer_phone", "combo_ticket", "combo_note",
    ):
        assert field in source
    assert 'row.department in {"quanly", "letan"}' in source
    assert 'vera_work_schedule_combo_sale' in source
    assert '@app.get("/v2/work-schedule/combo-sales")' in source
    assert '@app.post("/v2/work-schedule/combo-sales")' in source


def test_staff_status_update_survives_google_credentials_failure():
    source = (ROOT / "vera_web_v2_staff.py").read_text(encoding="utf-8")
    assert '"sync_warning": f"{type(sync_exc).__name__}: {sync_exc}"' in source
    assert "Trạng thái đã lưu; chưa dọn lịch nghỉ tương lai" in source

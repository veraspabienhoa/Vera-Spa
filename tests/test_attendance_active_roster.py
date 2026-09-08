from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_attendance_reader_merges_all_active_employees():
    source = (ROOT / "vera_web_v2_attendance_query_perf.py").read_text(encoding="utf-8")
    assert "def _active_roster" in source
    assert "Trạng thái làm việc" in source
    assert "= 'đang làm việc'" in source
    assert "def _append_missing_active_employees" in source
    assert "attendance_roster_only" in source
    assert "Danh sách nhân viên PostgreSQL" in source


def test_attendance_roster_covers_every_vera_department():
    source = (ROOT / "vera_web_v2_attendance_query_perf.py").read_text(encoding="utf-8")
    for role in ("nhanvien", "leader", "quanly", "letan", "locker", "tapvu", "admin"):
        assert f'"{role}"' in source
    for department in ("Nhân viên + Leader", "Quản lý", "Lễ tân", "Locker", "Tạp vụ", "Admin"):
        assert department in source


def test_timesoft_shift_cannot_override_postgres_employee_department():
    source = (ROOT / "vera_web_v2_attendance_query_perf.py").read_text(encoding="utf-8")
    controls = (ROOT / "vera_web_v2_department_attendance.py").read_text(encoding="utf-8")
    assert 'base["break_department"] = ROLE_DEPARTMENT.get(role, role or "Khác")' in source
    assert 'if not str(base.get("break_department") or "").strip()' not in source
    assert 'role in {"quanly", "admin"}' in source
    assert 'BREAK_DEPARTMENTS = ("letan", "locker", "tapvu")' in controls
    assert "apply_midshift_break_control" in source
    assert "apply_midshift_break_result_control" in source
    assert 'schedules = _schedule_map(conn, start, end)' in source

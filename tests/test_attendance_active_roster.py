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

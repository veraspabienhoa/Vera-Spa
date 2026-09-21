from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_normalized_leave_and_attendance_schema_has_required_indexes():
    source = (ROOT / "vera_web_v2_hr_enhancements.py").read_text(encoding="utf-8")
    for table in ["vera_hr_leave_period", "vera_hr_attendance_log", "vera_hr_leave_return_audit"]:
        assert table in source
    for index in ["idx_hr_leave_username_created", "idx_hr_leave_department_range", "idx_hr_attendance_username_time"]:
        assert index in source


def test_checkin_handler_is_idempotent_and_closes_canonical_leave():
    source = (ROOT / "vera_web_v2_hr_enhancements.py").read_text(encoding="utf-8")
    assert "ON CONFLICT (employee_username,checkin_at,source) DO NOTHING" in source
    assert 'canonical_payload["Trạng thái kỳ nghỉ"] = "Đã kết thúc"' in source
    assert 'canonical_payload["Ngày quay lại làm việc"]' in source
    assert 'str(leave.get("end_source") or "") == "manual"' in source


def test_overlap_api_and_admin_heatmap_are_wired():
    backend = (ROOT / "vera_web_v2_hr_enhancements.py").read_text(encoding="utf-8")
    api = (ROOT / "vera_web_v2_api_v38.py").read_text(encoding="utf-8")
    frontend = (ROOT / "web-v2/src/components/LongLeaveAdminPanel.jsx").read_text(encoding="utf-8")
    assert '/v2/hr/leaves/overlap' in backend
    assert "install_hr_enhancement_routes" in api
    assert "TỔNG QUAN & KIỂM TRA XUNG ĐỘT NGHỈ PHÉP" in frontend
    assert "exceeds_threshold" in frontend

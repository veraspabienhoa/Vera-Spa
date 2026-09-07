from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_employee_self_service_permissions_cannot_be_revoked_by_feature_overrides():
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")

    assert '_EMPLOYEE_SELF_SERVICE_ROLES = {"nhanvien", "leader", "locker", "tapvu"}' in api
    assert '"leave_detail_edit"' in api
    assert '"leave_detail_delete"' in api
    assert "role in _EMPLOYEE_SELF_SERVICE_ROLES and feature in _EMPLOYEE_SELF_SERVICE_FEATURES" in api


def test_employee_create_uses_three_day_notice_and_unpaid_uses_one_day():
    shared = (ROOT / "vera_web_v2_api_shared.py").read_text(encoding="utf-8")
    queue = (ROOT / "vera_web_v2_leave_sync_queue.py").read_text(encoding="utf-8")
    preview = (ROOT / "vera_web_v2_leave_preview.py").read_text(encoding="utf-8")

    assert 'days = 1 if "khong phep" in norm(item.get("leave_type", "")) else 3' in shared
    assert "current_day + timedelta(days=days)" in shared
    assert "role not in api_module._EMPLOYEE_SELF_SERVICE_ROLES" in queue
    assert 'role not in {"nhanvien", "leader", "locker", "tapvu"}' in preview


def test_employee_can_edit_and_delete_only_own_rows_inside_notice_window():
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")
    ui = (ROOT / "web-v2/src/lib/leaveRecordPermissions.js").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")

    delete_guard = api.split("def _validate_delete_permission", 1)[1].split(
        "def _validate_edit_permission", 1
    )[0]
    edit_guard = api.split("def _validate_edit_permission", 1)[1].split(
        "def _validate_and_prepare", 1
    )[0]
    assert "Nhân viên chỉ được xóa lịch nghỉ của chính mình." in delete_guard
    assert "_validate_employee_self_service_notice(target, row)" in delete_guard
    assert "Nhân viên chỉ được sửa lịch nghỉ của chính mình." in edit_guard
    assert "_validate_employee_self_service_notice(target, row, item)" in edit_guard
    assert "return item, True" in edit_guard

    assert "EMPLOYEE_SELF_SERVICE_ROLES.has(roleKey)" in ui
    assert "Boolean(isOwnRecord) && employeeDateAllowed" in ui
    assert "currentLeaveType: item?.leave_type" in page
    assert "isOwnRecord: normalizeSearch(item?.employee_name)" in page


def test_leave_payloads_include_type_for_one_day_frontend_rule():
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")

    assert '"name": item["name"], "leave_type": item["leave_type"], "days": item["days"]' in api
    assert "employee_name, leave_reason, leave_type," in api

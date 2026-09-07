from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_employee_self_service_permissions_follow_dynamic_policy():
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")

    assert '_EMPLOYEE_SELF_SERVICE_ROLES = {"nhanvien", "leader", "locker", "tapvu"}' in api
    assert '"leave_detail_edit"' in api
    assert '"leave_detail_delete"' in api
    assert "load_employee_self_service_policy(conn)[\"enabled\"]" in api


def test_employee_create_uses_dynamic_notice_policy():
    shared = (ROOT / "vera_web_v2_api_shared.py").read_text(encoding="utf-8")
    queue = (ROOT / "vera_web_v2_leave_sync_queue.py").read_text(encoding="utf-8")
    preview = (ROOT / "vera_web_v2_leave_preview.py").read_text(encoding="utf-8")

    assert "employee_self_service_notice_days(employee_policy, item)" in shared
    assert "current_day + timedelta(days=days)" in shared
    assert 'not employee_policy["enabled"]' in queue
    assert 'not employee_policy["enabled"]' in preview


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
    assert "_validate_employee_self_service_notice(conn, target, row)" in delete_guard
    assert "Nhân viên chỉ được sửa lịch nghỉ của chính mình." in edit_guard
    assert "_validate_employee_self_service_notice(conn, target, row, item)" in edit_guard
    assert "return item, True" in edit_guard

    assert "EMPLOYEE_SELF_SERVICE_ROLES.has(roleKey)" in ui
    assert "Boolean(isOwnRecord) && employeeDateAllowed" in ui
    assert "employeeSelfServicePolicy?.enabled !== false" in ui
    assert "currentLeaveType: item?.leave_type" in page
    assert "isOwnRecord: normalizeSearch(item?.employee_name)" in page
    assert "canEditRecord(item) && (employeeSelfService || item.leave_date === date)" in page
    assert "canEditRecord(item) && item.leave_date === date" not in page
    assert "recordReasonsByDate[item?.leave_date]" in page


def test_leave_payloads_include_type_for_one_day_frontend_rule():
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")

    assert '"name": item["name"], "leave_type": item["leave_type"], "days": item["days"]' in api
    assert "employee_name, leave_reason, leave_type," in api


def test_employee_policy_is_editable_in_official_rules():
    rules = (ROOT / "vera_web_v2_rules.py").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/RulesPage.jsx").read_text(encoding="utf-8")

    assert '@app.put("/v2/rules/employee-self-service-policy")' in rules
    assert '"employee_self_service_policy": employee_self_service_policy' in rules
    assert "Tạm dừng nội quy" in page
    assert "Kích hoạt nội quy" in page
    assert "regular_notice_days" in page
    assert "unpaid_notice_days" in page


def test_employee_policy_defaults_and_validation():
    from vera_employee_self_service_policy import normalize_policy, notice_days

    default = normalize_policy(None)
    assert default == {"enabled": True, "regular_notice_days": 3, "unpaid_notice_days": 1}
    changed = normalize_policy({"enabled": False, "regular_notice_days": 7, "unpaid_notice_days": 2})
    assert changed["enabled"] is False
    assert notice_days(changed, {"leave_type": "Có phép"}) == 7
    assert notice_days(changed, {"leave_type": "Không phép"}) == 2

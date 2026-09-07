from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_leave_list_day_filter_syncs_viewed_date_before_react_click():
    source = (ROOT / "web-v2/src/lib/leaveListDateFilterSync.js").read_text(encoding="utf-8")
    main = (ROOT / "web-v2/src/main.jsx").read_text(encoding="utf-8")

    assert 'Lọc thời gian danh sách' in source
    assert "label === 'Hôm nay'" in source
    assert "label === 'Hôm qua'" in source
    assert "document.addEventListener('click'" in source
    assert "}, true)" in source
    assert "startLeaveListDateFilterSync()" in main


def test_manager_and_frontdesk_share_same_day_special_group_ui_rules():
    source = (ROOT / "web-v2/src/lib/leaveRecordPermissions.js").read_text(encoding="utf-8")

    assert "new Set(['letan', 'quanly'])" in source
    assert "EDITOR_ROLES.has(roleKey)" in source
    assert "recordDate === today && letanReasonGroup(currentReason)" in source


def test_employee_toolbar_uses_real_react_selects_and_current_search_input():
    source = (ROOT / "web-v2/src/lib/employeeToolbarRecovery.js").read_text(encoding="utf-8")
    main = (ROOT / "web-v2/src/main.jsx").read_text(encoding="utf-8")

    assert "select.classList.remove('vera-typing-select-source')" in source
    assert "select.dataset.veraTypingSearch = '1'" in source
    assert ".staff-control-panel .staff-toolbar" in source
    assert ".staff-search input" in source
    assert ".staff-list-panel .vera-list-name-search" in source
    assert "removeDuplicateListSearch" in source
    assert "startEmployeeToolbarRecovery()" in main

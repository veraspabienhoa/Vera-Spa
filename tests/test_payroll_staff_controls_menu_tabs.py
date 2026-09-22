from ui_source import read_ui_source
from pathlib import Path


def test_employee_flags_support_profile_exemption_and_payroll_exclusion():
    backend = Path("vera_web_v2_staff.py").read_text(encoding="utf-8")
    page = read_ui_source(Path("web-v2/src/pages/EmployeePage.jsx"))
    profile = Path("vera_web_v2_profile.py").read_text(encoding="utf-8")
    reminder = read_ui_source(Path("web-v2/src/components/ProfileCompletionReminder.jsx"))

    assert "profile_requirement_exempt: bool | None" in backend
    assert "payroll_excluded: bool | None" in backend
    assert '"Miễn yêu cầu đủ hồ sơ"' in backend
    assert '"Không tính lương"' in backend
    assert '"profile_requirement_exempt"' in profile
    assert "profile.profile_requirement_exempt" in reminder
    assert "Miễn đủ hồ sơ" in page
    assert "Không tính lương" in page
    assert "profile_requirement_exempt" in page
    assert "payroll_excluded" in page


def test_payroll_exclusion_is_enforced_server_side_and_status_is_returned():
    backend = Path("vera_web_v2_payroll.py").read_text(encoding="utf-8")

    assert "payroll_excluded" in backend
    assert "Không tính lương" in backend
    assert 'if bool(employee.get("payroll_excluded")):' in backend
    assert '"__employment_status"' in backend
    assert "employment_status" in backend


def test_payroll_has_column_totals_and_requested_quick_filters():
    page = read_ui_source(Path("web-v2/src/pages/PayrollPageEnhanced.jsx"))

    for label in (
        "Lương", "Trách nhiệm / hỗ trợ", "Hoàn trả tích lũy", "Tích lũy",
        "Phí sinh hoạt", "Vi phạm kỳ này", "Nợ vi phạm kỳ trước", "Tiền ứng",
        "Hỗ trợ Locker", "Thực nhận",
    ):
        assert label in page
    assert "payroll-column-summary" in page
    assert "draftNonPositiveOnly" in page
    assert "draftFormerOnly" in page
    assert "Thực nhận ≤ 0" in page
    assert ">Đã nghỉ việc</button>" in page


def test_sidebar_menu_items_are_links_for_native_right_click_open_new_tab():
    shell = read_ui_source(Path("web-v2/src/components/AppShell.jsx"))

    assert "const menuPageUrl = (id) =>" in shell
    assert "url.searchParams.set('standalone', '1')" in shell
    assert "href={ready ? menuPageUrl(id) : '#'}" in shell
    assert "chooseFromLink(event, id, ready)" in shell
    assert "Có thể nhấp chuột phải để mở tab mới" in shell

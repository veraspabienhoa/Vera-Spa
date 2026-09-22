from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_department_payroll_has_dedicated_menu_and_route():
    shell = (ROOT / "web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")
    app = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")
    payroll = (ROOT / "web-v2/src/pages/PayrollPageV38.jsx").read_text(encoding="utf-8")
    panel = (ROOT / "web-v2/src/pages/DepartmentPayrollPanel.jsx").read_text(encoding="utf-8")
    assert "id: 'payroll', label: 'Lương KTV'" in shell
    assert "id: 'department-payroll', label: 'Lương hành chánh'" in shell
    assert "page === 'department-payroll' && <DepartmentPayrollPanel" in app
    assert "import DepartmentPayrollPanel" not in payroll
    assert "Chọn tất cả có email" in panel
    assert "Tính lương nháp từ Thống kê tháng" in panel
    assert "Tháng hiện tại chỉ tính đến hôm nay" in panel
    assert "NHÂN VIÊN ỨNG LƯƠNG" in panel
    assert "Hoàn thành bảng lương" in panel
    assert "LỊCH SỬ BẢNG LƯƠNG" in panel
    assert "/v2/department-payroll/combined/history" in panel


def test_mobile_leave_reason_text_is_half_sized():
    styles = (ROOT / "web-v2/src/styles.css").read_text(encoding="utf-8")
    mobile_reason = styles.split(".leave-records-table .reason-edit-cell select", 1)[1].split("}", 1)[0]
    assert "font-size: clamp(4px, 1.125vw, 5px) !important" in mobile_reason


def test_work_schedule_monthly_statistics_include_today_for_draft_payroll():
    schedule = (ROOT / "web-v2/src/pages/WorkSchedulePage.jsx").read_text(encoding="utf-8")
    assert "row.work_date <= todayIso" in schedule
    assert "đến ngày hiện tại" in schedule
    assert "đến hết ngày hôm qua" not in schedule


def test_official_department_payroll_is_one_record_per_month():
    backend = (ROOT / "vera_web_v2_department_payroll.py").read_text(encoding="utf-8")
    assert 'item.get("month") == body.month' in backend
    assert "history.append" in backend
    assert "department_payroll_combined_history" in backend
    assert "_clean_combined_rows" in backend


def test_salary_configuration_is_split_into_two_employee_tables():
    panel = (ROOT / "web-v2/src/pages/DepartmentPayrollPanel.jsx").read_text(encoding="utf-8")
    backend = (ROOT / "vera_web_v2_department_payroll.py").read_text(encoding="utf-8")
    assert "BẢNG 1 · LƯƠNG GIỜ" in panel
    assert "BẢNG 2 · LƯƠNG THÁNG" in panel
    assert "Mỗi nhân viên là một dòng" in panel
    assert '"operations": [row for row in rows' in backend
    assert '"support": "Support"' in backend
    assert 'Object.entries(settings)' in panel
    assert '"department_employee_salary_configs"' in backend


def test_department_email_uses_the_standard_employee_layout():
    backend = (ROOT / "vera_web_v2_department_payroll.py").read_text(encoding="utf-8")
    assert "payroll._payroll_email_subject" in backend
    assert "payroll._payroll_email_text" in backend
    assert "payroll._payroll_email_html" in backend
    assert '"email_layout": payroll.PAYROLL_EMAIL_TEMPLATE_RELEASE' in backend


def test_employee_config_supports_department_search_and_explicit_rows():
    panel = (ROOT / "web-v2/src/pages/DepartmentPayrollPanel.jsx").read_text(encoding="utf-8")
    backend = (ROOT / "vera_web_v2_department_payroll.py").read_text(encoding="utf-8")
    styles = (ROOT / "web-v2/src/styles.css").read_text(encoding="utf-8")
    assert "salary_employee_catalog" in backend
    assert "employeeCandidates" in panel
    assert "Tìm nhân viên" in panel
    assert "-- Chọn nhân viên --" in panel
    assert "Thêm dòng" in panel
    assert "removeEmployeeRow" in panel
    assert ".department-config-table{display:block;width:100%;max-width:100%;overflow-x:auto" in styles
    assert ".department-payroll-page{order:880;min-width:0;max-width:100%;overflow:hidden}" in styles


def test_department_payroll_rows_fit_without_horizontal_page_scroll():
    styles = (ROOT / "web-v2/src/styles.css").read_text(encoding="utf-8")
    assert ".department-payroll-table { width: 100%; max-width: 100%; overflow-x: clip; }" in styles
    assert ".department-payroll-table table { width: 100%; min-width: 0; table-layout: fixed" in styles


def test_salary_advance_form_has_searchable_employee_date_and_valid_amount_input():
    ledger = (ROOT / "web-v2/src/lib/departmentSalaryAdvanceLedger.js").read_text(encoding="utf-8")
    assert 'type="search" autocomplete="off" role="combobox"' in ledger
    assert 'placeholder="Tìm và chọn nhân viên trong danh sách…"' in ledger
    assert "renderEmployeeSuggestions" in ledger
    assert "data-advance-employee-option" in ledger
    assert "records.every((record) => existingPanel.contains(record.target))" in ledger
    assert "<datalist" not in ledger
    assert 'placeholder="dd-mm-yyyy"' in ledger
    assert "parseDisplayDate" in ledger
    assert 'data-advance-amount required' in ledger
    assert "toLocaleString('vi-VN')" in ledger
    assert 'step="1000"' not in ledger

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_department_payroll_has_dedicated_menu_and_route():
    shell = (ROOT / "web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")
    app = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")
    payroll = (ROOT / "web-v2/src/pages/PayrollPageV38.jsx").read_text(encoding="utf-8")
    panel = (ROOT / "web-v2/src/pages/DepartmentPayrollPanel.jsx").read_text(encoding="utf-8")
    assert "id: 'payroll', label: 'Lương KTV'" in shell
    assert "id: 'department-payroll', label: 'HC'" in shell
    assert "page === 'department-payroll' && <DepartmentPayrollPanel" in app
    assert "import DepartmentPayrollPanel" not in payroll
    assert "Chọn tất cả có email" in panel


def test_official_department_payroll_is_one_record_per_month():
    backend = (ROOT / "vera_web_v2_department_payroll.py").read_text(encoding="utf-8")
    assert 'item.get("month") == body.month' in backend
    assert "history.append" in backend


def test_salary_configuration_is_split_into_two_employee_tables():
    panel = (ROOT / "web-v2/src/pages/DepartmentPayrollPanel.jsx").read_text(encoding="utf-8")
    backend = (ROOT / "vera_web_v2_department_payroll.py").read_text(encoding="utf-8")
    assert "BẢNG 1 · QUẢN LÝ / LỄ TÂN / LOCKER" in panel
    assert "BẢNG 2 · TẠP VỤ" in panel
    assert "Mỗi nhân viên là một dòng" in panel
    assert '"operations": [row for row in rows' in backend
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

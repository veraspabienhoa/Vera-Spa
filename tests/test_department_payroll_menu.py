from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_department_payroll_has_dedicated_menu_and_route():
    shell = (ROOT / "web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")
    app = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")
    payroll = (ROOT / "web-v2/src/pages/PayrollPageV38.jsx").read_text(encoding="utf-8")
    panel = (ROOT / "web-v2/src/pages/DepartmentPayrollPanel.jsx").read_text(encoding="utf-8")
    assert "id: 'department-payroll', label: 'Lương bộ phận'" in shell
    assert "page === 'department-payroll' && <DepartmentPayrollPanel" in app
    assert "import DepartmentPayrollPanel" not in payroll
    assert "Chọn tất cả có email" in panel


def test_official_department_payroll_is_one_record_per_month():
    backend = (ROOT / "vera_web_v2_department_payroll.py").read_text(encoding="utf-8")
    assert 'item.get("month") == body.month' in backend
    assert "history.append" in backend

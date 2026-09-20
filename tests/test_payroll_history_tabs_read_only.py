from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_payroll_has_separate_calculate_and_history_tabs():
    wrapper = (ROOT / "web-v2/src/pages/PayrollPageV38.jsx").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/PayrollPageEnhanced.jsx").read_text(encoding="utf-8")
    assert "const [payrollTab, setPayrollTab] = useState('calculate')" in wrapper
    assert 'activeTab={payrollTab}' in wrapper
    assert '>Tính lương</button>' in page
    assert '>Lịch sử bảng lương</button>' in page
    assert 'payroll-history-panel' in page
    assert 'payroll-tab-history>section.panel:not(.payroll-history-panel)' in wrapper


def test_saved_payroll_cannot_be_reopened_for_editing():
    wrapper = (ROOT / "web-v2/src/pages/PayrollPageV38.jsx").read_text(encoding="utf-8")
    api = (ROOT / "vera_web_v2_api_v38.py").read_text(encoding="utf-8")
    assert "PayrollSavedAdminPanel" not in wrapper
    assert "install_payroll_saved_edit_routes" not in api


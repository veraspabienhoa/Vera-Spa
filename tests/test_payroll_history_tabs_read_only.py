from ui_source import read_ui_source
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_payroll_history_is_displayed_in_its_own_tab():
    wrapper = read_ui_source((ROOT / "web-v2/src/pages/PayrollPageV38.jsx"))
    page = read_ui_source((ROOT / "web-v2/src/pages/PayrollPageEnhanced.jsx"))
    assert "const [payrollTab, setPayrollTab] = useState('calculate')" in wrapper
    assert 'activeTab={payrollTab}' in wrapper
    assert '>Tính lương</button>' in page
    assert '>Lịch sử bảng lương</button>' in page
    assert 'payroll-history-panel' in page
    assert "const [historyOpen, setHistoryOpen] = useState(false)" in page
    assert 'hidden={!historyOpen}' in page
    assert page.index('payroll-history-panel') > page.index('payroll-default-config-panel')
    assert 'PayrollHistorySearch' in page
    assert 'payroll-tab-history>section.panel:not(.payroll-history-panel)' in wrapper
    assert 'payroll-tab-calculate>.payroll-history-panel{display:none}' in wrapper
    assert "onTabChange?.('history')\n    showHistory()" in page


def test_saved_payroll_can_be_reopened_and_history_can_be_emailed():
    page = read_ui_source((ROOT / "web-v2/src/pages/PayrollPageEnhanced.jsx"))
    api = (ROOT / "vera_web_v2_api_v38.py").read_text(encoding="utf-8")
    saved_edit = (ROOT / "vera_web_v2_payroll_saved_edit.py").read_text(encoding="utf-8")
    assert "install_payroll_saved_edit_routes" in api
    assert '@app.post("/v2/payroll/saved-batches/{batch_id:path}/edit")' in saved_edit
    assert "Sửa bảng lương" in page
    assert "emailHistory" in page
    assert "Chọn tất cả nhân viên theo bộ lọc (mọi trang) để gửi email" in page
    assert "Gửi email (${historySelected.length})" in page

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYROLL_PAGE = ROOT / "web-v2/src/pages/PayrollPageEnhanced.jsx"


def test_payroll_page_has_canonical_recalculation_button():
    source = PAYROLL_PAGE.read_text(encoding="utf-8")
    api = (ROOT / "web-v2/src/lib/api.js").read_text(encoding="utf-8")
    backend = (ROOT / "vera_web_v2_payroll_live_tour_tip.py").read_text(encoding="utf-8")

    assert "fetchAutomaticPayrollSource" not in source
    assert "File TimeSoft" not in source
    assert "Upload & tính lương" not in source
    assert "Tính lương từ TIP" in source
    assert "const recalculatePayroll = () => run('recalculate'" in source
    assert "veraApi.calculatePayrollFromTips(month, periodNo)" in source
    assert "/v2/payroll/calculate-from-tips" in api
    assert '"source": "TIP nhân viên từ Live Tour"' in backend
    assert "Tính lại lương" in source
    assert "Đang tính lại…" in source


def test_all_ktv_payroll_money_editors_format_thousands_while_typing():
    source = PAYROLL_PAGE.read_text(encoding="utf-8")

    assert "import VeraMoneyInput" in source
    assert "numberInputDisplayValue" not in source
    assert 'type="number"' not in source
    assert source.count("<VeraMoneyInput") >= 7


def test_employee_search_clears_bulk_email_selection_and_selects_only_exact_visible_match():
    source = PAYROLL_PAGE.read_text(encoding="utf-8")

    assert "const [searchSelectionMode, setSearchSelectionMode] = useState(false)" in source
    assert "setSelected(names.length === 1 ? names : [])" in source
    assert "const allVisibleSelected = !searchSelectionMode" in source
    assert "setSearchSelectionMode(false)" in source

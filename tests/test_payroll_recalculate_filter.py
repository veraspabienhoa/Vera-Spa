from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYROLL_PAGE = ROOT / "web-v2/src/pages/PayrollPageEnhanced.jsx"


def test_payroll_page_has_canonical_recalculation_button():
    source = PAYROLL_PAGE.read_text(encoding="utf-8")

    assert "async function fetchAutomaticPayrollSource(month, periodNo)" in source
    assert "/v2/payroll/timesoft-source.xlsx?" in source
    assert "const recalculatePayroll = () => run('recalculate'" in source
    assert "await veraApi.calculatePayroll(sourceFile, month, periodNo)" in source
    assert "Tính lại lương" in source
    assert "Đang tính lại…" in source


def test_employee_search_clears_bulk_email_selection_and_selects_only_exact_visible_match():
    source = PAYROLL_PAGE.read_text(encoding="utf-8")

    assert "const [searchSelectionMode, setSearchSelectionMode] = useState(false)" in source
    assert "setSelected(names.length === 1 ? names : [])" in source
    assert "const allVisibleSelected = !searchSelectionMode" in source
    assert "setSearchSelectionMode(false)" in source

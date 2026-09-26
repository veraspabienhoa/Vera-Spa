from pathlib import Path


def test_revenue_net_summary_and_web_entry_permission_contract():
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert 'REVENUE_ENTRY_FEATURE = "revenue_entry_create"' in backend
    assert 'revenue_group[REVENUE_ENTRY_FEATURE] = "Nhập Thu Chi"' in backend
    assert 'permissions.FEATURES[REVENUE_ENTRY_FEATURE] = "Nhập Thu Chi"' in backend
    assert '@app.post("/v2/revenue/entry")' in backend
    assert 'require_feature(conn, ident, REVENUE_ENTRY_FEATURE)' in backend
    assert 'revenue_store.insert_web_entries(' in backend
    assert '"storage": "postgresql"' in backend
    assert '"net_income": round(total_income - total_expense, 2)' in backend
    assert '"balance": round(total_income - total_expense - tip, 2)' in backend
    assert "revenue_auto.totals(days)" in backend
    assert '"can_create_entry": can_create_entry' in backend

    assert 'label: \'TỔNG THU - TỔNG CHI\'' in page
    assert 'canCreateEntry = Boolean(sourceReady && !sharedSource.changing && !autoMode && data?.source === revenueSource && data?.can_create_entry)' in page
    assert '<form className="revenue-entry-form"' in page
    assert 'NHẬP DOANH THU - CHI PHÍ' in page
    assert "const canViewAdminRevenueSummary = role === 'admin' || role === 'giamdoc'" in page
    assert 'saveRevenueEntry' in page
    assert 'Còn lại = (Tổng thu - Tổng chi) - Tiền TIP trong kỳ' in page
    assert '.revenue-grid{display:grid;grid-template-columns:repeat(5' in page
    assert '.revenue-card.balance{grid-column:1/-1}' in page


def test_revenue_entry_can_save_thu_and_chi_together():
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert "income_amount: float" in backend
    assert "expense_amount: float" in backend
    assert 'entries.append(("Thu", income_amount, body.income_note))' in backend
    assert 'entries.append(("Chi", expense_amount, body.expense_note))' in backend
    assert '"saved_rows": saved_rows' in backend
    assert "confirm_duplicate: bool = False" in backend
    assert "find_duplicate_web_entries" in backend
    assert '"code": "duplicate_revenue_entry"' in backend

    assert "entryIncomeAmount" in page
    assert "entryExpenseAmount" in page
    assert "Ghi chú Thu" in page
    assert "Ghi chú Chi" in page
    assert "Lưu Thu + Chi" in page
    assert "income_amount: Number(incomeAmount || 0)" in page
    assert "expense_amount: Number(expenseAmount || 0)" in page
    assert "Có thể xóa để nhập nội dung Thu mới." not in page
    assert "Có thể xóa để nhập nội dung Chi mới." not in page
    assert "auto-note-empty" in page
    assert "window.confirm(saveError.message)" in page

from pathlib import Path


def test_revenue_net_summary_and_web_entry_permission_contract():
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert 'REVENUE_ENTRY_FEATURE = "revenue_entry_create"' in backend
    assert 'revenue_group[REVENUE_ENTRY_FEATURE] = "Nhập Thu Chi"' in backend
    assert 'permissions.FEATURES[REVENUE_ENTRY_FEATURE] = "Nhập Thu Chi"' in backend
    assert '@app.post("/v2/revenue/entry")' in backend
    assert 'require_feature(conn, ident, REVENUE_ENTRY_FEATURE)' in backend
    assert 'worksheet.append_rows(rows, value_input_option="USER_ENTERED")' in backend
    assert 'put("Loại giao dịch"' in backend
    assert 'put("Số tiền"' in backend
    assert 'put("Ngày giao dịch"' in backend
    assert 'put("Ghi chú"' in backend
    assert 'summary["net_income"] = round(summary["total_income"] - summary["total_expense"], 2)' in backend
    assert 'summary["balance"] = round(summary["net_income"] - tip, 2)' in backend
    assert '"can_create_entry": can_create_entry' in backend

    assert 'label: \'TỔNG THU - TỔNG CHI\'' in page
    assert 'canCreateEntry = Boolean(data?.can_create_entry)' in page
    assert '<form className="revenue-entry-form"' in page
    assert 'NHẬP BÁO CÁO THU CHI' in page
    assert 'saveRevenueEntry' in page
    assert 'Còn lại = (Tổng thu - Tổng chi) - Tiền TIP trong kỳ' in page
    assert '.revenue-grid{display:grid;grid-template-columns:repeat(5' in page
    assert '.revenue-card.balance{grid-column:1/-1}' in page


def test_revenue_entry_can_save_thu_and_chi_together():
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert "income_amount: float" in backend
    assert "expense_amount: float" in backend
    assert 'rows.append(build_row("Thu", income_amount, body.income_note))' in backend
    assert 'rows.append(build_row("Chi", expense_amount, body.expense_note))' in backend
    assert 'timestamp = now.strftime("%d/%m/%Y %H:%M:%S")' in backend
    assert '"saved_rows": len(rows)' in backend

    assert "entryIncomeAmount" in page
    assert "entryExpenseAmount" in page
    assert "Ghi chú Thu" in page
    assert "Ghi chú Chi" in page
    assert "Lưu Thu + Chi" in page
    assert "income_amount: Number(incomeAmount || 0)" in page
    assert "expense_amount: Number(expenseAmount || 0)" in page

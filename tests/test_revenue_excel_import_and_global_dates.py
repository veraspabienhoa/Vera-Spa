from pathlib import Path


def test_revenue_excel_import_append_replace_and_full_admin_edit_are_wired():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    store = Path("vera_revenue_store.py").read_text(encoding="utf-8")

    assert '@app.post("/v2/revenue/import.xlsx")' in backend
    assert 'mode: Literal["append", "replace"]' in backend
    assert "import_ledger_xlsx(" in backend
    assert 'def import_ledger_xlsx' in store
    assert 'mode == "replace"' in store
    assert "UPDATE {TABLE} SET is_deleted=true" in store
    assert "existing_keys" in store
    assert "Import thêm mới" in page
    assert "Import thay toàn bộ" in page
    assert "handleRevenueImport(event, 'append')" in page
    assert "handleRevenueImport(event, 'replace')" in page

    for label in ["Ngày giao dịch (DD-MM-YYYY)", "Ngày nhập (DD-MM-YYYY)", "Giờ nhập (HH:MM:SS)", "Người nhập"]:
        assert label in page
    assert "entered_at=COALESCE(:entered_at, entered_at)" in store


def test_all_visible_web_v2_calendar_dates_share_vera_date_input():
    component = Path("web-v2/src/components/VeraDateInput.jsx").read_text(encoding="utf-8")
    leave = Path("web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")
    revenue = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert 'type="text"' in component and 'type="date"' in component
    assert "onChange={changeText}" in component and "onChange={pickDate}" in component
    assert '<VeraDateInput' in leave
    assert '<VeraDateInput' in revenue
    assert "<RevenueDateInput" not in revenue

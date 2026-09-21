from pathlib import Path


def test_weekly_shift_badge_is_in_quick_tools_without_circled_number():
    page = Path("web-v2/src/pages/LiveTourPage.jsx").read_text(encoding="utf-8")
    controls = Path("web-v2/src/pages/LiveTourControls.css").read_text(encoding="utf-8")

    topbar = page.split('className="tour-topbar"', 1)[1].split('className="tour-control-layout"', 1)[0]
    quick = page.split('className="tour-quick-tools"', 1)[1].split('live-tour-admin-controls-toggle', 1)[0]
    assert "live-tour-weekly-shift" not in topbar
    assert "live-tour-weekly-shift" in quick
    assert "CA TUẦN NÀY ①" not in page
    assert "Ca tuần ①" not in page
    assert ">CA TUẦN NÀY<" in page
    assert ">Ca tuần này<" in page
    assert "Ca 1" in page and "Ca 2" in page
    assert ".live-tour-page .live-tour-weekly-shift .weekly-desktop{display:none}" in controls


def test_revenue_ledger_filters_match_visible_ledger_columns():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    route = Path("vera_web_v2_purchase_reconcile.py").read_text(encoding="utf-8")

    ledger_filters = page.split("activeTab === 'ledger' ? <div className=\"detail-filter-secondary\">", 1)[1].split("</div> : <div", 1)[0]
    for label in ("Ngày", "Loại giao dịch", "Số tiền", "Ghi chú", "Ngày nhập", "Người nhập"):
        assert f"<label>{label}" in ledger_filters
    assert "ledgerEnteredDate" in page
    assert "params.set('entered_date', ledgerEnteredDate)" in page
    assert "entered_date: date | None = Query(default=None)" in route


def test_leave_list_hides_manual_sheet_sync_button():
    page = Path("web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")
    list_actions = page.split('<div className="list-actions">', 1)[1].split("</div>", 1)[0]
    assert "Đồng bộ Web V2 → LichNghi_VeraSpa" not in list_actions
    assert "Export to Excel" in list_actions


def test_combo_import_is_an_independent_permission():
    permissions = Path("vera_web_v2_permissions.py").read_text(encoding="utf-8")
    grants = Path("vera_web_v2_live_tour_permissions.py").read_text(encoding="utf-8")
    backend = Path("vera_web_v2_live_tour.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/LiveTourPage.jsx").read_text(encoding="utf-8")

    assert '"live_tour_combo_import": "Nhập combo khách hàng"' in permissions
    assert '"live_tour_combo_import": {"live_tour_customers_view"}' in permissions
    assert '"combo_import": "live_tour_combo_import"' in grants
    assert 'if action == "combo_import":\n        return "live_tour_combo_import"' in backend
    assert 'Chỉ Admin được nhập combo.' not in backend
    assert "capability('combo_import'" in page
    assert "{canImportCombo && <button" in page

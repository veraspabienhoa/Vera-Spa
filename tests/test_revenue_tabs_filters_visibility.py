from pathlib import Path


def test_revenue_summary_is_admin_and_giamdoc_only_in_ui():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    assert "const canViewAdminRevenueSummary = role === 'admin' || role === 'giamdoc'" in page
    assert "canViewAdminRevenueSummary && <section className=\"revenue-period\"" in page
    assert "canViewAdminRevenueSummary && canEditTip" in page
    assert "canViewAdminRevenueSummary && <div className=\"admin-revenue-summary\"" in page


def test_revenue_entry_heading_and_detail_tabs_are_renamed():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    assert "NHẬP DOANH THU - CHI PHÍ" in page
    assert ">Chi tiết Doanh thu - Chi phí</button>" in page
    assert ">Báo cáo mua hàng</button>" in page
    assert "Quản lý Thu Chi · Input</h3>" not in page
    assert "BaoCaoMuaHang.xlsb · Input</h3>" not in page


def test_revenue_detail_tabs_have_independent_filters_like_report_filter_panel():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    assert "const [detailPreset, setDetailPreset]" in page
    assert "const [detailStart, setDetailStart]" in page
    assert "const [detailEnd, setDetailEnd]" in page
    assert "const [ledgerNoteFilter, setLedgerNoteFilter]" in page
    assert "const [ledgerAmountFilter, setLedgerAmountFilter]" in page
    assert "const [purchaseItemFilter, setPurchaseItemFilter]" in page
    assert "const [purchaseBuyerFilter, setPurchaseBuyerFilter]" in page
    assert "const [purchaseUserFilter, setPurchaseUserFilter]" in page
    assert ">Hôm qua</button>" in page
    assert ">Hôm nay</button>" in page
    assert "Xóa lọc chi tiết" in page


def test_purchase_reconciliation_stays_on_overview_after_detail_tabs():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    tabs_at = page.index('className="revenue-tabs"')
    reconcile_at = page.index("activeTab === 'overview' && <section className=\"reconcile-panel\"")
    assert reconcile_at > tabs_at
    assert "Đối chiếu chi mua hàng" in page

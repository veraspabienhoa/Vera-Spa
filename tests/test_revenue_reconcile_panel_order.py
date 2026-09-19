from pathlib import Path


def test_revenue_reconcile_is_separate_from_detail_tabs_and_stays_on_overview():
    source = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    tabs = source.index('className="revenue-tabs"')
    ledger_tab = source.index("Doanh thu-Chi phí", tabs)
    purchase_tab = source.index("Báo cáo mua hàng", ledger_tab)
    reconcile = source.index("Đối chiếu chi mua hàng", purchase_tab)

    assert tabs < ledger_tab < purchase_tab < reconcile
    assert "activeTab === 'overview' && <section className=\"reconcile-panel\"" in source
    assert "reconcile-grid" not in source

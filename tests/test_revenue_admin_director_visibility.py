from pathlib import Path


def test_revenue_overview_and_external_links_are_admin_director_only():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert "const canViewAdminRevenueSummary = role === 'admin' || role === 'giamdoc'" in page
    assert '{canViewAdminRevenueSummary && <div className="revenue-actions">' in page
    assert "canViewAdminRevenueSummary && <button" in page
    assert ">Tổng quan</button>" in page
    assert "if (!canViewAdminRevenueSummary && activeTab === 'overview') setActiveTab('ledger')" in page
    assert "canViewAdminRevenueSummary && activeTab === 'overview'" in page
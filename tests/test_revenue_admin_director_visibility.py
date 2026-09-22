from ui_source import read_ui_source
from pathlib import Path


def test_revenue_overview_is_admin_director_only_and_external_entry_is_removed():
    page = read_ui_source(Path("web-v2/src/pages/RevenuePage.jsx"))

    assert "const canViewAdminRevenueSummary = role === 'admin' || role === 'giamdoc'" in page
    assert 'Mở Google Form' not in page
    assert 'Xem báo cáo' not in page
    assert "canViewAdminRevenueSummary && <button" in page
    assert ">Tổng quan</button>" in page
    assert "if (!canViewAdminRevenueSummary && activeTab === 'overview') setActiveTab('ledger')" in page
    assert "canViewAdminRevenueSummary && activeTab === 'overview'" in page

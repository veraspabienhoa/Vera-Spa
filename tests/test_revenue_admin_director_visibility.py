from ui_source import read_ui_source
from pathlib import Path
import re


def test_revenue_overview_is_admin_director_only_and_external_entry_is_removed():
    page = read_ui_source(Path("web-v2/src/pages/RevenuePage.jsx"))

    assert "const canViewAdminRevenueSummary = role === 'admin' || role === 'giamdoc'" in page
    assert 'Mở Google Form' not in page
    # The retired external report link must stay removed; an internal filter
    # submit button can legitimately use the same label.
    anchors = re.findall(r'<a\b[\s\S]*?</a>', page)
    assert not any('Xem báo cáo' in anchor for anchor in anchors)
    assert "canViewAdminRevenueSummary && <button" in page
    assert ">Tổng quan</button>" in page
    assert "if (!canViewAdminRevenueSummary && activeTab === 'overview') setActiveTab('ledger')" in page
    assert "canViewAdminRevenueSummary && activeTab === 'overview'" in page

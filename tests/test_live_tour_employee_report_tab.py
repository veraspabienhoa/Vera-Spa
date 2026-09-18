from pathlib import Path


def test_employee_analytics_has_its_own_report_tab_with_full_filters():
    page = Path("web-v2/src/pages/LiveTourReportsPage.jsx").read_text(encoding="utf-8")

    assert "['employee', 'Theo nhân viên']" in page
    assert "<LiveTourFilters value={filters} onChange={setFilters}" in page
    assert "tab === 'employee' && <LiveTourEmployeeRevenueBreakdown rows={reports}/>" in page
    assert "tab === 'revenue' && <LiveTourEmployeeRevenueBreakdown" not in page
    assert "tab !== 'employee' && (tab === 'performance'" in page

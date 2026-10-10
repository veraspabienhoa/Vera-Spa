from pathlib import Path


def test_employee_analytics_has_its_own_report_tab_with_full_filters():
    page = Path("web-v2/src/pages/LiveTourReportsPage.jsx").read_text(encoding="utf-8")

    assert "['employee', 'Theo nhân viên']" in page
    assert "<LiveTourFilters showDate={tab !== 'history'} value={filters} onChange={setFilters}" in page
    assert "tab === 'employee' && <LiveTourEmployeeRevenueBreakdown summary={data.employee_totals}/>" in page
    assert "reportReadQuery(appliedFilters, tab, performanceTiming, page)" in page
    assert "veraApi.liveTourReports(query, { signal: controller.signal })" in page
    assert "tab === 'employee' ? 'employee' : 'reports', { ...appliedFilters" in page
    assert "<LiveTourEmployeeRevenueBreakdown rows={rows}" not in page
    helper = Path("web-v2/src/lib/liveTourReportPage.js").read_text(encoding="utf-8")
    assert "'date', 'date_from', 'date_to', 'employee', 'customer', 'service', 'bill_no'" in helper
    assert "summarizeEmployeeRevenue(allRows)" in helper  # Legacy compatibility also aggregates the full filter.
    assert "summarizeEmployeeRevenue(rows)" not in helper
    assert "tab === 'revenue' && <LiveTourEmployeeRevenueBreakdown" not in page
    assert "tab !== 'employee' && tab !== 'history' && (tab === 'performance'" in page

from pathlib import Path


def test_revenue_tip_uses_native_date_filters_and_readonly_auto_total():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    helper = Path("web-v2/src/lib/revenueTipPeriod.js").read_text(encoding="utf-8")

    assert '<VeraDateInput aria-label="Ngày bắt đầu Tiền TIP"' in page
    assert '<VeraDateInput aria-label="Đến ngày Tiền TIP"' in page
    date_component = Path("web-v2/src/components/VeraDateInput.jsx").read_text(encoding="utf-8")
    assert 'type="text"' in date_component
    assert 'type="date"' in date_component
    assert 'aria-label="Tiền TIP trong kỳ tự động"' in page
    assert 'readOnly' in page
    assert 'loadPeriodTip(tipStart, tipEnd, controller.signal, !sharedSourceSupported)' in page
    assert "return invoiceRowDate(row)" in helper
    filters = Path("web-v2/src/lib/liveTourFilters.js").read_text(encoding="utf-8")
    assert "row?.effective_at || row?.booked_at || row?.created_at || row?.business_date" in filters
    assert "revenueTipValue(row?.tip)" in helper

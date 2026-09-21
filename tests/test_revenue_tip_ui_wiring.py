from pathlib import Path


def test_revenue_tip_uses_native_date_filters_and_readonly_auto_total():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    helper = Path("web-v2/src/lib/revenueTipPeriod.js").read_text(encoding="utf-8")

    assert '<RevenueDateInput ariaLabel="Ngày bắt đầu Tiền TIP"' in page
    assert '<RevenueDateInput ariaLabel="Đến ngày Tiền TIP"' in page
    assert 'type="date"' in page
    assert 'position:absolute;inset:0;width:100%!important;height:100%!important' in page
    assert 'aria-label="Tiền TIP trong kỳ tự động"' in page
    assert 'readOnly' in page
    assert 'revenueTipTotal(liveTourRows, defaultTipStartDate, defaultTipEndDate)' in page
    assert "row?.business_date || row?.effective_at" in helper
    assert "revenueTipValue(row?.tip)" in helper

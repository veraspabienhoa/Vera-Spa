from pathlib import Path


def test_manual_and_hybrid_use_same_current_period_tip_and_shared_date_control():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert "if (result.source !== 'manual_tip_auto')" not in page
    assert "loadPeriodTip(tipStart, tipEnd, controller.signal, !sharedSourceSupported)" in page
    assert "const todayIsoVietnam = () =>" in page
    assert "useState(todayIsoVietnam)" in page
    assert '<VeraDateInput aria-label="Ngày giao dịch"' in page
    assert '<VeraDateInput aria-label="Ngày bắt đầu Tiền TIP"' in page
    assert '<VeraDateInput aria-label="Đến ngày Tiền TIP"' in page
    assert "const defaultTipStartDate = defaultRevenueTipStart(result.current_date)" in page
    assert "setEntryDate(result.current_date)" not in page
    assert 'grid-template-areas:"title title" "date ."' in page

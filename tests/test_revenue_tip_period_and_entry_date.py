from pathlib import Path


def test_manual_and_hybrid_use_same_current_period_tip_and_date_control():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    # Manual and Dịch Manual · Tip Auto must share the same Live Tour rows and
    # the same current-period start/end before calculating tip.
    assert "if (result.source !== 'manual_tip_auto')" not in page
    assert "revenueTipTotal(liveTourRows, defaultTipStartDate, defaultTipEndDate)" in page
    assert "result.source === 'manual_tip_auto'\n              ? Number(result.tip_revenue" not in page

    # Transaction date is always a valid YYYY-MM-DD internal value on every device,
    # while VeraDateInput renders DD-MM-YYYY. Width remains controlled by the existing grid.
    assert "const todayIsoVietnam = () =>" in page
    assert "useState(todayIsoVietnam)" in page
    assert ".revenue-entry-form .entry-date .vera-date-input{width:100%;max-width:none}" in page
    assert 'grid-template-areas:"title title" "date ."' in page

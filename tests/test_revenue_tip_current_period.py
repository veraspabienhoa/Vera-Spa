from pathlib import Path


def test_tip_period_uses_current_half_month_not_revenue_dataset_start():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    helper = Path("web-v2/src/lib/revenueTipPeriod.js").read_text(encoding="utf-8")

    assert "const defaultTipStartDate = defaultRevenueTipStart(result.current_date)" in page
    assert "const defaultTipStartDate = result.start_date" not in page
    assert "Number(match[3]) <= 15 ? '01' : '16'" in helper
    assert "loadPeriodTip(tipStart, tipEnd, controller.signal, !sharedSourceSupported)" in page

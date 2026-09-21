from pathlib import Path


def test_revenue_three_date_controls_use_full_native_hit_area_and_visible_ddmmyyyy():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert page.count("<RevenueDateInput") == 3
    assert "display || 'dd-mm-yyyy'" in page
    assert 'type="date"' in page
    assert 'position:absolute;inset:0;width:100%!important;height:100%!important' in page
    assert "opacity:.001" in page
    assert "setEntryDate(result.current_date)" in page
    assert "const defaultTipStartDate = result.start_date || result.period_tip_start" in page
    # Keep the previously approved revenue form width/grid unchanged.
    assert 'grid-template-columns:minmax(0,1fr) minmax(0,2fr)' in page
    assert 'grid-template-areas:"title title" "date ."' in page

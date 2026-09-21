from pathlib import Path


def test_revenue_date_controls_use_shared_manual_and_picker_component():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    component = Path("web-v2/src/components/VeraDateInput.jsx").read_text(encoding="utf-8")

    assert page.count("<RevenueDateInput") == 0
    assert page.count("<VeraDateInput") >= 8
    assert 'type="text"' in component
    assert 'type="date"' in component
    assert "setEntryDate(result.current_date)" in page
    assert "const defaultTipStartDate = defaultRevenueTipStart(result.current_date)" in page
    assert 'grid-template-columns:minmax(0,1fr) minmax(0,2fr)' in page
    assert 'grid-template-areas:"title title" "date ."' in page

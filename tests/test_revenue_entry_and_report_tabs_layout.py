from pathlib import Path


def test_revenue_notes_use_their_own_row():
    source = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert '"date income expense save"' in source
    assert '"income-note income-note expense-note expense-note"' in source
    assert ".entry-note:not(.entry-expense-note){grid-area:income-note}" in source
    assert ".entry-expense-note{grid-area:expense-note}" in source


def test_mobile_report_tabs_do_not_break_words():
    page = Path("web-v2/src/pages/LiveTourReportsPage.jsx").read_text(encoding="utf-8")
    styles = Path("web-v2/src/pages/LiveTourReportsPage.css").read_text(encoding="utf-8")

    assert 'className="feature-page spa-page live-tour-reports-page"' in page
    assert ".live-tour-reports-page .spa-tabs" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in styles
    assert "word-break: keep-all" in styles

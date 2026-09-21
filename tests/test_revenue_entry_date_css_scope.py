from pathlib import Path


def test_revenue_entry_submit_button_css_does_not_cover_shared_date_picker():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert ".revenue-entry-form > button{grid-area:save;" in page
    assert ".revenue-entry-form button{grid-area:save;" not in page
    assert ".revenue-entry-form .entry-date .vera-date-input{width:100%;max-width:none}" in page
    assert '<VeraDateInput aria-label="Ngày giao dịch"' in page

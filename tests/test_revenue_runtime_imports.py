from pathlib import Path


def test_revenue_page_keeps_date_component_import_for_remaining_filters():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    assert "import VeraDateInput from '../components/VeraDateInput'" in page
    assert page.count("<VeraDateInput") >= 5
    assert page.count("<RevenueDateInput") == 3

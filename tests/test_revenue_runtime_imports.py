from pathlib import Path


def test_revenue_page_uses_shared_date_component_for_all_date_boxes():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    assert "import VeraDateInput from '../components/VeraDateInput'" in page
    assert page.count("<VeraDateInput") >= 8
    assert "<RevenueDateInput" not in page

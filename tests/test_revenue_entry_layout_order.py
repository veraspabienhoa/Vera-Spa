from pathlib import Path


def test_revenue_period_follows_server_entry_form():
    source = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    form = source.index('<form className="revenue-entry-form"')
    save = source.index("Lưu Thu + Chi", form)
    period = source.index('aria-label="Khoảng dữ liệu Doanh thu"', save)
    assert form < save < period
    assert "Mở Google Form" not in source

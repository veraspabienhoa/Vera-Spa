from pathlib import Path


def test_revenue_period_and_external_actions_follow_entry_form():
    source = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    form = source.index('<form className="revenue-entry-form"')
    save = source.index("Lưu Thu + Chi", form)
    period = source.index('aria-label="Khoảng dữ liệu Doanh thu"', save)
    google = source.index("Mở Google Form", period)
    report = source.index("Xem báo cáo", google)

    assert form < save < period < google < report

from pathlib import Path


def test_revenue_period_follows_server_entry_form():
    source = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    form = source.index('<form className="revenue-entry-form"')
    save = source.index("Lưu Thu + Chi", form)
    period = source.index('aria-label="Khoảng dữ liệu Doanh thu"', save)
    assert form < save < period
    assert "Mở Google Form" not in source


def test_mobile_revenue_fields_and_tip_dates_keep_the_requested_layout():
    source = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert 'grid-template-areas:"title" "date" "income" "income-note" "expense" "expense-note" "save"' in source
    assert 'grid-template-areas:"title" "date" "income" "expense" "income-note"' not in source
    assert '.revenue-tip-editor .vera-date-input>input[type="text"]{display:block;width:100%' in source
    assert '.revenue-tip-editor .vera-native-date-picker{left:auto!important;right:4px!important;width:38px!important' in source

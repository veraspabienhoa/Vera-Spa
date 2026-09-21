from pathlib import Path


def test_revenue_mobile_date_and_entered_by_filter_contract():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    css = Path("web-v2/src/styles.css").read_text(encoding="utf-8")
    route = Path("vera_web_v2_purchase_reconcile.py").read_text(encoding="utf-8")

    assert 'aria-label="Phạm vi doanh thu"' not in page
    assert "setLedgerEnteredByFilter" in page
    assert 'placeholder="Tìm người nhập"' in page
    assert "params.set('entered_by', ledgerEnteredByFilter)" in page
    assert 'entered_by: str = Query(default="", max_length=200)' in route
    assert 'entered_by_key in norm(row.get("entered_by"))' in route

    # Calendar hit-area is now shared by desktop and mobile instead of a
    # touch-only 46px override. Manual DD-MM-YYYY typing remains available.
    assert ".vera-date-input > .vera-native-date-picker" in css
    assert "pointer-events: auto;" in css
    assert ".vera-date-input > .vera-date-picker-button { pointer-events: none; }" in css

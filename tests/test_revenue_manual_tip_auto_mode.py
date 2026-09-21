from pathlib import Path


def test_revenue_manual_tip_auto_mode_and_period_contract():
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert 'Literal["manual", "auto", "manual_tip_auto"]' in backend
    assert 'source == "manual_tip_auto"' in backend
    assert 'auto_tip = _auto_revenue' in backend
    assert 'REVENUE_PERIOD_START = date(2025, 9, 5)' in backend
    assert '"start_date_label": (start_date or REVENUE_PERIOD_START).strftime("%d-%m-%Y")' in backend

    assert "Dịch Manual · Tip Auto" in page
    assert "Chế độ thủ công: giữ nguyên luồng nhập Thu/Chi hiện tại." not in page
    assert 'grid-template-areas:"title title" "date ." "income income-note" "expense expense-note" "save save"' in page
    assert "Dùng ngày này · {data?.current_date_label || '—'}" in page
    assert "systemTipMode" in page

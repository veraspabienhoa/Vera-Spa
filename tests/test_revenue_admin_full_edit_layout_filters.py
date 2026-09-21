from pathlib import Path


def test_revenue_admin_full_edit_layout_and_filters_contract():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    store = Path("vera_revenue_store.py").read_text(encoding="utf-8")

    assert "Loại giao dịch (Thu hoặc Chi)" in page
    assert "Ngày giao dịch (DD-MM-YYYY)" in page
    assert "Ngày nhập (DD-MM-YYYY)" in page
    assert "Giờ nhập (HH:MM:SS)" in page
    assert "window.prompt('Người nhập'" in page
    assert "entered_date: enteredDate" in page
    assert "entered_time: String(enteredTime).trim()" in page
    assert "entered_by_name: enteredBy" in page
    assert "entered_date: date | None" in backend
    assert "entered_time: str | None" in backend
    assert "entered_at=COALESCE(:entered_at, entered_at)" in store

    assert "Có thể xóa để nhập nội dung Thu mới." not in page
    assert "Có thể xóa để nhập nội dung Chi mới." not in page
    assert "auto-note-empty" in page
    assert "['next_month', 'Tháng sau']" not in page
    assert 'grid-template-columns:minmax(0,1fr) minmax(0,2fr)' in page
    assert 'grid-template-areas:"title title" "date ." "income income-note" "expense expense-note" "save save"' in page

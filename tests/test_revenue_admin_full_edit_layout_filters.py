from pathlib import Path


def test_revenue_admin_full_edit_layout_and_filters_contract():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    store = Path("vera_revenue_store.py").read_text(encoding="utf-8")

    assert "PHIẾU THU CHI" in page
    assert "Loại giao dịch<select" in page
    assert "Ngày giao dịch<VeraDateInput" in page
    assert "Ngày nhập<VeraDateInput" in page
    assert "Giờ nhập<input" in page
    assert "window.prompt" not in page
    assert "entered_date: entryEditor.enteredDate" in page
    assert "entered_time: entryEditor.enteredTime" in page
    assert "entered_by_name: entryEditor.enteredBy" in page
    assert "entered_date: date | None" in backend
    assert "entered_time: str | None" in backend
    assert "entered_at=COALESCE(:entered_at, entered_at)" in store

    assert "Có thể xóa để nhập nội dung Thu mới." not in page
    assert "Có thể xóa để nhập nội dung Chi mới." not in page
    assert "auto-note-empty" in page
    assert "['next_month', 'Tháng sau']" not in page
    assert 'grid-template-columns:minmax(0,1fr) minmax(0,2fr)' in page
    assert 'grid-template-areas:"title title" "date ." "income income-note" "expense expense-note" "save save"' in page

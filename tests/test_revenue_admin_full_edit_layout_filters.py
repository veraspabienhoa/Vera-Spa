from pathlib import Path


def test_revenue_admin_full_edit_layout_and_filters_contract():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    store = Path("vera_revenue_store.py").read_text(encoding="utf-8")

    assert "Loại giao dịch (Thu hoặc Chi)" in page
    assert "Ngày giao dịch (DD-MM-YYYY)" in page
    assert "window.prompt('Người nhập'" in page
    assert "entered_by_name: enteredBy" in page
    assert "entered_by_name: str | None" in backend
    assert "entered_by_name=COALESCE(:entered_by_name, entered_by_name)" in store
    update_sql = store.split("def update_entry", 1)[1].split("def soft_delete_entry", 1)[0]
    assert "entered_at=" not in update_sql
    assert "created_at=" not in update_sql

    assert "Có thể xóa để nhập nội dung Thu mới." not in page
    assert "Có thể xóa để nhập nội dung Chi mới." not in page
    assert "auto-note-empty" in page
    assert "['next_month', 'Tháng sau']" not in page
    assert 'grid-template-columns:minmax(0,1fr) minmax(0,2fr)' in page
    assert 'grid-template-areas:"title title" "date ." "income income-note" "expense expense-note" "save save"' in page

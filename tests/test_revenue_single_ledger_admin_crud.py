from pathlib import Path


def test_revenue_page_uses_single_manual_ledger_and_admin_actions():
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    assert "BẢN GHI DOANH THU · ADMIN" not in page
    assert "Sửa dòng đã chọn" in page
    assert "Xóa dòng đã chọn" in page
    assert 'type="checkbox"' in page
    assert "Ngày giao dịch<VeraDateInput" in page
    assert "Ngày giao dịch (YYYY-MM-DD)" not in page
    assert "reconcileFilters.filter(([value]) => value !== 'next_month')" not in page
    assert 'aria-label="Phạm vi doanh thu"' not in page


def test_main_revenue_ledger_has_ids_and_dd_mm_yyyy_labels():
    route = Path("vera_web_v2_purchase_reconcile.py").read_text(encoding="utf-8")
    store = Path("vera_revenue_store.py").read_text(encoding="utf-8")
    assert "revenue_store.list_entries(conn, start_date=start, end_date=end)" in route
    assert '"id": int(row["id"])' in store
    assert 'strftime("%d-%m-%Y")' in store
    assert '"entered_date_label"' in store

from pathlib import Path

import vera_web_v2_revenue_leave_list as revenue


def test_all_time_range_has_no_bounds():
    assert revenue._range_bounds("all") == (None, None)


def test_revenue_source_toggle_and_admin_crud_are_wired():
    backend = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    store = Path("vera_revenue_store.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    assert 'source: Literal["manual", "auto", "manual_tip_auto"]' in backend
    assert 'time_range: str = Query("all")' in backend
    assert 'service_revenue' in backend and 'tip_revenue' in backend and 'total_revenue' in backend
    assert '@app.patch("/v2/revenue/entries/{entry_id}")' in backend
    assert '@app.delete("/v2/revenue/entries/{entry_id}")' in backend
    assert 'Chỉ Admin được sửa hoặc xóa báo cáo doanh thu.' in backend
    assert "entered_at" not in store.split("def update_entry", 1)[1].split("def soft_delete_entry", 1)[0].split("UPDATE {TABLE}", 1)[1].split("WHERE id", 1)[0]
    assert "is_deleted=true" in store
    assert "vera_revenue_entry_audit" in store
    assert "Manual · Thủ công" in page and "Auto · Tự động hệ thống" in page
    assert "['all', 'Tất cả']" in page
    assert "Tự động = Tiền dịch vụ + Tiền tip" in page

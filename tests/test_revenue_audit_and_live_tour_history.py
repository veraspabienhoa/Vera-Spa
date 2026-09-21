from pathlib import Path


def test_revenue_admin_audit_duplicate_and_push_contracts():
    routes = Path("vera_web_v2_revenue_leave_list.py").read_text(encoding="utf-8")
    store = Path("vera_revenue_store.py").read_text(encoding="utf-8")
    settings = Path("vera_web_v2_notification_settings.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")

    assert '@app.get("/v2/revenue/audit")' in routes
    assert '@app.get("/v2/revenue/audit/export.xlsx")' in routes
    assert '@app.get("/v2/revenue/duplicates")' in routes
    assert '@app.get("/v2/revenue/duplicates/export.xlsx")' in routes
    assert "def list_audit_entries" in store
    assert "def duplicate_analysis" in store
    assert "revenue_manual_changes" in settings
    assert "BackgroundTasks" in routes
    assert "Sửa dòng đã chọn" in page and "Xóa dòng đã chọn" in page
    assert "Lịch sử sửa, xóa" in page
    assert "KIỂM TRA DỮ LIỆU TRÙNG" in page
    assert "activeTab === 'duplicates'" in page
    assert "isAdmin || (row.entered_date" in page
    assert "required_entered_date=None if admin_unrestricted" in routes
    assert "window.prompt" not in page


def test_live_tour_board_history_keeps_every_board_column_and_exports():
    relational = Path("vera_live_tour_relational.py").read_text(encoding="utf-8")
    backend = Path("vera_web_v2_live_tour.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/LiveTourReportsPage.jsx").read_text(encoding="utf-8")
    api = Path("web-v2/src/lib/api.js").read_text(encoding="utf-8")

    assert 'BOARD_HISTORY_TABLE = "vera_live_tour_board_history"' in relational
    assert "before_payload JSONB" in relational and "after_payload JSONB" in relational
    assert '@app.get("/v2/live-tour/board-history")' in backend
    assert '@app.get("/v2/live-tour/board-history/export.xlsx")' in backend
    assert '[f"Trước · {column}" for column in BOARD_COLUMNS]' in backend
    assert '[f"Sau · {column}" for column in BOARD_COLUMNS]' in backend
    assert "Lịch sử Live Tour" in page
    assert "liveTourBoardHistory" in api and "exportLiveTourBoardHistory" in api


def test_revenue_export_matches_attached_seven_column_template_style():
    export = Path("vera_web_v2_purchase_reconcile.py").read_text(encoding="utf-8")
    assert 'headers = ["Ngày", "Loại giao dịch", "Số tiền", "Ghi chú", "Ngày nhập", "Giờ nhập", "Người nhập"]' in export
    assert 'fgColor="1F513F"' in export
    assert 'widths = [14, 18, 18, 48, 14, 12, 26.55]' in export
    assert 'sheet.freeze_panes = "A2"' in export
    assert "sheet.auto_filter.ref = sheet.dimensions" in export

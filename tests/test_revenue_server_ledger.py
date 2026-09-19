from datetime import datetime
from io import BytesIO

from openpyxl import Workbook

import vera_revenue_store as store


def _workbook_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Input"
    sheet.append(["Dấu thời gian", "Loại giao dịch", "Số tiền", "Ngày giao dịch", "Ghi chú", "Địa chỉ email", "Tháng"])
    sheet.append([datetime(2026, 9, 19, 8, 15, 30), "Thu", 1_250_000, datetime(2026, 9, 18), "Doanh thu", "admin@example.com", datetime(2026, 9, 1)])
    sheet.append([datetime(2026, 9, 19, 8, 16, 45), "Chi", "106.780.00", None, "Mua hàng", "admin@example.com", None])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_revenue_workbook_parser_preserves_rows_and_audit_timestamp():
    rows = store.parse_workbook(_workbook_bytes())
    assert len(rows) == 2
    assert rows[0]["transaction_type"] == "Thu"
    assert rows[0]["amount"] == 1_250_000
    assert rows[0]["transaction_date"].isoformat() == "2026-09-18"
    assert rows[0]["entered_at"].isoformat() == "2026-09-19T08:15:30+07:00"
    assert rows[1]["amount"] == 10_678_000
    assert rows[1]["transaction_date"] is None


def test_revenue_page_displays_server_audit_columns():
    source = open("web-v2/src/pages/RevenuePage.jsx", encoding="utf-8").read()
    assert "Dữ liệu Thu/Chi được lưu trực tiếp trên server VERA SPA" in source
    assert "<th>Ngày nhập</th><th>Giờ nhập</th><th>Người nhập</th>" in source
    assert "row.entered_date_label" in source
    assert "row.entered_time" in source
    assert "row.entered_by" in source
    assert "Mở Google Form" not in source


def test_revenue_backend_writes_postgresql_not_google_sheet():
    source = open("vera_web_v2_revenue_leave_list.py", encoding="utf-8").read()
    assert "revenue_store.insert_web_entries" in source
    assert '"storage": "postgresql"' in source
    assert "worksheet.append_rows" not in source

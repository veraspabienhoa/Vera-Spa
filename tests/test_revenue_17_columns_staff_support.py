from pathlib import Path

import vera_web_v2_live_tour as live
import vera_web_v2_permissions as permissions
import vera_web_v2_staff as staff
from test_live_tour_backend import NOW, state_with


EXPECTED_REPORT_HEADERS = [
    "Ngày", "Ngày giờ hóa đơn", "Nhân viên", "Dịch vụ", "Phòng", "Yêu cầu",
    "Thời gian bắt đầu thực hiện", "Thời gian bắt đầu thực hiện YC", "Số bill",
    "Khách hàng", "Điện thoại", "Tiền dịch vụ", "Giảm giá", "Tip", "Tổng tiền",
    "Thanh toán", "Người tạo",
]


def test_revenue_report_export_matches_attached_17_column_template():
    state = state_with()
    state["invoices"] = [{
        "id": "i1", "discount": 20_000,
        "entries": [{
            "employee_id": "e1", "employee_name": "An", "service": "Body 90", "room": "1.1",
            "request": "YC", "started_at": NOW.isoformat(), "board_started_at": NOW.isoformat(),
            "board_yc_started_at": NOW.isoformat(),
        }],
    }]
    state["reports"] = [{
        "id": "r1", "invoice_id": "i1", "business_date": "2026-09-21", "effective_at": NOW.isoformat(),
        "employee_id": "e1", "employee_name": "An", "service": "Body 90", "room": "1.1", "request": "YC",
        "bill_no": "HD-1", "customer_name": "Khách A", "customer_phone": "0901", "total": 510_000,
        "tip": 30_000, "payment_method": "TIỀN MẶT", "actor": "admin",
    }]

    sheet, headers, rows = live._export_rows(state, "reports", NOW)

    assert sheet == "Bao_cao"
    assert headers == EXPECTED_REPORT_HEADERS and len(headers) == 17
    assert len(rows[0]) == 17
    assert rows[0][6] == "" and rows[0][7] == NOW.isoformat()
    assert rows[0][11:15] == [500_000, 20_000, 30_000, 510_000]


def test_support_is_registered_as_employee_like_department():
    assert "support" in permissions.ROLES
    assert permissions.DEFAULT_ROLE_FEATURES["support"] == permissions.DEFAULT_ROLE_FEATURES["nhanvien"]
    assert "support" in staff.ALL_ROLES
    assert staff._department("support") == "Support"


def test_employee_page_has_bulk_visibility_controls_for_inactive_statuses():
    source = Path("web-v2/src/pages/EmployeePage.jsx").read_text(encoding="utf-8")
    assert "support: 'Support'" in source
    assert "Ẩn tất cả nhân viên nghỉ việc" in source
    assert "Hiện tất cả nhân viên nghỉ việc" in source
    assert "Ẩn tất cả nhân viên tạm nghỉ" in source
    assert "Hiện tất cả nhân viên tạm nghỉ" in source

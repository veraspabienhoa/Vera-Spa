from datetime import date

import vera_web_v2_payroll as payroll


def _sample_row():
    return {
        "Tên Hệ thống": "Cẩm Vân",
        "Tiền Lương": 11_750_000,
        "Tiền Hỗ Trợ Hoàn Lại": 0,
        "Hoàn trả tiền tích lũy": 0,
        "Tích lũy": 0,
        "Chi Phí Sinh Hoạt": 150_000,
        "Tiền phạt trong tháng": 850_000,
        "Vi phạm kỳ trước": 0,
        "Tiền ứng lương": 0,
        "Tiền hỗ trợ Locker": 80_000,
        "Số tiền thực nhận": 10_670_000,
    }


def _sample_violations():
    return [
        {
            "leave_date": date(2026, 8, 20),
            "leave_reason": "Nghỉ không phép",
            "detail": "N5",
            "penalty": 800_000,
        },
        {
            "leave_date": date(2026, 8, 25),
            "leave_reason": "Ra ngoài vào muộn dưới 30 phút",
            "detail": "",
            "penalty": 50_000,
        },
    ]


def test_payroll_email_subject_matches_employee_and_period():
    subject = payroll._payroll_email_subject(
        "Cẩm Vân", date(2026, 8, 16), date(2026, 8, 31)
    )
    assert subject == "Bảng lương Cẩm Vân - 16/08/2026 đến 31/08/2026"


def test_payroll_email_html_matches_requested_labels_and_layout():
    html = payroll._payroll_email_html(
        "Nguyễn Thị Cẩm Vân",
        date(2026, 8, 16),
        date(2026, 8, 31),
        _sample_row(),
        _sample_violations(),
    )
    assert "Chào <strong>Nguyễn Thị Cẩm Vân</strong>" in html
    assert "Hỗ trợ/Hoàn tiền" in html
    assert "Phí sinh hoạt" in html
    assert "Vi phạm trong kỳ" in html
    assert "Tiền Hỗ Trợ Hoàn Lại" not in html
    assert "Chi Phí Sinh Hoạt" not in html
    assert "Tiền phạt trong tháng" not in html
    assert "Chi tiết vi phạm trong kỳ:" in html
    assert "20/08/2026" in html
    assert "800,000 VNĐ" in html
    assert "Số tiền thực nhận: 10,670,000 VNĐ" in html


def test_payroll_email_plain_text_uses_same_requested_labels():
    content = payroll._payroll_email_text(
        "Nguyễn Thị Cẩm Vân",
        date(2026, 8, 16),
        date(2026, 8, 31),
        _sample_row(),
        _sample_violations(),
    )
    assert "Hỗ trợ/Hoàn tiền: 0 VNĐ" in content
    assert "Phí sinh hoạt: 150,000 VNĐ" in content
    assert "Vi phạm trong kỳ: 850,000 VNĐ" in content
    assert "Tổng vi phạm: 850,000 VNĐ" in content

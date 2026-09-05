from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

import vera_web_v2_staff_security as staff_security


ROOT = Path(__file__).resolve().parents[1]


def _sample_image(width: int = 600, height: int = 800) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "#dbe8e1").save(output, format="WEBP", quality=82)
    return output.getvalue()


def test_cccd_ocr_parses_number_date_and_place(monkeypatch):
    monkeypatch.setattr(
        staff_security,
        "_ocr_text",
        lambda _: "Số / No: 075204001234\nNgày cấp / Date of issue: 05/09/2026\nNơi cấp / Place of issue: Cục Cảnh sát QLHC về TTXH",
    )

    assert staff_security._extract_cccd_fields(b"image") == {
        "cccd_number": "075204001234",
        "cccd_issue_date": "05/09/2026",
        "cccd_issue_place": "Cục Cảnh sát QLHC về TTXH",
    }


def test_employee_profile_pdf_is_printable_a4_document():
    content = staff_security._build_employee_profile_pdf(
        {
            "username": "nhanvien01",
            "full_name": "Nguyễn Văn An",
            "birth_date": "01/01/2000",
            "phone": "0900000000",
            "email": "an@example.com",
            "address": "Đồng Nai",
            "role": "nhanvien",
            "employment_status": "Đang làm việc",
            "employment_start_date": "01/09/2026",
            "work_shift": "Ca 1",
            "cccd_number": "075204001234",
            "cccd_issue_date": "05/09/2026",
            "cccd_issue_place": "Cục Cảnh sát QLHC về TTXH",
            "bank_account": "123456789",
            "bank_name": "Vietcombank",
        },
        {"portrait": _sample_image()},
    )

    assert content.startswith(b"%PDF-")
    assert len(content) > 10_000


def test_employee_media_security_and_exports_are_wired():
    security_source = (ROOT / "vera_web_v2_staff_security.py").read_text(encoding="utf-8")
    staff_source = (ROOT / "vera_web_v2_staff.py").read_text(encoding="utf-8")
    identity_ui = (ROOT / "web-v2/src/pages/EmployeeIdentityPanel.jsx").read_text(encoding="utf-8")

    assert "Nhân viên không được xóa ảnh CCCD sau khi đã lưu" in security_source
    assert "side IN ('front','back','portrait')" in security_source
    assert 'abs((width / max(height, 1)) - 0.75)' in security_source
    assert '"Ảnh nhân viên"' in staff_source
    assert "ws.add_image" in staff_source
    assert "Xuất PDF hồ sơ nhân viên" in identity_ui
    assert "Crop / Xoay ảnh đã lưu" in identity_ui


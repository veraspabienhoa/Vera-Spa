from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

import vera_web_v2_staff_security as staff_security


ROOT = Path(__file__).resolve().parents[1]


def _sample_image(width: int = 600, height: int = 800) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "#dbe8e1").save(output, format="WEBP", quality=82)
    return output.getvalue()


def test_cccd_ocr_parses_name_number_date_and_place(monkeypatch):
    monkeypatch.setattr(
        staff_security,
        "_ocr_text",
        lambda _: "Họ và tên / Full name: NGUYỄN VĂN AN\nSố / No: 075204001234\nNgày cấp / Date of issue: 05/09/2026\nNơi cấp / Place of issue: Cục Cảnh sát QLHC về TTXH",
    )

    assert staff_security._extract_cccd_fields(b"image") == {
        "full_name": "NGUYỄN VĂN AN",
        "cccd_number": "075204001234",
        "cccd_issue_date": "05/09/2026",
        "cccd_issue_place": "Cục Cảnh sát QLHC về TTXH",
    }
    assert staff_security._identity_match_key("NGUYỄN VĂN AN") == staff_security._identity_match_key("Nguyen Van An")


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
            "employment_status": "Đã nghỉ việc",
            "employment_start_date": "01/09/2026",
            "employment_end_date": "30/09/2026",
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


def test_selected_employee_profiles_merge_into_one_pdf():
    profile = {
        "username": "nhanvien01",
        "full_name": "Nguyễn Văn An",
        "employment_status": "Đang làm việc",
    }
    content = staff_security._merge_profile_pdfs([
        (profile, {"portrait": _sample_image()}),
        ({**profile, "username": "nhanvien02", "full_name": "Trần Thị Bình"}, {}),
    ])

    assert content.startswith(b"%PDF-")
    assert len(PdfReader(BytesIO(content)).pages) == 2


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
    assert "Camera trước" in identity_ui
    assert "Camera sau" in identity_ui
    assert "facingMode: { ideal: facingMode }" in identity_ui
    assert "setCropInset('left'" in identity_ui
    assert "setCropInset('right'" in identity_ui
    assert "staffSecurityApi.extractIdentity(blob)" in identity_ui
    assert "onPointerDown={beginCropGesture}" in identity_ui
    assert "Vẽ vùng crop tự do" in identity_ui
    assert "Di chuyển ảnh/vùng chọn" in identity_ui
    assert "@app.post(\"/v2/staff/profiles.pdf\")" in security_source
    assert "_merge_profile_pdfs" in security_source

    pdf_builder = security_source.split("def _build_employee_profile_pdf", 1)[1].split("def install_staff_security_routes", 1)[0]
    assert '("Tên đăng nhập",' not in pdf_builder
    assert '("Phân quyền",' not in pdf_builder
    assert '("Ca làm việc",' not in pdf_builder
    assert '("Số tài khoản",' not in pdf_builder
    assert '("Ngân hàng",' not in pdf_builder
    assert 'rows.insert(11, ("Ngày nghỉ việc"' in pdf_builder
    assert 'styles["signature_title"]' in pdf_builder
    assert "validate_saved_identity_matches" in security_source
    assert "ocr_payload" in security_source
    assert '"Giới tính"' in staff_source
    assert '"Quận/Huyện"' in staff_source

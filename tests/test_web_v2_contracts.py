from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from pypdf import PdfReader

from vera_web_v2_contracts import (
    CONTRACT_TYPE_CONFIGS,
    ContractExportRequest,
    DEFAULT_SETTINGS,
    _contract_pdf,
    _ensure_complete_contract_profiles,
    _missing_contract_fields,
)


ROOT = Path(__file__).resolve().parents[1]


def _complete_employee(**overrides):
    employee = {
        "username": "ktv01",
        "employee_name": "Nguyễn Văn An",
        "birth_date": "2000-01-02",
        "birth_place": "Đồng Nai",
        "permanent_address": "193 Trương Định, Tam Hiệp, Đồng Nai",
        "cccd_number": "075200001234",
        "cccd_issue_date": "05/09/2026",
        "cccd_issue_place": "Cục Cảnh sát QLHC về TTXH",
        "role": "nhanvien",
    }
    employee.update(overrides)
    return employee


def test_contract_export_request_accepts_multiple_selected_employees():
    request = ContractExportRequest(
        contract_type="letan",
        scope="selected",
        usernames=["ktv01", "ktv02"],
    )
    assert request.contract_type == "letan"
    assert request.usernames == ["ktv01", "ktv02"]


def test_contract_profile_validation_reports_employee_and_missing_fields():
    employee = _complete_employee(employee_name="Lê Thị B", cccd_number="", permanent_address="")
    assert _missing_contract_fields(employee) == ["Địa chỉ thường trú từ CCCD", "Số CCCD"]

    with pytest.raises(HTTPException) as raised:
        _ensure_complete_contract_profiles([employee])

    assert raised.value.status_code == 422
    assert "Lê Thị B" in raised.value.detail
    assert "Địa chỉ thường trú từ CCCD" in raised.value.detail
    assert "Số CCCD" in raised.value.detail


def test_complete_ktv_contract_is_printable_pdf():
    content = _contract_pdf(_complete_employee(), DEFAULT_SETTINGS)
    assert content.startswith(b"%PDF-")
    assert len(PdfReader(BytesIO(content)).pages) >= 1


def test_role_specific_contract_defaults_and_pdfs_are_available():
    expected = {
        "ktv": (("leader", "nhanvien"), "Xoa bóp, gội đầu", "HỢP ĐỒNG LAO ĐỘNG BÁN THỜI GIAN"),
        "letan": (("letan",), "Đón tiếp và hướng dẫn khách", "HỢP ĐỒNG LAO ĐỘNG BÁN THỜI GIAN"),
        "locker": (("locker",), "bàn giao tư trang", "HỢP ĐỒNG LAO ĐỘNG BÁN THỜI GIAN"),
        "quanly": (("quanly",), "Điều hành hoạt động trong ca", "HỢP ĐỒNG LAO ĐỘNG BÁN THỜI GIAN"),
        "tapvu": (("tapvu",), "Vệ sinh phòng dịch vụ", "HỢP ĐỒNG LAO ĐỘNG"),
    }

    for contract_type, (roles, content_marker, document_title) in expected.items():
        config = CONTRACT_TYPE_CONFIGS[contract_type]
        assert config["roles"] == roles
        assert config["document_title"] == document_title
        assert content_marker in config["defaults"]["template_content"]

        employee = _complete_employee(role=roles[0])
        content = _contract_pdf(employee, config["defaults"], contract_type)
        reader = PdfReader(BytesIO(content))
        assert content.startswith(b"%PDF-")
        assert len(reader.pages) >= 1
        assert reader.metadata.title == f"{config['label']} - {employee['employee_name']}"


def test_contract_ui_names_multi_select_and_highlighted_settings():
    page = (ROOT / "web-v2/src/pages/ContractPage.jsx").read_text(encoding="utf-8")
    shell = (ROOT / "web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")
    permissions = (ROOT / "vera_web_v2_permissions.py").read_text(encoding="utf-8")

    for label in ("Hợp đồng KTV", "Hợp đồng Lễ tân", "Hợp đồng Locker", "Hợp đồng Quản lý", "Hợp đồng Tạp vụ"):
        assert label in page
    assert "contractType" in page
    assert "contract_type: contractType" in page
    assert "selectedUsernames" in page
    assert "Chọn tất cả đang hiển thị" in page
    assert "contract-highlight-field" in page
    assert "label: 'Hợp đồng'" in shell
    assert '"Hợp đồng": {' in permissions

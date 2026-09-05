from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from pypdf import PdfReader

from vera_web_v2_contracts import (
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
    request = ContractExportRequest(scope="selected", usernames=["ktv01", "ktv02"])
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


def test_contract_ui_names_multi_select_and_highlighted_settings():
    page = (ROOT / "web-v2/src/pages/ContractPage.jsx").read_text(encoding="utf-8")
    shell = (ROOT / "web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")
    permissions = (ROOT / "vera_web_v2_permissions.py").read_text(encoding="utf-8")

    assert "Hợp đồng KTV" in page
    assert "selectedUsernames" in page
    assert "Chọn tất cả đang hiển thị" in page
    assert "contract-highlight-field" in page
    assert "label: 'Hợp đồng'" in shell
    assert '"Hợp đồng": {' in permissions

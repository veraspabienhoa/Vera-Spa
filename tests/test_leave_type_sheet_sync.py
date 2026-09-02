import pytest
from fastapi import HTTPException

from vera_web_v2_leave_sync_queue import (
    _required_leave_type,
    _sheet_values_with_required_leave_type,
)


class _ApiModule:
    @staticmethod
    def _norm(value):
        return str(value or "").strip().casefold()

    @classmethod
    def _sheet_values_for_record(cls, headers, record, _source_row):
        mapping = {
            cls._norm("Tên nhân viên"): record["employee_name"],
            cls._norm("Lý do nghỉ"): record["leave_reason"],
            cls._norm("Loại nghỉ"): record["leave_type"],
        }
        return [mapping.get(cls._norm(header), "") for header in headers]


def test_user_registration_sheet_row_contains_leave_type():
    headers = ["Ngày", "Thứ ngày", "Tên nhân viên", "Lý do nghỉ", "Loại nghỉ"]
    record = {
        "employee_name": "Cẩm Vân",
        "leave_reason": "Nghỉ CÓ phép",
        "leave_type": "Có phép",
    }

    row = _sheet_values_with_required_leave_type(
        api_module=_ApiModule,
        headers=headers,
        record=record,
        source_row=2,
    )

    assert row[4] == "Có phép"


def test_user_registration_rejects_a_reason_without_leave_type():
    with pytest.raises(HTTPException) as exc_info:
        _required_leave_type({"leave_type": "  "})

    assert exc_info.value.status_code == 400
    assert "Loại nghỉ" in str(exc_info.value.detail)


def test_sheet_sync_requires_leave_type_header():
    with pytest.raises(RuntimeError, match="cột Loại nghỉ"):
        _sheet_values_with_required_leave_type(
            api_module=_ApiModule,
            headers=["Ngày", "Tên nhân viên", "Lý do nghỉ"],
            record={
                "employee_name": "Cẩm Vân",
                "leave_reason": "Nghỉ CÓ phép",
                "leave_type": "Có phép",
            },
            source_row=2,
        )

from datetime import date

import pytest

from vera_web_v2_leave_source_export import missing_leave_rows


def _norm(value):
    return str(value or "").strip().casefold()


def test_sync_appends_only_missing_leave_rows_and_excludes_violations():
    sheet_values = [
        ["Ngày", "Thứ ngày", "Tên nhân viên", "Lý do nghỉ", "Loại nghỉ"],
        ["01/09/2026", "Thứ Ba", "Cẩm Vân", "Nghỉ CÓ phép", ""],
    ]
    records = [
        {"leave_date": date(2026, 9, 1), "employee_name": "Cẩm Vân", "leave_reason": "Nghỉ CÓ phép", "leave_type": "Có phép"},
        {"leave_date": date(2026, 9, 2), "employee_name": "Cẩm Vân", "leave_reason": "Nghỉ CÓ phép", "leave_type": "Có phép"},
        {"leave_date": date(2026, 9, 2), "employee_name": "Cẩm Vân", "leave_reason": "Nghỉ CÓ phép", "leave_type": "Có phép"},
        {"leave_date": date(2026, 9, 2), "employee_name": "Cẩm Vân", "leave_reason": "Đi trễ", "leave_type": "Vi phạm"},
    ]

    rows, backfills, existing, excluded = missing_leave_rows(records, sheet_values, norm=_norm)

    assert rows == [["02/09/2026", "Thứ Tư", "Cẩm Vân", "Nghỉ CÓ phép", "Có phép"]]
    assert backfills == [(2, "Có phép")]
    assert existing == 2
    assert excluded == 1
    assert all(len(row) == 5 for row in rows)


def test_sync_preserves_an_existing_nonblank_leave_type():
    sheet_values = [
        ["Ngày", "Thứ ngày", "Tên nhân viên", "Lý do nghỉ", "Loại nghỉ"],
        ["01/09/2026", "Thứ Ba", "Cẩm Vân", "Nghỉ CÓ phép", "Đã duyệt thủ công"],
    ]
    records = [
        {
            "leave_date": date(2026, 9, 1),
            "employee_name": "Cẩm Vân",
            "leave_reason": "Nghỉ CÓ phép",
            "leave_type": "Có phép",
        },
    ]

    rows, backfills, existing, excluded = missing_leave_rows(records, sheet_values, norm=_norm)

    assert rows == []
    assert backfills == []
    assert existing == 1
    assert excluded == 0


def test_sync_rejects_a_source_record_without_leave_type():
    with pytest.raises(ValueError, match="chưa có Loại nghỉ"):
        missing_leave_rows(
            [{
                "leave_date": date(2026, 9, 2),
                "employee_name": "Cẩm Vân",
                "leave_reason": "Nghỉ CÓ phép",
                "leave_type": "",
            }],
            [["Ngày", "Thứ ngày", "Tên nhân viên", "Lý do nghỉ", "Loại nghỉ"]],
            norm=_norm,
        )

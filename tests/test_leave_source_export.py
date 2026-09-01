from datetime import date

from vera_web_v2_leave_source_export import missing_leave_rows


def _norm(value):
    return str(value or "").strip().casefold()


def test_sync_appends_only_missing_leave_rows_and_excludes_violations():
    sheet_values = [
        ["Ngày", "Thứ ngày", "Tên nhân viên", "Lý do nghỉ"],
        ["01/09/2026", "Thứ Ba", "Cẩm Vân", "Nghỉ CÓ phép"],
    ]
    records = [
        {"leave_date": date(2026, 9, 1), "employee_name": "Cẩm Vân", "leave_reason": "Nghỉ CÓ phép", "leave_type": "Có phép"},
        {"leave_date": date(2026, 9, 2), "employee_name": "Cẩm Vân", "leave_reason": "Nghỉ CÓ phép", "leave_type": "Có phép"},
        {"leave_date": date(2026, 9, 2), "employee_name": "Cẩm Vân", "leave_reason": "Nghỉ CÓ phép", "leave_type": "Có phép"},
        {"leave_date": date(2026, 9, 2), "employee_name": "Cẩm Vân", "leave_reason": "Đi trễ", "leave_type": "Vi phạm"},
    ]

    rows, existing, excluded = missing_leave_rows(records, sheet_values, norm=_norm)

    assert rows == [["02/09/2026", "Thứ Tư", "Cẩm Vân", "Nghỉ CÓ phép"]]
    assert existing == 2
    assert excluded == 1
    assert all(len(row) == 4 for row in rows)

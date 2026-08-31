from vera_web_v2_work_schedule_permissions import _sanitize_directory_payload


def test_hidden_management_accounts_are_removed_from_employee_and_account_lists():
    payload = {
        "employees": [
            {"username": "Thanh Dung", "full_name": "Thanh Dung", "role": "quanly"},
            {"username": "thutrang", "full_name": "Thu Trang", "role": "quanly"},
            {"username": "camvan", "full_name": "Cẩm Vân", "role": "nhanvien"},
        ],
        "accounts": [
            {"username": "Thu Trang", "role": "quanly"},
            {"username": "admin", "role": "admin"},
        ],
    }

    result = _sanitize_directory_payload(payload)

    assert [row["username"] for row in result["employees"]] == ["camvan"]
    assert [row["username"] for row in result["accounts"]] == ["admin"]


def test_historical_records_are_preserved():
    payload = {
        "records": [
            {"employee_name": "Thanh Dung", "leave_date": "2026-08-01"},
            {"employee_name": "Thu Trang", "leave_date": "2026-08-02"},
        ],
        "rows": [
            {"employee_name": "Thanh Dung", "amount": 100000},
        ],
    }

    result = _sanitize_directory_payload(payload)

    assert result == payload

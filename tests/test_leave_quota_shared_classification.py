from pathlib import Path

from vera_leave_registration_shared import count_unique_leave_people, quota_group


def test_leader_and_approved_are_visible_but_do_not_consume_daily_quota():
    rows = [
        {
            "employee_name": "Nhân viên thường",
            "leave_reason": "Nghỉ CÓ phép",
            "leave_type": "CÓ phép",
            "calculated_days": 1,
        },
        {
            "employee_name": "Leader A",
            "leave_reason": "Leader nghỉ phép theo chính sách",
            "leave_type": "Leader",
            "calculated_days": 1,
        },
        {
            "employee_name": "Nhân viên B",
            "leave_reason": "Nghỉ bệnh có giấy khám hoặc được quản lý duyệt",
            "leave_type": "Được duyệt",
            "calculated_days": 1,
        },
    ]

    assert quota_group("Leader nghỉ phép theo chính sách", "Leader") == ""
    assert quota_group("Nghỉ bệnh có giấy khám hoặc được quản lý duyệt", "Được duyệt") == ""
    assert quota_group("Nghỉ phép năm", "Phép năm") == "co_phep"

    stats = count_unique_leave_people(rows)
    assert stats == {
        "total_leave": 3,
        "paid": 1,
        "generated": 0,
        "unpaid": 0,
    }


def test_registration_and_stats_share_the_same_quota_classifier_and_config():
    api = Path("vera_web_v2_api.py").read_text(encoding="utf-8")
    stats = Path("vera_web_v2_leave_day_stats.py").read_text(encoding="utf-8")
    shared = Path("vera_leave_registration_shared.py").read_text(encoding="utf-8")

    assert "quota_group(item[\"name\"], item.get(\"leave_type\", \"\"))" in api
    assert "count_unique_leave_people(day_rows)" in api
    assert '_daily_quota_config(conn)["days"][body.leave_date.weekday()]' in api
    assert "limit = 4 if group == \"co_phep\" else 1" not in api

    assert "count_unique_leave_people(bucket[\"rows\"])" in stats
    assert "generated_limit > 0 and people[\"generated\"] >= generated_limit" in stats

    assert 'if type_key in {"leader", "duoc duyet"}:' in shared
    assert "policy_group = quota_group(" in shared

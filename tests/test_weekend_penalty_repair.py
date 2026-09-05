from decimal import Decimal

from vera_weekend_penalty_repair import (
    _policy_map,
    _repair_target,
    _strip_progressive_prefix,
)


def test_repairs_exact_weekend_surcharge_for_all_three_groups():
    official = _policy_map({
        "rows": [
            {"Lý do nghỉ": "Nghỉ CUỐI TUẦN KHÔNG phép", "Phạt vi phạm": 1_000_000},
            {"Lý do nghỉ": "Đi trễ CUỐI TUẦN KHÔNG phép", "Phạt vi phạm": 500_000},
            {"Lý do nghỉ": "Về sớm CUỐI TUẦN KHÔNG phép", "Phạt vi phạm": 500_000},
        ],
    })

    cases = (
        ("Nghỉ CUỐI TUẦN KHÔNG phép", "Người Thứ 3 nghỉ không phép", 1_100_000, 1_000_000),
        ("Đi trễ CUỐI TUẦN KHÔNG phép", "Người Thứ 4 đi trễ không phép", 700_000, 500_000),
        ("Về sớm CUỐI TUẦN KHÔNG phép", "Người Thứ 3 về sớm không phép", 600_000, 500_000),
    )
    for reason, detail, current, expected in cases:
        assert _repair_target({
            "leave_reason": reason,
            "detail": detail,
            "penalty": current,
        }, official) == (Decimal(expected), "")


def test_does_not_touch_rows_without_exact_evidence():
    official = _policy_map({
        "rows": [{
            "Lý do nghỉ": "Về sớm CUỐI TUẦN KHÔNG phép",
            "Phạt vi phạm": 500_000,
        }],
    })
    assert _repair_target({
        "leave_reason": "Về sớm CUỐI TUẦN KHÔNG phép",
        "detail": "Người Thứ 3 về sớm không phép",
        "penalty": 650_000,
    }, official) is None
    assert _repair_target({
        "leave_reason": "Về sớm CUỐI TUẦN KHÔNG phép",
        "detail": "Ghi chú thủ công",
        "penalty": 600_000,
    }, official) is None


def test_prefix_removal_preserves_operator_note():
    assert _strip_progressive_prefix(
        "Người Thứ 3 về sớm không phép | Khách đồng ý"
    ) == "Khách đồng ý"

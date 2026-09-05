from datetime import date
from pathlib import Path

import pandas as pd

from vera_leave_registration_live_shared import progressive_ordinal_and_bonus
from vera_progressive_penalty import (
    CONFIG_SHEET_KEY,
    SETTING_CATEGORY,
    SETTING_KEY,
    as_bool,
    bonus,
    canonical_reason,
    load_weekend_unpaid_enabled,
    progressive_key,
)


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_weekend_progressive_groups_do_not_add_nth_bonus_by_default():
    saturday = date(2026, 9, 5)
    sunday = date(2026, 9, 6)

    for work_date in (saturday, sunday):
        for reason in (
            "Nghỉ không phép",
            "Nghỉ CUỐI TUẦN KHÔNG phép",
            "Đi trễ không phép",
            "Đi trễ CUỐI TUẦN KHÔNG phép",
            "Về sớm không phép",
            "Về sớm CUỐI TUẦN KHÔNG phép",
            "Ra sớm không phép",
        ):
            assert canonical_reason(reason) is not None
            assert bonus(3, work_date, reason) == 0
            assert bonus(5, work_date, reason) == 0


def test_admin_can_enable_weekend_unpaid_nth_bonus_again():
    saturday = date(2026, 9, 5)

    for reason in ("Nghỉ không phép", "Đi trễ không phép", "Về sớm không phép"):
        assert bonus(1, saturday, reason, weekend_unpaid_enabled=True) == 0
        assert bonus(2, saturday, reason, weekend_unpaid_enabled=True) == 0
        assert bonus(3, saturday, reason, weekend_unpaid_enabled=True) == 100_000
        assert bonus(4, saturday, reason, weekend_unpaid_enabled=True) == 200_000
        assert bonus(5, saturday, reason, weekend_unpaid_enabled=True) == 300_000


def test_weekday_progression_and_non_progressive_reasons_are_unchanged():
    friday = date(2026, 9, 4)
    saturday = date(2026, 9, 5)

    for reason in ("Nghỉ không phép", "Đi trễ không phép", "Về sớm không phép"):
        assert bonus(3, friday, reason) == 100_000
    assert bonus(4, friday, "Nghỉ CUỐI TUẦN KHÔNG phép") == 200_000
    assert bonus(7, saturday, "Nghỉ có phép") == 0


def test_progressive_groups_remain_independent_and_normalized():
    assert progressive_key("Nghỉ CUỐI TUẦN KHÔNG phép") == "nghi_khong_phep"
    assert progressive_key("Đi trễ KHÔNG phép") == "di_tre_khong_phep"
    assert progressive_key("Ra sớm không phép") == "ve_som_khong_phep"
    assert progressive_key("Ra ngoài vào muộn") == ""


def test_shared_preview_and_save_calculation_use_the_same_weekend_switch():
    for reason in ("Nghỉ không phép", "Đi trễ không phép", "Về sớm không phép"):
        existing = pd.DataFrame([
            {"Ngày": date(2026, 9, 5), "Lý do nghỉ": reason},
            {"Ngày": date(2026, 9, 5), "Lý do nghỉ": reason},
        ])

        assert progressive_ordinal_and_bonus(
            existing,
            date(2026, 9, 5),
            reason,
        ) == (None, 0)
        assert progressive_ordinal_and_bonus(
            existing,
            date(2026, 9, 5),
            reason,
            weekend_unpaid_enabled=True,
        ) == (3, 100_000)


def test_shared_weekday_progression_stays_enabled_by_default():
    existing = pd.DataFrame([
        {"Ngày": date(2026, 9, 4), "Lý do nghỉ": "Nghỉ không phép"},
        {"Ngày": date(2026, 9, 4), "Lý do nghỉ": "Nghỉ CUỐI TUẦN KHÔNG phép"},
    ])

    assert progressive_ordinal_and_bonus(
        existing,
        date(2026, 9, 4),
        "Nghỉ không phép",
    ) == (3, 100_000)


def test_switch_contract_and_boolean_compatibility():
    assert SETTING_CATEGORY == "leave_rules"
    assert SETTING_KEY == "weekend_unpaid_nth_penalty"
    assert CONFIG_SHEET_KEY == "weekend_unpaid_nth_penalty_enabled"
    assert as_bool({"enabled": True}) is True
    assert as_bool("BẬT") is True
    assert as_bool("TẮT") is False
    assert as_bool("invalid") is False


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeConnection:
    def __init__(self, value=None, *, fail=False):
        self.value = value
        self.fail = fail
        self.params = None

    def execute(self, _statement, params):
        if self.fail:
            raise RuntimeError("database unavailable")
        self.params = params
        return _FakeResult(self.value)


def test_missing_or_invalid_database_switch_defaults_to_off():
    missing = _FakeConnection(None)
    invalid = _FakeConnection('{"enabled": "unknown"}')
    enabled = _FakeConnection({"enabled": True})

    assert load_weekend_unpaid_enabled(missing) is False
    assert load_weekend_unpaid_enabled(invalid) is False
    assert load_weekend_unpaid_enabled(_FakeConnection(fail=True)) is False
    assert load_weekend_unpaid_enabled(enabled) is True
    assert enabled.params == {
        "category": SETTING_CATEGORY,
        "setting_key": SETTING_KEY,
    }


def test_every_active_writer_uses_the_shared_weekend_policy():
    manual_api = _source("vera_web_v2_api_shared.py")
    base_api = _source("vera_web_v2_api.py")
    auto_pg = _source("vera_auto_check.py")
    auto_google = _source("timesoft_sync_job.py")
    revenue_list = _source("vera_web_v2_revenue_leave_list.py")

    assert "load_weekend_unpaid_enabled(conn)" in manual_api
    assert "progressive_bonus_amount" in manual_api
    assert "load_weekend_unpaid_enabled(conn)" in base_api
    assert "progressive_penalty_bonus" in base_api
    assert "progressive_penalty.load_weekend_unpaid_enabled(conn)" in auto_pg
    assert "progressive_penalty.bonus(" in auto_pg
    assert "progressive_penalty.CONFIG_SHEET_KEY" in auto_google
    assert "progressive_penalty.bonus(" in auto_google
    assert "load_weekend_unpaid_enabled(conn)" in revenue_list
    assert "progressive_penalty_applies(" in revenue_list


def test_rules_page_exposes_an_admin_weekend_toggle():
    rules = _source("vera_web_v2_rules.py")
    page = _source("web-v2/src/pages/RulesPage.jsx")
    client = _source("web-v2/src/lib/api.js")

    assert '@app.put("/v2/rules/weekend-unpaid-nth-penalty")' in rules
    assert "expected_revision" in rules
    assert "Chỉ tài khoản admin được bật hoặc tắt Người Thứ N" in rules
    assert "WEEKEND_UNPAID_NTH_CONFIG_SHEET_KEY" in rules
    assert "NGƯỜI THỨ N – VI PHẠM CUỐI TUẦN" in page
    assert "Tắt Người Thứ N cuối tuần" in page
    assert "Kích hoạt Người Thứ N cuối tuần" in page
    assert "saveWeekendUnpaidNthPenalty" in client

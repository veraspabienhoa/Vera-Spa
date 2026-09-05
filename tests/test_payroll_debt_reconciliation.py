from __future__ import annotations

from datetime import date
import unicodedata

import vera_web_v2_payroll as payroll
import vera_web_v2_payroll_debt_sync as debt_sync
import vera_web_v2_payroll_enhancements as enhancements


def _norm(value) -> str:
    raw = unicodedata.normalize("NFD", str(value or ""))
    return " ".join(
        "".join(character for character in raw if unicodedata.category(character) != "Mn")
        .replace("đ", "d").replace("Đ", "D").casefold().split()
    )


def test_manual_prior_debt_replaces_settlement_and_preserves_remaining(monkeypatch):
    custom = [{
        "id": "custom-1",
        "employee_name": "Linh Đan",
        "amount": 1_000_000,
        "due_from": "2026-08-16",
        "status": "Chưa hoàn thành",
    }]
    legacy = [{
        "__debt_key": "legacy-negative-1",
        "Tên nhân viên": "Linh Đan",
        "Số tiền": 500_000,
        "Loại": "Âm thực nhận",
        "Bắt đầu trừ từ": "16/08/2026",
        "Trạng thái": "Chưa hoàn thành",
    }]
    saved_custom = []
    legacy_calls = []

    monkeypatch.setattr(payroll, "_obligations", lambda _conn: custom)
    monkeypatch.setattr(
        payroll,
        "_put_setting",
        lambda _conn, key, value, _actor: saved_custom.append((key, value)),
    )

    def replace(_conn, batch, allocations, _actor):
        legacy_calls.append((batch, dict(allocations)))
        return [dict(item) for item in legacy]

    monkeypatch.setattr(debt_sync, "replace_batch_settlements", replace)
    body = payroll.PayrollSave(
        start=date(2026, 8, 16),
        end=date(2026, 8, 31),
        rows=[{"Tên Hệ thống": "Linh Đan"}],
    )

    first = enhancements._reconcile_payroll_debts(
        object(),
        body,
        [{"Tên Hệ thống": "Linh Đan", "Vi phạm kỳ trước": 700_000, "Số tiền thực nhận": 1_000_000}],
        "admin",
        _norm,
    )

    label = "Kỳ 2 - Tháng 8/2026"
    assert first == {
        "requested": 700_000,
        "applied": 700_000,
        "unmatched": 0,
        "custom_applied": 200_000,
        "legacy_applied": 500_000,
        "negative_created": 0,
    }
    assert custom[0]["principal_amount"] == 1_000_000
    assert custom[0]["amount"] == 800_000
    assert custom[0]["settlements"] == {label: 200_000}
    assert legacy_calls[-1] == (label, {"legacy-negative-1": 500_000})

    second = enhancements._reconcile_payroll_debts(
        object(),
        body,
        [{"Tên Hệ thống": "Linh Đan", "Vi phạm kỳ trước": 300_000, "Số tiền thực nhận": 1_400_000}],
        "admin",
        _norm,
    )

    assert second["applied"] == 300_000
    assert second["custom_applied"] == 0
    assert custom[0]["amount"] == 1_000_000
    assert custom[0]["settlements"] == {}
    assert legacy_calls[-1] == (label, {"legacy-negative-1": 300_000})
    assert saved_custom[-1][0] == "violation_obligations"


def test_negative_actual_payment_creates_next_period_obligation(monkeypatch):
    custom = []
    monkeypatch.setattr(payroll, "_obligations", lambda _conn: custom)
    monkeypatch.setattr(payroll, "_put_setting", lambda *_args: None)
    monkeypatch.setattr(debt_sync, "replace_batch_settlements", lambda *_args: [])
    body = payroll.PayrollSave(
        start=date(2026, 8, 16),
        end=date(2026, 8, 31),
        rows=[{"Tên Hệ thống": "Anh Thư"}],
    )

    result = enhancements._reconcile_payroll_debts(
        object(),
        body,
        [{"Tên Hệ thống": "Anh Thư", "Vi phạm kỳ trước": 0, "Số tiền thực nhận": -450_000}],
        "admin",
        _norm,
    )

    assert result["negative_created"] == 1
    assert custom[0]["type"] == "Âm thực nhận"
    assert custom[0]["amount"] == 450_000
    assert custom[0]["principal_amount"] == 450_000
    assert custom[0]["due_from"] == "2026-09-01"
    assert custom[0]["status"] == "Chưa hoàn thành"


def test_legacy_settlement_is_not_subtracted_twice(monkeypatch):
    monkeypatch.setattr(debt_sync, "_hidden_keys", lambda _conn: set())
    monkeypatch.setattr(debt_sync, "_manual_rows", lambda _conn: [])
    monkeypatch.setattr(
        debt_sync,
        "_settlement_ledger",
        lambda _conn: {"stable-key": {"Kỳ 2 - Tháng 8/2026": 400_000}},
    )
    original = [{
        "__debt_key": "stable-key",
        "Tên nhân viên": "Linh Đan",
        "Số tiền": 1_000_000,
        "Trạng thái": "Chưa hoàn thành",
    }]

    first = debt_sync._apply_admin_adjustments(object(), original)
    second = debt_sync._apply_admin_adjustments(object(), first)

    assert first[0]["Số tiền"] == 600_000
    assert second[0]["Số tiền"] == 600_000
    assert second[0]["__original_amount"] == 1_000_000


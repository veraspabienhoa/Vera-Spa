"""Regression fixtures for contribution, refund and carried-debt calculation."""
from datetime import date
import asyncio
import unicodedata
from types import SimpleNamespace

from fastapi import FastAPI
import pandas as pd
import pytest

import vera_web_v2_payroll as payroll
import vera_web_v2_payroll_personal as personal
from vera_web_v2_accumulation_permission import _apply_adjustments

START, END = date(2026, 9, 16), date(2026, 9, 30)


def norm(value):
    raw = unicodedata.normalize('NFD', str(value or '').casefold())
    return ''.join(c for c in raw if not unicodedata.combining(c)).replace('đ', 'd')


def history_row(start, end, contribution=0, refund=0):
    return {'Tên Hệ thống': 'A', 'Mã bản lưu': f'{start}|{end}', 'Từ ngày': start,
            'Đến ngày': end, 'Tích lũy': contribution, 'Hoàn trả tiền tích lũy': refund}


def test_calculation_and_tracking_share_adjusted_balance(monkeypatch):
    source = [{'Tên nhân viên': 'A', 'Đã tích lũy': 4_000_000}]
    adjustments = [{'employee_name': 'A', 'delta': 1_000_000}]
    employee = {'username': 'A'}
    balance = personal._accumulation_balance(employee, [], source, adjustments, norm)
    tracking = _apply_adjustments({'employees': [{'employee_name': 'A', **personal._accumulation_balance(employee, [], source, [], norm)}]}, adjustments, norm)['employees'][0]
    assert balance['paid_total'] == tracking['paid_total'] == 5_000_000
    assert balance['remaining'] == tracking['remaining'] == 0
    monkeypatch.setattr(payroll, '_employee_accumulation_balances', lambda *a: {norm('A'): balance})
    assert payroll._tichluy_map(None, [employee], START, END, norm) == {norm('A'): 0}


def test_history_and_source_are_merged_without_duplicate_contributions():
    source = [{'Tên nhân viên': 'A', 'Đã tích lũy': 4_500_000,
               'Chi tiết các kỳ': {'2026-09-01|2026-09-15': 500_000}}]
    records = [history_row('2026-09-01', '2026-09-15', 500_000),
               history_row('2026-09-16', '2026-09-30', 500_000)]
    balance = personal._accumulation_balance({'username': 'A'}, records, source, [], norm, (START, END))
    assert balance['paid_total'] == 4_500_000
    assert balance['remaining'] == 500_000
    source[0]['Đã tích lũy'] = 5_000_000
    source[0]['Chi tiết các kỳ']['2026-09-16|2026-09-30'] = 500_000
    again = personal._accumulation_balance({'username': 'A'}, records, source, [], norm, (START, END))
    assert again['paid_total'] == balance['paid_total']


def test_refund_replacement_and_next_period_do_not_pay_twice(monkeypatch):
    source = [{'Tên nhân viên': 'A', 'Đã tích lũy': 5_000_000}]
    records = [history_row('2026-09-16', '2026-09-30', refund=5_000_000)]
    employee = {'username': 'A', 'employment_status': 'Đã nghỉ việc'}
    monkeypatch.setattr(payroll, '_accumulation_refunds', lambda c: [])
    monkeypatch.setattr(payroll, '_employee_accumulation_balances', lambda c, employees, n, period: {norm('A'): personal._accumulation_balance(employee, records, source, [], n, period)})
    assert payroll._accumulation_refund_map(None, START, END, norm, [employee]) == {norm('A'): 5_000_000}
    assert payroll._accumulation_refund_map(None, date(2026, 10, 1), date(2026, 10, 15), norm, [employee]) == {norm('A'): 0}
    balance = personal._accumulation_balance(employee, records, source, [], norm)
    assert balance['refunded_total'] == 5_000_000
    assert balance['refundable_total'] == 0
    records.append(history_row('2026-08-16', '2026-08-31', refund=100_000))
    assert personal._accumulation_balance(employee, records, source, [], norm)['refundable_total'] == 0


def test_prior_debt_includes_due_within_period_and_restores_own_settlement(monkeypatch):
    custom = [{'employee_name': 'A', 'amount': 0, 'status': 'Đã hoàn thành',
               'source_status': 'Chưa hoàn thành', 'due_from': '2026-09-20',
               'settlements': {payroll._period_label(START, END): 1_480_000}},
              {'employee_name': 'A', 'amount': 100, 'due_from': '2026-10-01'}]
    monkeypatch.setattr(payroll, '_obligations', lambda c: custom)
    conn = SimpleNamespace(execute=lambda *a, **kw: SimpleNamespace(scalar_one_or_none=lambda: []))
    assert payroll._obligation_map(conn, START, norm, END) == {norm('A'): 1_480_100}
    assert payroll._obligation_map(conn, date(2026, 10, 1), norm, date(2026, 10, 15)) == {norm('A'): 100}


@pytest.mark.parametrize('salary,debt,expected_debt,expected_net', [
    (6_550_000, 1_480_000, 1_480_000, 4_840_000),
    (1_000_000, 1_480_000, 770_000, 0),
    (100_000, 1_480_000, 0, -130_000),
])
def test_canonical_calculation_only_deducts_available_net(monkeypatch, salary, debt, expected_debt, expected_net):
    employee = {'username': 'A', 'full_name': 'Synthetic employee', 'role': 'nhanvien',
                'email': '', 'bank_account': '', 'bank_name': '', 'employment_status': 'Đang làm việc'}
    class Result:
        def __init__(self, rows): self.rows = rows
        def mappings(self): return self
        def all(self): return self.rows
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, statement, *args):
            return Result([employee] if 'FROM employees' in str(statement) else [])
    monkeypatch.setattr(payroll, '_setting', lambda conn, key, default: default)
    monkeypatch.setattr(payroll, '_read_source', lambda p: None)
    monkeypatch.setattr(payroll, '_config', lambda c: payroll.DEFAULT_CONFIG)
    monkeypatch.setattr(payroll, '_tichluy_map', lambda *a: {norm('A'): 0})
    monkeypatch.setattr(payroll, '_obligation_map', lambda *a: {norm('A'): debt})
    monkeypatch.setattr(payroll, '_accumulation_refund_map', lambda *a: {})
    monkeypatch.setattr(payroll, '_tip_rows', lambda *a: (pd.DataFrame([{'key': norm('A'), 'employee': 'A', 'amount': salary}]), {}))
    import vera_attendance_participation
    monkeypatch.setattr(vera_attendance_participation, 'eligible', lambda rows, *a, **kw: rows)
    app = FastAPI()
    payroll.install_payroll_routes(app, engine_instance=lambda: SimpleNamespace(connect=Connection),
        current_identity=lambda: None, require_feature=lambda *a: None, norm=norm,
        identity_type=SimpleNamespace, google_client=lambda: None)
    route = next(r for r in app.routes if getattr(r, 'path', '') == '/v2/payroll/calculate')
    result = asyncio.run(route.endpoint(month='2026-09', period_no=2, payload=b'', ident=SimpleNamespace()))
    row = result['rows'][0]
    assert row['Vi phạm kỳ trước'] == expected_debt
    assert row['Số tiền thực nhận'] == expected_net


def test_prior_debt_is_capped_after_employee_specific_deductions():
    from vera_web_v2_payroll_v38 import _apply_overrides_to_calculation
    row = payroll._net({'Tên Hệ thống': 'A', 'Tiền Lương': 2_000_000,
                        'Vi phạm kỳ trước': 1_480_000, '__available_prior_debt': 1_480_000})
    output = _apply_overrides_to_calculation({'rows': [row]}, {norm('A'): {'living': 1_000_000, 'locker': 0}}, norm)
    assert output['rows'][0]['Vi phạm kỳ trước'] == 1_000_000
    assert output['rows'][0]['Số tiền thực nhận'] == 0
    output = _apply_overrides_to_calculation({'rows': [row]}, {norm('A'): {'living': 0, 'locker': 0}}, norm)
    assert output['rows'][0]['Vi phạm kỳ trước'] == 1_480_000
    assert output['rows'][0]['Số tiền thực nhận'] == 520_000


def test_missing_accumulation_source_does_not_enroll_employee_implicitly(monkeypatch):
    employee = {'username': 'A'}
    balance = personal._accumulation_balance(employee, [], [], [], norm)
    monkeypatch.setattr(payroll, '_employee_accumulation_balances', lambda *a: {norm('A'): balance})
    assert payroll._tichluy_map(None, [employee], START, END, norm)[norm('A')] == 0
    balance = personal._accumulation_balance(employee, [], [{'Tên nhân viên': 'A', 'Ngày bắt đầu làm': '2026-09-25'}], [], norm)
    assert payroll._tichluy_map(None, [employee], START, END, norm)[norm('A')] == 0
    balance = personal._accumulation_balance(employee, [], [{'Tên nhân viên': 'A'}], [], norm)
    assert payroll._tichluy_map(None, [employee], START, END, norm)[norm('A')] == 500_000


def test_completed_snapshot_with_current_period_detail_does_not_deduct(monkeypatch):
    source = [{'Tên nhân viên': 'A', 'Đã tích lũy': 5_000_000,
               'Chi tiết các kỳ': {'2026-09-16|2026-09-30': 500_000}}]
    monkeypatch.setattr(payroll, '_employee_accumulation_balances',
        lambda c, employees, n, exclude=None: {norm('A'): personal._accumulation_balance(
            {'username': 'A'}, [], source, [], n, exclude)})
    assert payroll._tichluy_map(None, [{'username': 'A'}], START, END, norm) == {norm('A'): 0}


def test_future_due_debt_is_collectible_but_current_deferred_penalty_stays_deferred(monkeypatch):
    custom = [{'employee_name': 'A', 'amount': 1_480_000, 'due_from': '2026-10-01',
               'period_start': '2026-09-01', 'period_end': '2026-09-15'},
              {'employee_name': 'A', 'amount': 1_400_000, 'due_from': '2026-10-01',
               'period_start': START.isoformat(), 'period_end': END.isoformat()}]
    monkeypatch.setattr(payroll, '_obligations', lambda c: custom)
    conn = SimpleNamespace(execute=lambda *a, **kw: SimpleNamespace(scalar_one_or_none=lambda: []))
    assert payroll._obligation_map(conn, START, norm, END) == {norm('A'): 1_480_000}


def test_completion_settles_future_due_existing_debt_once(monkeypatch):
    import vera_web_v2_payroll_enhancements as enhancements
    import vera_web_v2_payroll_debt_sync as debt_sync
    custom = [{'employee_name': 'A', 'amount': 1_480_000, 'due_from': '2026-10-01',
               'period_start': '2026-09-01', 'period_end': '2026-09-15', 'status': 'Chưa hoàn thành'}]
    monkeypatch.setattr(payroll, '_obligations', lambda c: custom)
    monkeypatch.setattr(payroll, '_put_setting', lambda *a: None)
    monkeypatch.setattr(debt_sync, 'replace_batch_settlements', lambda *a: [])
    body = payroll.PayrollSave(start=START, end=END, rows=[{'Tên Hệ thống': 'A'}])
    rows = [{'Tên Hệ thống': 'A', 'Vi phạm kỳ trước': 1_480_000, 'Số tiền thực nhận': 4_840_000}]
    for _ in range(2):
        result = enhancements._reconcile_payroll_debts(None, body, rows, 'admin', norm)
        assert result['applied'] == 1_480_000
    assert custom[0]['amount'] == 0
    assert custom[0]['settlements'] == {payroll._period_label(START, END): 1_480_000}


def test_unsaved_draft_honors_completed_source_but_official_replacement_keeps_last_payment(monkeypatch):
    source = [{'Tên nhân viên': 'A', 'Đã tích lũy': 5_000_000,
               'Chi tiết các kỳ': {'2026-09-16|2026-09-30': 500_000}}]
    records = []
    monkeypatch.setattr(personal, '_dataset', lambda conn, key: source if key == 'tichluy' else records)
    monkeypatch.setattr(payroll, '_setting', lambda *args: [])
    employee = {'username': 'A'}
    assert payroll._employee_accumulation_balances(None, [employee], norm, (START, END), saved_only=True)[norm('A')]['remaining'] == 0
    records.append(history_row(START, END, contribution=500_000))
    assert payroll._employee_accumulation_balances(None, [employee], norm, (START, END), saved_only=True)[norm('A')]['remaining'] == 500_000

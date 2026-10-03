"""Completion commits payroll, negative-net debt and draft cleanup together."""
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
import pytest
import vera_web_v2_payroll as payroll
import vera_web_v2_payroll_enhancements as enhancements
import vera_web_v2_payroll_debt_sync as debt_sync


def test_completion_cleans_only_its_draft_and_rolls_back_on_failure(monkeypatch):
    start, end = date(2026, 9, 16), date(2026, 9, 30)
    key = payroll._draft_key(start, end)
    other = payroll._draft_key(date(2026, 10, 1), date(2026, 10, 15))
    state = {'drafts': {key: 'saved', other: 'other'}, 'debts': [], 'history': []}
    events = []
    fail_commit = False

    class Transaction:
        is_active = True
        def __init__(self):
            self.before = deepcopy(state)
        def commit(self):
            if fail_commit:
                raise RuntimeError('commit failed')
            events.append('commit')
            self.is_active = False
        def rollback(self):
            state.clear(); state.update(self.before)
            events.append('rollback')
            self.is_active = False

    class Connection:
        def begin(self): return Transaction()
        def close(self): events.append('close')
        def execute(self, statement, params=None):
            sql = str(statement)
            if sql.startswith('DELETE FROM vera_app_setting'):
                events.append('delete draft')
                state['drafts'].pop(params['key'], None)
            elif 'INSERT INTO payroll_history_rows' in sql:
                state['history'].append(params['payload'])
                events.append('save payroll')

    connection = Connection()
    monkeypatch.setattr(payroll, '_clean_draft_rows', lambda *a, **kw: [payroll._net({
        'Tên Hệ thống': 'A', 'Tiền Lương': 100_000, 'Tiền phạt trong tháng': 550_000})])
    monkeypatch.setattr(payroll, '_payload', lambda conn: ([], '', None))
    monkeypatch.setattr(payroll, '_obligations', lambda conn: deepcopy(state['debts']))
    monkeypatch.setattr(debt_sync, 'replace_batch_settlements', lambda *a: [])
    monkeypatch.setattr(payroll, '_put_setting', lambda conn, setting, value, actor: state.update(debts=deepcopy(value)))
    app = FastAPI()
    payroll.install_payroll_routes(app, engine_instance=lambda: SimpleNamespace(connect=lambda: connection),
        current_identity=lambda: None, require_feature=lambda *a: None,
        norm=lambda value: str(value or '').casefold(), identity_type=SimpleNamespace,
        google_client=lambda: None)
    app.state.payroll_before_save_hook = lambda conn, body, prepared_rows, actor, norm, **kw: {
        'debt_reconciliation': enhancements._reconcile_payroll_debts(conn, body, prepared_rows, actor, norm)}
    endpoint = next(r.endpoint for r in app.routes if getattr(r, 'path', '') == '/v2/payroll/save')
    body = payroll.PayrollSave(start=start, end=end, rows=[{'Tên Hệ thống': 'A'}])
    before = deepcopy(state)
    fail_commit = True
    with pytest.raises(RuntimeError, match='commit failed'):
        endpoint(body, SimpleNamespace(employee_username='admin'))
    assert state == before
    assert events[-2:] == ['rollback', 'close']

    fail_commit = False
    result = endpoint(body, SimpleNamespace(employee_username='admin'))
    assert key not in state['drafts']
    assert other in state['drafts']
    assert state['debts'][0]['amount'] == 450_000
    assert state['debts'][0]['type'] == 'Âm thực nhận'
    assert result['debt_reconciliation']['negative_created'] == 1
    assert events.index('save payroll') < events.index('delete draft')
    assert events[-2:] == ['commit', 'close']
    endpoint(body, SimpleNamespace(employee_username='admin'))
    assert len(state['debts']) == 1

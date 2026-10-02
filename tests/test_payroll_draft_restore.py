"""Restore consumes only the selected saved draft in the caller transaction."""
from datetime import date
from types import SimpleNamespace
from contextlib import contextmanager
from copy import deepcopy

from fastapi import FastAPI, HTTPException
import pytest
import vera_web_v2_payroll as payroll


def setup_restore(monkeypatch, saved, replacement=None, denied=False):
    events = []
    class Connection:
        def execute(self, statement, params):
            sql = str(statement)
            if 'advisory' in sql:
                events.append(('lock', params['label']))
                if replacement:
                    saved.update(deepcopy(replacement))
            elif sql.startswith('DELETE'):
                events.append(('delete', params['key']))
                del saved[params['key']]
    connection = Connection()
    @contextmanager
    def begin():
        before = deepcopy(saved)
        events.append(('begin', None))
        try:
            yield connection
            events.append(('commit', None))
        except Exception:
            saved.clear(); saved.update(before)
            events.append(('rollback', None))
            raise
    def get(conn, start, end, norm):
        assert conn is connection
        events.append(('read', payroll._draft_key(start, end)))
        return deepcopy(saved.get(payroll._draft_key(start, end)))
    def latest(conn, norm):
        assert conn is connection
        return deepcopy(next(iter(saved.values()), None))
    def permission(conn, ident, feature):
        events.append(('permission', feature))
        if denied and feature == 'payroll_save':
            raise HTTPException(403, 'denied')
    monkeypatch.setattr(payroll, '_saved_draft', get)
    monkeypatch.setattr(payroll, '_latest_saved_draft', latest)
    app = FastAPI()
    payroll.install_payroll_routes(app, engine_instance=lambda: SimpleNamespace(begin=begin),
        current_identity=lambda: None, require_feature=permission, norm=str,
        identity_type=SimpleNamespace, google_client=lambda: None)
    route = next(r for r in app.routes if getattr(r, 'path', '') == '/v2/payroll/draft/restore')
    return route.endpoint, events


def draft(start='2026-08-01', end='2026-08-15', salary=100):
    return {'start': start, 'end': end, 'rows': [{'Tên Hệ thống': 'A', 'Tiền Lương': salary}],
            'saved_at': '2026-10-02T16:00:00Z', 'saved_by': 'admin'}


def test_restore_fallback_returns_rows_and_deletes_only_that_period(monkeypatch):
    key = payroll._draft_key(date(2026,8,1), date(2026,8,15))
    other_key = payroll._draft_key(date(2026,7,1), date(2026,7,15))
    saved = {key: draft(), other_key: draft('2026-07-01','2026-07-15')}
    newer = {key: draft(salary=800)}
    endpoint, events = setup_restore(monkeypatch, saved, replacement=newer)
    result = endpoint(month='2026-10',period_no=1,ident=SimpleNamespace())
    assert result['selected_month'] == '2026-08'
    assert result['selected_period_no'] == 1
    assert result['draft']['rows'][0]['Tiền Lương'] == 800
    assert result['draft']['saved_at'] == ''
    assert result['has_saved_draft'] is True
    assert key not in saved
    assert other_key in saved
    assert events.index(('lock','Kỳ 1 - Tháng 8/2026')) < events.index(('delete', key))
    assert events[-1][0] == 'commit'


def test_restore_no_draft_does_not_delete(monkeypatch):
    endpoint, events = setup_restore(monkeypatch, {})
    result = endpoint(month='2026-10',period_no=1,ident=SimpleNamespace())
    assert result == {'draft': None, 'has_saved_draft': False}
    assert not any(action == 'delete' for action, _ in events)


def test_restore_requires_save_permission_and_keeps_saved_data_on_denial(monkeypatch):
    key = payroll._draft_key(date(2026,8,1), date(2026,8,15))
    saved = {key: draft()}
    endpoint, events = setup_restore(monkeypatch, saved, denied=True)
    with pytest.raises(HTTPException) as error:
        endpoint(month='2026-08',period_no=1,ident=SimpleNamespace())
    assert error.value.status_code == 403
    assert saved[key]['rows'][0]['Tiền Lương'] == 100
    assert events[-1][0] == 'rollback'
    assert not any(action == 'delete' for action, _ in events)

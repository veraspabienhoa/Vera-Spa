"""Revenue mutations must not transfer unrelated financial history."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException
from sqlalchemy import text

import vera_revenue_store as store
import vera_web_v2_revenue_leave_list as routes
from test_notification_schema_locking import database


class LockedRowConnection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, sql, params=None):
        sql = str(sql)
        self.calls.append((sql, params))
        if sql.lstrip().startswith('SELECT'):
            assert 'WHERE id=:id AND is_deleted=false FOR UPDATE' in sql
            return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: self.row))
        return SimpleNamespace()


def locked_row():
    return dict(id=7, transaction_type='Chi', amount=Decimal('1234.56'),
                note='Synthetic expense', entered_at=datetime(2026, 10, 7, 18, tzinfo=timezone.utc),
                edit_revision=3)


def test_delete_returns_the_locked_audit_version_without_history_read(monkeypatch):
    monkeypatch.setattr(store, 'ensure_schema', lambda conn: None)
    conn = LockedRowConnection(locked_row())
    result = store.soft_delete_entry(conn, entry_id=7, actor='synthetic',
                                     required_entered_date=date(2026, 10, 8))
    assert result == dict(type='Chi', amount=1234.56, note='Synthetic expense')
    assert len(conn.calls) == 3
    audit = json.loads(conn.calls[-1][1]['before'])
    assert audit['note'] == result['note'] and float(audit['amount']) == result['amount']
    assert audit['edit_revision'] == 3


@pytest.mark.parametrize('row,day,error', [
    (None, None, KeyError),
    (locked_row(), date(2026, 10, 7), PermissionError),
])
def test_delete_rejections_do_not_write_audit_or_finances(monkeypatch, row, day, error):
    monkeypatch.setattr(store, 'ensure_schema', lambda conn: None)
    conn = LockedRowConnection(row)
    with pytest.raises(error):
        store.soft_delete_entry(conn, entry_id=7, actor='synthetic', required_entered_date=day)
    assert len(conn.calls) == 1


class Engine:
    def __init__(self):
        self.committed = False

    @contextmanager
    def begin(self):
        yield self
        self.committed = True


def endpoints(monkeypatch, *, permission_error=False):
    engine = Engine()
    app = FastAPI()
    app.get('/v2/leave/records')(lambda: {})
    app.get('/v2/leave/daily-stats')(lambda: {})
    def check(conn, ident, feature):
        if permission_error:
            raise HTTPException(403, 'denied')
    routes.install_revenue_leave_list_routes(
        app, engine_instance=lambda: engine, current_identity=lambda: None,
        require_feature=check, feature_allowed=lambda *args: True,
        norm=str, progressive_key=str, google_client=lambda: None,
    )
    monkeypatch.setattr(routes.revenue_auto, 'require_manual', lambda conn: None)
    def forbidden(*args, **kwargs):
        pytest.fail('mutation must not load ledger rows')
    monkeypatch.setattr(store, 'list_entries', forbidden)
    return engine, {r.path: r.endpoint for r in app.routes if hasattr(r, 'endpoint')}


def test_delete_endpoint_queues_locked_detail_only_after_commit(monkeypatch):
    engine, api = endpoints(monkeypatch)
    detail = dict(type='Thu', amount=321.09, note='Locked version')
    monkeypatch.setattr(store, 'soft_delete_entry', lambda conn, **kw: detail)
    background = BackgroundTasks()
    response = api['/v2/revenue/entries/{entry_id}'](7, background,
                    SimpleNamespace(role='admin', employee_username='synthetic'))
    assert response['ok'] and engine.committed
    assert len(background.tasks) == 1
    assert background.tasks[0].kwargs['detail'] == dict(entry_id=7, actor='synthetic', **detail)


@pytest.mark.parametrize('error,status', [(KeyError(7), 404), (PermissionError(7), 403)])
def test_failed_delete_never_schedules_notification(monkeypatch, error, status):
    engine, api = endpoints(monkeypatch)
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(store, 'soft_delete_entry', fail)
    background = BackgroundTasks()
    with pytest.raises(HTTPException) as caught:
        api['/v2/revenue/entries/{entry_id}'](7, background, SimpleNamespace(role='letan'))
    assert caught.value.status_code == status
    assert not background.tasks and not engine.committed


def test_delete_feature_rejection_does_not_reach_writer(monkeypatch):
    engine, api = endpoints(monkeypatch, permission_error=True)
    monkeypatch.setattr(store, 'soft_delete_entry', lambda *a, **kw: pytest.fail('permission bypass'))
    with pytest.raises(HTTPException) as caught:
        api['/v2/revenue/entries/{entry_id}'](7, BackgroundTasks(), SimpleNamespace(role='letan'))
    assert caught.value.status_code == 403 and not engine.committed


@pytest.mark.parametrize('report_date,start,end', [
    (date(2026, 10, 8), None, None),
    (None, None, None),
    (date(2026, 10, 20), date(2026, 9, 16), date(2026, 9, 30)),
])
def test_tip_uses_whole_ledger_totals_and_preserves_period(monkeypatch, report_date, start, end):
    engine, api = endpoints(monkeypatch)
    calls = []
    monkeypatch.setattr(store, 'ledger_totals', lambda conn: dict(
        total_income=12000.25, total_expense=4000.10, report_date=report_date))
    monkeypatch.setattr(routes, '_save_period_tip', lambda *args: calls.append(args))
    response = api['/v2/revenue/tip'](routes.RevenueTipUpdate(amount=100.05,
                    start_date=start, end_date=end), SimpleNamespace(employee_username='synthetic'))
    expected_date = report_date or datetime.now(routes.VN_TZ).date()
    expected_start = start or expected_date.replace(day=1 if expected_date.day <= 15 else 16)
    assert response['balance'] == 7900.10
    assert response['period_tip_start'] == expected_start.isoformat()
    assert response['period_tip_end'] == (end or expected_date).isoformat()
    assert engine.committed and len(calls) == 1


def test_postgres_aggregate_matches_history_and_excludes_deleted(database):
    with database.begin() as conn:
        store.ensure_schema(conn)
        rows = [dict(kind='Thu', amount='100.10', day='2026-09-01', stamp='2026-10-07T18:00:00Z', deleted=False),
                dict(kind='Chi', amount='20.03', day=None, stamp='2026-10-07T18:00:00Z', deleted=False),
                dict(kind='Thu', amount='1000000', day='2099-01-01', stamp='2026-10-07T18:00:00Z', deleted=True)]
        conn.execute(text('''INSERT INTO vera_revenue_entry
            (transaction_type,amount,transaction_date,entered_at,is_deleted)
            VALUES (:kind,:amount,CAST(:day AS date),CAST(:stamp AS timestamptz),:deleted)'''), rows)
        history = store.list_entries(conn)
        totals = store.ledger_totals(conn)
        assert totals == dict(total_income=sum(r['amount'] for r in history if r['type'] == 'Thu'),
                              total_expense=sum(r['amount'] for r in history if r['type'] == 'Chi'),
                              report_date=max(date.fromisoformat(r['date']) for r in history))
        assert totals['report_date'] == date(2026, 10, 8)
        conn.execute(text('DELETE FROM vera_revenue_entry'))
        assert store.ledger_totals(conn) == dict(total_income=0, total_expense=0, report_date=None)

from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import text

import vera_leave_penalty_recheck as recheck
import vera_postgres_job_queue as queue
from test_live_tour_resource_postgres import database

DAY = date(2026, 10, 14)


def manual(uid='manual', **changes):
    return dict(record_uid=uid, employee_name='Synthetic', leave_date=DAY,
                source_sheet_id='sheet', updated_by='Reception', **changes)


def test_manual_source_filter_and_immutable_event_link(monkeypatch):
    calls = []
    class Conn:
        def execute(self, sql, params):
            return SimpleNamespace(scalar=lambda: params['uid'] == 'linked')
    monkeypatch.setattr(queue, 'enqueue_conn', lambda c, q, key, payload: calls.append((key, payload)) or True)
    rows = [manual(), manual('linked'), {**manual('auto'), 'source_sheet_id':'postgres:auto_check'},
            {**manual('mirror'), 'updated_by':'AUTO UPDATE 24/7'},
            {**manual('other'), 'employee_name':'Another'}]
    assert recheck.enqueue_deleted(Conn(), rows, manual_sheet_id='sheet') == 2
    assert [p['employee'] for _, p in calls] == ['Synthetic', 'Another']


def test_queue_rolls_back_with_delete_and_retries_without_recreating_jobs(database):
    queue.ensure_schema(lambda: database)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE vera_auto_check_event(leave_record_uid text)'))
        conn.execute(text('CREATE TABLE leaves(uid text)'))
        conn.execute(text("INSERT INTO leaves VALUES('manual')"))
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            conn.execute(text('DELETE FROM leaves'))
            assert recheck.enqueue_deleted(conn, [manual()], manual_sheet_id='sheet') == 1
            raise RuntimeError('rollback')
    assert queue.claim_one(lambda: database, recheck.QUEUE) is None
    with database.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM leaves')).scalar_one() == 1
        conn.execute(text('DELETE FROM leaves'))
        assert recheck.enqueue_deleted(conn, [manual()], manual_sheet_id='sheet') == 1
        assert recheck.enqueue_deleted(conn, [manual()], manual_sheet_id='sheet') == 0
    assert queue.claim_one(lambda: database, recheck.QUEUE)['payload'] == {'employee':'Synthetic','work_date':'2026-10-14'}


def test_worker_atomic_rules_preserve_lease_and_retry_pending_evidence(database, monkeypatch):
    queue.ensure_schema(lambda: database)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE fine(value int)'))
        queue.enqueue_conn(conn, recheck.QUEUE, 'delete:a', {'employee':'Synthetic','work_date':DAY.isoformat()})
    def pending(conn, employee, day):
        assert employee == 'Synthetic' and day == DAY
        conn.execute(text('INSERT INTO fine VALUES(1)'))
        raise recheck.EvidencePending()
    monkeypatch.setattr(recheck, 'evaluate', pending)
    assert recheck.process_one(lambda: database)
    with database.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM fine')).scalar_one() == 0
        assert conn.execute(text("SELECT status FROM vera_background_job")).scalar_one() == 'retry'
        conn.execute(text('UPDATE vera_background_job SET available_at=NOW()'))
    monkeypatch.setattr(recheck, 'evaluate', lambda conn, *args: conn.execute(text('INSERT INTO fine VALUES(2)')))
    assert recheck.process_one(lambda: database)
    assert not recheck.process_one(lambda: database)
    with database.connect() as conn:
        assert conn.execute(text('SELECT value FROM fine')).scalar_one() == 2
        assert conn.execute(text('SELECT status FROM vera_background_job')).scalar_one() == 'done'


@pytest.mark.parametrize('state', ['ready', 'stale', 'paused', 'no_violation', 'rule_error'])
def test_recheck_scopes_all_rules_and_reuses_one_connection(monkeypatch, state):
    import timesoft_sync_job as sync
    import vera_auto_check as auto
    import vera_facegate_runtime as runtime
    import vera_attendance_source as source
    import vera_missing_checkin_absence as absence
    conn = object(); calls = []
    monkeypatch.setattr(source, 'source_for', lambda _: 'facegate')
    monkeypatch.setattr(auto, 'penalties_paused', lambda _: state == 'paused')
    monkeypatch.setattr(auto, 'automatic_penalty_employee_eligible', lambda *a: True)
    monkeypatch.setattr(auto, 'load_config', lambda _: {})
    monkeypatch.setattr(auto, 'load_catalog', lambda _: {})
    monkeypatch.setattr(runtime, 'records', lambda *a: [dict(employee_name='Synthetic', attendance_fine_evidence_ready=state!='stale')])
    monkeypatch.setattr(runtime, 'worker_frames', lambda *a: [(DAY,pd.DataFrame({'employeeInfo.Name':['Synthetic','Other']}))])
    def arrival(engine, cfg, employees, catalog, frames, **kwargs):
        assert engine.conn is conn and list(employees.values()) == ['Synthetic']
        assert frames[0][1]['employeeInfo.Name'].tolist() == ['Synthetic']
        calls.append('arrival')
        return {'errors':int(state=='rule_error'), 'added':int(state!='no_violation')}
    def breaks(engine, catalog, **kwargs):
        assert engine.conn is conn and kwargs == dict(work_date=DAY, employee_names={'Synthetic'})
        calls.append('break'); return {}
    def missing(c, **kwargs):
        assert c is conn and kwargs == dict(work_date=DAY, employee_names={'Synthetic'})
        calls.append('absence'); return {}
    monkeypatch.setattr(sync,'process_timesoft_penalties',arrival)
    monkeypatch.setattr(sync,'process_break_return_penalties',breaks)
    monkeypatch.setattr(absence,'process',missing)
    if state in {'stale','paused','rule_error'}:
        with pytest.raises(recheck.EvidencePending): recheck.evaluate(conn,'Synthetic',DAY)
    else:
        recheck.evaluate(conn,'Synthetic',DAY)
    assert calls == ([] if state in {'stale','paused'} else ['arrival','break','absence'])


def test_existing_rules_adapter_never_opens_another_connection():
    entered=[]
    class Conn:
        @contextmanager
        def begin_nested(self):
            entered.append(1)
            yield self
    conn=Conn()
    with recheck._TransactionEngine(conn).begin() as actual:
        assert actual is conn
    assert entered == [1]


def test_enqueue_is_inside_canonical_delete_transaction():
    from pathlib import Path
    source=Path('vera_web_v2_api.py').read_text().split('def _delete_leave_uids',1)[1].split('@app.delete',1)[0]
    assert source.index('_validate_delete_permission') < source.index('DELETE FROM leave_records')
    assert source.index('DELETE FROM leave_records') < source.index('enqueue_deleted(conn, rows') < source.index('tx.commit()')
    assert 'penalty_recheck_queued' in source


def test_break_recheck_ignores_other_employee(monkeypatch):
    import timesoft_sync_job as sync
    import vera_web_v2_break_return_penalty as returned
    conn=object(); seen=[]
    @contextmanager
    def begin(): yield conn
    monkeypatch.setattr(sync.auto_check, 'penalties_paused', lambda c: False)
    monkeypatch.setattr(sync, '_confirmed_break_return_records', lambda *a, **kw: [
        {'employee_name':'Synthetic'}, {'employee_name':'Other'}])
    monkeypatch.setattr(returned, 'confirmed_break_return_fact', lambda row, day: seen.append((row['employee_name'],day)))
    sync.process_break_return_penalties(SimpleNamespace(begin=begin), {}, work_date=DAY, employee_names={'Synthetic'})
    assert seen == [('Synthetic',DAY)]

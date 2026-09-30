from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import text

import vera_missing_checkin_absence as rule
from vera_facegate_control_log import VN_TZ
from test_live_tour_resource_postgres import database

REAL_SAVE = rule.auto_check.save_violation
REAL_SCHEMA = rule.auto_check.ensure_schema

POLICY = dict(enabled=True, ca1_enabled=True, ca2_enabled=True, revision=0)


@pytest.mark.parametrize('shift,hour', [('Ca 1', 15), ('Ca 2', 17)])
def test_strict_cutoff_and_sync_after_cutoff(shift, hour):
    cutoff = datetime(2026, 9, 30, hour, tzinfo=VN_TZ)
    row = dict(employee_username='Test', employee_name='Test', shift_code=shift)
    args = dict(row=row, policy=POLICY, mapped={'Test'}, checked=set(), leave_names=set())
    assert not rule.eligible_schedule(**args, now=cutoff, synced=cutoff)
    assert not rule.eligible_schedule(**args, now=cutoff+timedelta(seconds=1), synced=cutoff)
    assert rule.eligible_schedule(**args, now=cutoff+timedelta(seconds=1), synced=cutoff+timedelta(seconds=1))
    for override in (dict(mapped=set()), dict(checked={'Test'}), dict(leave_names={'test'}),
                     dict(policy={**POLICY, 'ca1_enabled': False, 'ca2_enabled': False})):
        assert not rule.eligible_schedule(**{**args, **override}, now=cutoff+timedelta(seconds=1), synced=cutoff+timedelta(seconds=1))


class Identity(BaseModel):
    role: str = 'admin'
    employee_username: str = 'Admin Test'


def client_for(engine, role='admin'):
    app = FastAPI()
    rule.install_routes(app, engine_instance=lambda: engine, current_identity=lambda: Identity(role=role),
                        require_feature=lambda *args: None, identity_type=Identity)
    return TestClient(app)


@pytest.mark.parametrize('role', ['letan', 'quanly', 'leader', 'nhanvien'])
def test_admin_only(role):
    response = client_for(None, role).put('/v2/rules/missing-checkin-absence',
        json=dict(enabled=False, ca1_enabled=True, ca2_enabled=True, expected_revision=0))
    assert response.status_code == 403


def test_policy_revision_and_persistence(database):
    with database.begin() as conn:
        conn.execute(text('ALTER TABLE vera_app_setting ADD COLUMN source text, ADD COLUMN updated_by text, ADD COLUMN created_at timestamptz'))
        assert rule.load_policy(conn)['enabled']
    body = dict(enabled=True, ca1_enabled=False, ca2_enabled=True, expected_revision=0)
    client = client_for(database)
    saved = client.put('/v2/rules/missing-checkin-absence', json=body)
    assert saved.status_code == 200 and saved.json()['revision'] == 1
    assert not saved.json()['ca1_enabled'] and saved.json()['ca2_enabled']
    assert client.put('/v2/rules/missing-checkin-absence', json=body).status_code == 409


@pytest.fixture
def scenario(monkeypatch):
    import vera_attendance_source as source
    import vera_facegate_attendance as fg
    import vera_facegate_runtime as runtime
    import vera_attendance_participation as participation
    import vera_missing_checkin_notifications as alerts
    import vera_resource_concurrency as locks
    import vera_notification_delivery as delivery
    now = datetime(2026, 9, 30, 17, 1, tzinfo=VN_TZ)
    data = dict(rows=[{'EmployeeName': 'Other'}], events=[], issues=[],
                index={'ref': {'username': 'Test'}},
                syncs=[{'work_date': now.date().isoformat(), 'last_synced_at': now.isoformat()}])
    state = SimpleNamespace(now=now, data=data, complete=True, leaves=[], saved=[], notices=[], policy=POLICY.copy())
    monkeypatch.setattr(source, 'source_for', lambda day: 'facegate')
    monkeypatch.setattr(rule, 'load_policy', lambda conn: state.policy)
    monkeypatch.setattr(fg, 'project_evidence', lambda conn, left, right: data)
    monkeypatch.setattr(runtime, 'archive_complete', lambda *args: state.complete)
    monkeypatch.setattr(participation, 'suspended', lambda *args: False)
    monkeypatch.setattr(alerts, '_staff_scheduled_rows', lambda *args: [dict(employee_username='Test', employee_name='Test', employee_role='nhanvien', shift_code='Ca 2')])
    monkeypatch.setattr(alerts, '_scheduled_rows', lambda *args: [])
    monkeypatch.setattr(locks, 'lock_transition', lambda *args, **kwargs: None)
    monkeypatch.setattr(rule.auto_check, 'ensure_schema', lambda *args: None)
    catalog = {rule.auto_check._norm(reason): {'name': reason, 'penalty': amount} for reason, amount in zip(rule.REASONS, (123000, 456000))}
    monkeypatch.setattr(rule.auto_check, 'load_catalog', lambda conn: catalog)
    def save(conn, **kwargs):
        state.saved.append(kwargs)
        state.leaves.append(dict(employee_name='Test', leave_reason=kwargs['reason_item']['name']))
        return True, 'ADDED'
    monkeypatch.setattr(rule.auto_check, 'save_violation', save)
    monkeypatch.setattr(delivery, 'enqueue', lambda *args, **kwargs: state.notices.append((args, kwargs)))
    class Result:
        def __init__(self, rows): self.rows = rows
        def mappings(self): return self
        def all(self): return self.rows
        def one(self): return {'id': 7, 'leave_record_uid': 'uid', 'penalty': state.saved[-1]['reason_item']['penalty']}
    class Conn:
        def execute(self, query, params=None): return Result(state.leaves)
    state.conn = Conn()
    return state


@pytest.mark.parametrize('day,reason,amount', [(30, rule.REASONS[0], '123,000'), (3, rule.REASONS[1], '456,000'), (4, rule.REASONS[1], '456,000')])
def test_weekday_weekend_official_amount_and_replay(scenario, day, reason, amount):
    s = scenario
    now = s.now if day == 30 else s.now.replace(month=10, day=day)
    s.data['syncs'][0].update(work_date=now.date().isoformat(), last_synced_at=now.isoformat())
    assert rule.process(s.conn, now=now)['added'] == 1
    assert s.saved[0]['reason_item']['name'] == reason
    assert amount in s.notices[0][0][2]['body']
    assert s.notices[0][0][1] == rule.KEY
    assert rule.process(s.conn, now=now)['added'] == 0
    assert len(s.saved) == len(s.notices) == 1


@pytest.mark.parametrize('condition', ['empty', 'incomplete', 'ambiguous', 'stale', 'future', 'disabled', 'checked', 'leave', 'unmapped'])
def test_no_writes_without_reliable_absence(scenario, condition):
    s = scenario
    if condition == 'empty': s.data['rows'] = []
    if condition == 'incomplete': s.complete = False
    if condition == 'ambiguous': s.data['issues'] = [{'reason': 'unmapped_reference'}]
    if condition == 'stale': s.data['syncs'][0]['last_synced_at'] = (s.now-timedelta(minutes=6)).isoformat()
    if condition == 'future': s.data['syncs'][0]['last_synced_at'] = (s.now+timedelta(seconds=1)).isoformat()
    if condition == 'disabled': s.policy['enabled'] = False
    if condition == 'checked': s.data['rows'].append({'EmployeeName': 'Test'})
    if condition == 'leave': s.leaves.append({'employee_name': 'Test', 'leave_reason': 'Nghỉ CÓ phép'})
    if condition == 'unmapped': s.data['index'] = {}
    assert rule.process(s.conn, now=s.now)['added'] == 0
    assert not s.saved and not s.notices


def test_registered_late_still_requires_checkin(scenario):
    s = scenario
    s.leaves.append({'employee_name': 'Test', 'leave_reason': 'Đi trễ CÓ phép'})
    assert rule.process(s.conn, now=s.now)['added'] == 1


def test_real_penalty_transaction_rollback_and_replay(database, scenario, monkeypatch):
    import vera_notification_delivery as delivery
    s = scenario
    monkeypatch.setattr(rule.auto_check, 'save_violation', REAL_SAVE)
    monkeypatch.setattr(rule.auto_check, 'ensure_schema', REAL_SCHEMA)
    monkeypatch.setattr(rule.auto_check.progressive_penalty, 'load_weekend_unpaid_enabled', lambda conn: False)
    with database.begin() as conn:
        conn.execute(text("""CREATE TABLE leave_records (
            source_sheet_id text, source_row bigint, leave_date date, employee_name text,
            leave_reason text, leave_type text, detail text, calculated_days numeric,
            accumulated_leave numeric, penalty numeric, update_date text, update_time text,
            updated_by text, weekday_label text, payload jsonb, record_uid text,
            created_at timestamptz, updated_at timestamptz);
            CREATE TABLE test_absence_outbox(event_key text PRIMARY KEY, body text);"""))
        REAL_SCHEMA(conn)
    def enqueue(conn, source, payload, event_key):
        conn.execute(text('INSERT INTO test_absence_outbox VALUES(:key,:body)'), {'key': event_key, 'body': payload['body']})
    monkeypatch.setattr(delivery, 'enqueue', enqueue)
    with pytest.raises(RuntimeError, match='abort'):
        with database.begin() as conn:
            assert rule.process(conn, now=s.now)['added'] == 1
            raise RuntimeError('abort')
    with database.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar() == 0
        assert conn.execute(text('SELECT count(*) FROM test_absence_outbox')).scalar() == 0
        assert rule.process(conn, now=s.now)['added'] == 1
    with database.begin() as conn:
        assert rule.process(conn, now=s.now)['added'] == 0
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar() == 1
        assert conn.execute(text('SELECT penalty FROM leave_records')).scalar() == 123000
        assert conn.execute(text('SELECT count(*) FROM test_absence_outbox')).scalar() == 1
        assert conn.execute(text('SELECT employee_notified_at IS NOT NULL FROM vera_auto_check_event')).scalar()

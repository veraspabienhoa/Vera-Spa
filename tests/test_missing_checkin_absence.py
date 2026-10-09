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


@pytest.mark.parametrize('shift,hour', [('Ca 1', 17), ('Ca 2', 19)])
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
    now = datetime(2026, 9, 30, 19, 1, tzinfo=VN_TZ)
    data = dict(rows=[{'EmployeeName': 'Other'}], events=[], issues=[],
                index={'ref': {'username': 'Test'}},
                syncs=[{'work_date': now.date().isoformat(), 'last_synced_at': now.isoformat()}])
    state = SimpleNamespace(now=now, data=data, complete=True, leaves=[], saved=[], notices=[], policy=POLICY.copy())
    monkeypatch.setattr(source, 'source_for', lambda day: 'facegate')
    monkeypatch.setattr(rule, 'load_policy', lambda conn: state.policy)
    monkeypatch.setattr(rule.auto_check, 'load_config', lambda conn: {'status': 'PAUSED' if state.policy.get('paused') else 'RUNNING'})
    monkeypatch.setattr(fg, 'project_evidence', lambda conn, left, right: data)
    monkeypatch.setattr(runtime, 'archive_complete', lambda *args: state.complete)
    monkeypatch.setattr(participation, 'suspended', lambda *args: False)
    monkeypatch.setattr(alerts, '_staff_scheduled_rows', lambda *args: [dict(employee_username='Test', employee_name='Test', employee_role='nhanvien', shift_code='Ca 2')])
    monkeypatch.setattr(alerts, '_scheduled_rows', lambda *args: [])
    monkeypatch.setattr(locks, 'lock_transition', lambda *args, **kwargs: None)
    monkeypatch.setattr(rule.auto_check, 'ensure_schema', lambda *args: None)
    catalog = {rule.auto_check._norm(reason): {'name': reason, 'penalty': amount} for reason, amount in zip(rule.REASONS, (123000, 456000))}
    monkeypatch.setattr(rule.auto_check, 'load_catalog', lambda conn: catalog)
    state.catalog = catalog
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
        def first(self): return self.rows[0] if self.rows else None
        def one(self): return {'id': 7, 'leave_record_uid': 'uid', 'penalty': state.saved[-1]['reason_item']['penalty']}
    class Conn:
        def execute(self, query, params=None):
            if "to_regclass('vera_holiday_leave_period')" in str(query):
                return SimpleNamespace(scalar=lambda: None)
            if 'SELECT id FROM vera_auto_check_event' in str(query):
                return Result([{'id': 7}] if state.saved else [])
            return Result(state.leaves)
        def begin_nested(self):
            return SimpleNamespace(commit=lambda: None, rollback=lambda: None)
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


@pytest.mark.parametrize('condition', ['empty', 'incomplete', 'ambiguous', 'stale', 'future', 'disabled', 'paused', 'checked', 'leave', 'unmapped'])
def test_no_writes_without_reliable_absence(scenario, condition):
    s = scenario
    if condition == 'empty': s.data['rows'] = []
    if condition == 'incomplete': s.complete = False
    if condition == 'ambiguous': s.data['issues'] = [{'reason': 'unmapped_reference'}]
    if condition == 'stale': s.data['syncs'][0]['last_synced_at'] = (s.now-timedelta(minutes=6)).isoformat()
    if condition == 'future': s.data['syncs'][0]['last_synced_at'] = (s.now+timedelta(seconds=1)).isoformat()
    if condition == 'disabled': s.policy['enabled'] = False
    if condition == 'paused': s.policy['paused'] = True
    if condition == 'checked': s.data['rows'].append({'EmployeeName': 'Test'})
    if condition == 'leave': s.leaves.append({'employee_name': 'Test', 'leave_reason': 'Nghỉ CÓ phép'})
    if condition == 'unmapped': s.data['index'] = {}
    assert rule.process(s.conn, now=s.now)['added'] == 0
    assert not s.saved and not s.notices


def test_registered_late_still_requires_checkin(scenario):
    s = scenario
    s.leaves.append({'employee_name': 'Test', 'leave_reason': 'Đi trễ CÓ phép'})
    half = {'name': 'Về sớm KHÔNG phép', 'days': 0.5, 'penalty': 60000}
    s.catalog[rule.auto_check._norm(half['name'])] = half
    assert rule.process(s.conn, now=s.now)['added'] == 1
    assert s.saved[0]['reason_item'] == half
    assert s.leaves[0]['leave_reason'] == 'Đi trễ CÓ phép'


@pytest.mark.parametrize('weekend,half_day,with_late', [
    (False, False, False), (True, False, False),
    (False, False, True), (True, False, True),
    (False, True, True), (True, True, True),
])
def test_existing_matching_absence_is_preserved_on_every_refresh(scenario, weekend, half_day, with_late):
    from copy import deepcopy
    s = scenario
    now = s.now.replace(month=10, day=3) if weekend else s.now
    s.data['syncs'][0].update(work_date=now.date().isoformat(), last_synced_at=now.isoformat())
    reason = ('Về sớm CUỐI TUẦN KHÔNG phép' if weekend else 'Về sớm KHÔNG phép') if half_day else rule.REASONS[weekend]
    item = {'name': reason, 'days': 0.5 if half_day else 0, 'penalty': 123000}
    s.catalog[rule.auto_check._norm(reason)] = item
    s.leaves.append(dict(record_uid='registered', employee_name='Test', leave_reason=reason,
                         detail='Người Thứ 1 | Ghi chú đã đăng ký', penalty=123000))
    if with_late:
        s.leaves.append(dict(record_uid='late', employee_name='Test', leave_reason='Đi trễ CÓ phép'))
    before = deepcopy(s.leaves)
    for _ in range(2):
        assert rule.process(s.conn, now=now) == {'added': 0, 'skipped': 1}
    assert s.leaves == before
    assert not s.saved and not s.notices


def test_registered_absence_cohort_keeps_uids_ordinals_and_money(database, scenario, monkeypatch):
    import vera_missing_checkin_notifications as alerts
    s = scenario
    names = ('An Nhiên', 'Phương Vy', 'Linh Đan')
    s.data['index'] = {str(i): {'username': name} for i, name in enumerate(names)}
    monkeypatch.setattr(alerts, '_staff_scheduled_rows', lambda *args: [
        dict(employee_username=name, employee_name=name, employee_role='nhanvien', shift_code='Ca 2')
        for name in names[:2]])
    with database.begin() as conn:
        REAL_SCHEMA(conn)
        conn.execute(text('''CREATE TABLE leave_records(
            record_uid text PRIMARY KEY, leave_date date, employee_name text,
            leave_reason text, detail text, penalty numeric, payload jsonb)'''))
        for ordinal, name in enumerate(names, 1):
            conn.execute(text('''INSERT INTO leave_records VALUES(
                :uid,:day,:name,:reason,:detail,:penalty,CAST(:payload AS jsonb))'''),
                dict(uid=f'original-{ordinal}', day=s.now.date(), name=name, reason=rule.REASONS[0],
                     detail=f'Người Thứ {ordinal} nghỉ không phép',
                     penalty=500000 if ordinal < 3 else 600000, payload='{"original":true}'))
        before = conn.execute(text('SELECT * FROM leave_records ORDER BY record_uid')).mappings().all()
        for _ in range(2):
            assert rule.process(conn, now=s.now) == {'added': 0, 'skipped': 2}
        assert conn.execute(text('SELECT * FROM leave_records ORDER BY record_uid')).mappings().all() == before
        assert conn.execute(text('SELECT count(*) FROM vera_auto_check_event')).scalar() == 0
        assert conn.execute(text("SELECT to_regclass('vera_absence_replacement_audit')")).scalar() is None
    assert not s.saved and not s.notices


def test_real_penalty_transaction_rollback_and_replay(database, scenario, monkeypatch):
    import vera_notification_delivery as delivery
    s = scenario
    monkeypatch.setattr(rule.auto_check, 'automatic_penalty_employee_eligible', lambda conn, employee, work_date: True)
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


def test_manual_reversal_is_not_recreated(database, scenario, monkeypatch):
    s = scenario
    with database.begin() as conn:
        REAL_SCHEMA(conn)
        conn.execute(text("INSERT INTO vera_auto_check_event(event_key,work_date,employee_name,reason,source,status) VALUES('reviewed',:day,'Test',:reason,:source,'revoked')"),
                     {'day': s.now.date(), 'reason': rule.REASONS[0], 'source': rule.SOURCE})
        # No leave table is needed: a reviewed decision stops before any write.
        assert rule.process(conn, now=s.now)['added'] == 0
        assert not s.saved and not s.notices


def test_half_day_missing_catalog_never_falls_back_to_full_day(scenario):
    s = scenario
    s.leaves.append({'employee_name': 'Test', 'leave_reason': 'Đi trễ CÓ phép'})
    result = rule.process(s.conn, now=s.now)
    assert result['added'] == 0
    assert result['review_required'][0]['reason'] == 'missing_half_day_official_reason'
    assert not s.saved and not s.notices


def test_checkin_arriving_before_final_write_cancels_penalty(scenario, monkeypatch):
    import vera_facegate_attendance as fg
    from copy import deepcopy
    s = scenario
    fresh = deepcopy(s.data)
    fresh['rows'].append({'EmployeeName': 'Test'})
    reads = iter([s.data, fresh])
    monkeypatch.setattr(fg, 'project_evidence', lambda *args: next(reads))
    assert rule.process(s.conn, now=s.now)['added'] == 0
    assert not s.saved and not s.notices


def test_half_day_weekend_uses_own_catalog_amount():
    weekday = {'name': 'Về sớm KHÔNG phép', 'days': 0.5, 'penalty': 123}
    weekend = {'name': 'Về sớm CUỐI TUẦN KHÔNG phép', 'days': 0.5, 'penalty': 456}
    catalog = {rule.auto_check._norm(item['name']): item for item in (weekday, weekend)}
    assert rule.absence_item(catalog, date(2026, 9, 30), True) == weekday
    assert rule.absence_item(catalog, date(2026, 10, 3), True) == weekend


def test_unpermitted_replacement_archives_and_rolls_back(database):
    with database.begin() as conn:
        REAL_SCHEMA(conn)
        conn.execute(text('CREATE TABLE leave_records(record_uid text,leave_date date,employee_name text,leave_reason text,penalty numeric)'))
        conn.execute(text("INSERT INTO leave_records VALUES('old', '2026-09-30','Test','Đi trễ KHÔNG phép',400000), ('approved','2026-09-30','Test','Đi trễ CÓ phép',0)"))
        conn.execute(text("INSERT INTO vera_auto_check_event(event_key,work_date,employee_name,reason,source,status,leave_record_uid) VALUES('late','2026-09-30','Test','Đi trễ KHÔNG phép','old','added','old')"))
    def replace(conn):
        rows = conn.execute(text("SELECT * FROM leave_records WHERE record_uid='old' FOR UPDATE")).mappings().all()
        rule.replace_unpermitted(conn, rows, day=date(2026,9,30), username='Test', target_reason=rule.REASONS[0])
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            replace(conn)
            raise RuntimeError('new absence failed')
    with database.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar() == 2
        replace(conn)
    with database.connect() as conn:
        assert conn.execute(text('SELECT record_uid FROM leave_records')).scalar() == 'approved'
        assert conn.execute(text('SELECT status FROM vera_auto_check_event')).scalar() == 'superseded'
        assert conn.execute(text("SELECT replaced_rows->0->>'penalty' FROM vera_absence_replacement_audit")).scalar() == '400000'


@pytest.mark.parametrize('role', ['locker', 'letan', 'tapvu', 'support', 'quanly', 'admin'])
def test_non_ktv_schedule_never_creates_absence(scenario, monkeypatch, role):
    import vera_missing_checkin_notifications as alerts
    s = scenario
    monkeypatch.setattr(alerts, '_staff_scheduled_rows', lambda *args: [dict(
        employee_username='Test', employee_name='Test', employee_role=role, shift_code='Ca 2',
        overtime_shift='TC Ca 1', overtime_start_time='09:30')])
    assert rule.process(s.conn, now=s.now)['added'] == 0
    assert not s.saved and not s.notices


def test_registered_holiday_suppresses_unpaid_absence_and_notification(scenario, monkeypatch):
    import vera_holiday_leave as holiday
    monkeypatch.setattr(holiday, 'approved_day', lambda conn, username, day: True)
    assert rule.process(scenario.conn, now=scenario.now)['added'] == 0
    assert scenario.saved == [] and scenario.notices == []

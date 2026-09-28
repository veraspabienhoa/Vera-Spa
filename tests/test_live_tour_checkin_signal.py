"""Source commit -> coalesced durable job, without increasing SQL round trips."""
import json
import os
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, text

import vera_postgres as vpg
import vera_postgres_job_queue as queue
import vera_live_tour_checkin_signal as signal

NOW = datetime(2026, 9, 28, 10, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
KEY = 'timesoft_employee_checkin_today'


def punch(name='An', clock='09:00:00'):
    return {'EmployeeName': name, 'WorkDateStr': '28/09/2026',
            'MachineTimeCheckInStr': '28/09/2026 ' + clock}


def test_signature_ignores_order_duplicates_payroll_and_vendor_shifts():
    rows = [punch(), punch('Bình')]
    original = signal.fingerprint(json.dumps(rows))
    changed = [{**row, 'WorkTimeName': 'Ca 2', 'WorkMinutes': 999} for row in reversed(rows)]
    assert signal.fingerprint(json.dumps(changed + changed)) == original
    assert signal.fingerprint(json.dumps([punch(clock='09:01:00')])) != signal.fingerprint(json.dumps([punch()]))
    assert signal.fingerprint(json.dumps([{**punch(), 'MachineTimeCheckOutStr': ''}])) != signal.fingerprint(json.dumps([punch()]))


@pytest.fixture
def db():
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('VERA_TEST_POSTGRES_URL required')
    schema = 'signal_test_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, pool_size=1, max_overflow=0, pool_timeout=1,
                           connect_args={'options': f'-csearch_path={schema}'})
    vpg.ensure_schema(engine)
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
    admin.dispose()


def send(db, rows=None, key=KEY, now=NOW):
    with db.begin() as conn:
        return signal.record_refresh(conn, key, json.dumps(rows or [punch()]), 'test', now=now)


def job(db):
    with db.connect() as conn:
        return dict(conn.execute(text('SELECT * FROM vera_background_job')).mappings().one())


def test_replays_do_not_schedule_work_and_bursts_coalesce(db):
    send(db)
    first = queue.claim_one(lambda: db, signal.QUEUE)
    queue.mark_done(lambda: db, first)
    before = job(db)
    for _ in range(10):
        send(db, [{**punch(), 'WorkMinutes': 100}])
    assert job(db) == before
    assert queue.claim_one(lambda: db, signal.QUEUE) is None
    for i in range(10):
        send(db, [punch(), punch('Bình', f'09:{i:02}:00')])
    assert job(db)['status'] == 'pending'
    assert job(db)['payload']['generation'] == 11
    assert job(db)['id'] == first['id']


def test_change_during_processing_is_not_lost_and_stale_completion_is_fenced(db):
    send(db)
    first = queue.claim_one(lambda: db, signal.QUEUE)
    send(db, [punch(), punch('Bình')])
    assert job(db)['status'] == 'processing'
    assert queue.claim_one(lambda: db, signal.QUEUE) is None
    queue.mark_done(lambda: db, first)
    assert job(db)['status'] == 'pending'
    second = queue.claim_one(lambda: db, signal.QUEUE)
    assert second['payload']['generation'] == 2
    queue.mark_done(lambda: db, first)
    assert job(db)['status'] == 'processing'
    queue.mark_done(lambda: db, second)
    assert job(db)['status'] == 'done'


def test_source_cache_and_signal_rollback_together_and_keep_two_statements(db, monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return NOW
    monkeypatch.setattr(signal, 'datetime', Clock)
    statements = []
    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db, 'before_cursor_execute', count)
    with pytest.raises(RuntimeError):
        with db.begin() as conn:
            vpg._write_dataset_conn(conn, KEY, pd.DataFrame([punch()]), 120)
            assert len(statements) == 2
            raise RuntimeError('rollback')
    event.remove(db, 'before_cursor_execute', count)
    with db.connect() as conn:
        for table in ('vera_dataset_cache', 'vera_sync_event', 'vera_background_job'):
            assert conn.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0
    with db.begin() as conn:
        vpg._write_dataset_conn(conn, KEY, pd.DataFrame([punch()]), 120)
    assert job(db)['status'] == 'pending'


def test_sources_share_one_job_and_old_days_do_not_schedule(db):
    assert not send(db, key='timesoft_employee_checkin_20260927')
    assert not send(db, key='employees')
    for key in (KEY, 'timesoft_employee_checkin_20260928', 'timesoft_employee_checkin_20260928_raw'):
        assert send(db, key=key)
    assert len(job(db)['payload']['fingerprints']) == 3
    before = job(db)['payload']['generation']
    send(db, now=NOW + timedelta(days=1))
    assert job(db)['payload']['generation'] == before + 1
    assert job(db)['payload']['day'] == '2026-09-29'
    assert len(job(db)['payload']['fingerprints']) == 1


def test_retry_and_lease_recovery_keep_latest_signal(db):
    send(db)
    first = queue.claim_one(lambda: db, signal.QUEUE)
    send(db, [punch('Bình')])
    queue.mark_retry(lambda: db, first, RuntimeError('transient'))
    with db.begin() as conn:
        conn.execute(text("UPDATE vera_background_job SET available_at=NOW()"))
    retry = queue.claim_one(lambda: db, signal.QUEUE)
    assert retry['payload']['generation'] == 2
    with db.begin() as conn:
        conn.execute(text("UPDATE vera_background_job SET locked_at=NOW()-INTERVAL '11 minutes'"))
    recovered = queue.claim_one(lambda: db, signal.QUEUE)
    queue.mark_done(lambda: db, retry)
    assert job(db)['status'] == 'processing'
    queue.mark_done(lambda: db, recovered)
    assert job(db)['status'] == 'done'


def test_regular_queue_jobs_still_complete(db):
    queue.enqueue(lambda: db, signal.QUEUE, 'scheduled', {'reason': 'scheduled'})
    item = queue.claim_one(lambda: db, signal.QUEUE)
    queue.mark_done(lambda: db, item)
    assert job(db)['status'] == 'done'


def test_real_worker_opens_vera_shift_without_full_attendance_or_five_minute_tick(db, monkeypatch):
    import time
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    import vera_web_v2_live_tour as live
    from vera_web_v2_live_tour_checkin import with_checkin
    from test_live_tour_backend import employee

    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE', 'off')
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(live, 'datetime', Clock)
    monkeypatch.setattr(signal, 'datetime', Clock)
    # Suppress only the periodic producer, so success must come from cache write.
    monkeypatch.setattr(queue, 'enqueue', lambda *args, **kwargs: False)
    directory = [{'username': 'An', 'full_name': 'An', 'role': 'nhanvien',
                  'payload': {}, 'work_shift': 'Ca 1', 'rotation_cycle': 'Cố định'}]
    monkeypatch.setattr(live, '_employee_directory',
                        lambda conn, now: with_checkin(conn, [dict(r) for r in directory], now))
    state = live._empty_state(NOW)
    state['employees'] = [employee('e1', 'An', shift='')]
    with db.begin() as conn:
        conn.execute(text('CREATE TABLE employees(username text,full_name text,bank_name text,bank_account text)'))
        conn.execute(text("""CREATE TABLE leave_records(id bigserial,employee_name text,
            leave_reason text,leave_type text,leave_date date,record_uid text,source_row int,detail text)"""))
        conn.execute(text("""INSERT INTO vera_app_setting(category,setting_key,value_json)
            VALUES ('live_tour','state',CAST(:state AS jsonb))"""), {'state': json.dumps(state)})
    class Identity(BaseModel):
        employee_username: str = 'admin'
        full_name: str = 'Admin'
        role: str = 'admin'
    attendance_calls = []
    def attendance(*args, **kwargs):
        attendance_calls.append(True)
        raise AssertionError('Check-in must not calculate full attendance')
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda: db,
        current_identity=lambda: Identity(), require_feature=lambda *args: None,
        feature_allowed=lambda *args: True, identity_type=Identity,
        attendance_reader=attendance)
    with TestClient(app) as client:
        with db.begin() as conn:
            vpg._write_dataset_conn(conn, KEY, pd.DataFrame([punch()]), 120)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if job(db)['status'] == 'done':
                break
            time.sleep(0.05)
        assert job(db)['status'] == 'done', job(db)['last_error']
        board = client.get('/v2/live-tour?view=board')
        assert board.status_code == 200, board.text
        assert board.json()['records'][0]['Vào ca'] == 'Ca 1'
        assert not attendance_calls
        with db.connect() as conn:
            saved = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='live_tour' AND setting_key='state'")).scalar_one()
        assert saved['invoices'] == state['invoices']
        assert saved['employees'][0]['tour_count'] == 0

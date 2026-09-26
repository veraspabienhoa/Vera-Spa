import copy
from datetime import timedelta
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sql_event, text

import vera_facegate_attendance as fg
import vera_facegate_sync as sync
from vera_web_v2_facegate_attendance import install_facegate_attendance_routes
from test_facegate_attendance import DAY, ADDRESS, MAP, REF, event


@pytest.fixture
def database(monkeypatch):
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url: pytest.skip('Real PostgreSQL required')
    schema = 'facegate_attendance_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn: conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, pool_size=1, max_overflow=0, pool_timeout=.05,
                           connect_args={'options': f'-csearch_path={schema}'})
    monkeypatch.setenv('VERA_FACEGATE_DEVICE_ID', 'synthetic-device')
    try:
        with engine.begin() as conn:
            sync.ensure_schema(conn)
            conn.execute(text('''CREATE TABLE vera_app_setting(category text,setting_key text,value_json jsonb,
                PRIMARY KEY(category,setting_key))'''))
            conn.execute(text('''CREATE TABLE employees(username text PRIMARY KEY,full_name text,role text,
                work_shift text,shift_start_date text,rotation_cycle text,employment_start_date text,
                stt integer,payload jsonb DEFAULT '{}'::jsonb)'''))
            conn.execute(text('''CREATE TABLE vera_dataset_cache(dataset_key text PRIMARY KEY,payload jsonb)'''))
            conn.execute(text('''CREATE TABLE vera_work_schedule(work_date date,employee_username text,employee_name text,
                department text,shift_code text,start_time text,end_time text)'''))
            conn.execute(text('''CREATE TABLE vera_work_shift_definition(department text,shift_code text,start_time text,end_time text)'''))
            conn.execute(text("""INSERT INTO employees(username,full_name,role,work_shift,shift_start_date,rotation_cycle)
                VALUES ('Ánh Thử','Nguyễn Ánh Thử','nhanvien','Ca 1','2026-09-01','Cố định (Không đổi)')"""))
            settings = [('devices', 'registry', {'devices': [{'id': 'facegate-current', 'address': ADDRESS}]}),
                        ('facegate', 'mapping_synthetic-device', MAP),
                        ('shift', 'shift_definitions', [{'Tên ca': 'Ca 1', 'Giờ bắt đầu': '10:00',
                          'Giờ kết thúc': '23:00', 'Bộ phận': 'Nhân viên + Leader'}])]
            for category, key, value in settings:
                conn.execute(text('INSERT INTO vera_app_setting VALUES (:c,:k,CAST(:v AS jsonb))'),
                             {'c': category, 'k': key, 'v': json.dumps(value)})
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn: conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def batch(count=129):
    return sync.prepare_batch({'source': 'facegate_control_log', 'total_count': count, 'truncated': False,
        'records': [{'event_id': i, 'occurred_at': f'{DAY}T09:59:{i % 60:02d}+07:00',
            'device_name': 'ANH THU', 'status_code': '1', 'type_code': '0', 'registration_ref': REF} for i in range(count)]},
        DAY.isoformat(), ADDRESS)


def test_postgres_batch_roundtrips_and_replay_and_changed_evidence(database):
    calls = []
    def observe(conn, cursor, statement, params, context, executemany): calls.append(statement)
    sql_event.listen(database, 'before_cursor_execute', observe)
    try:
        with database.begin() as conn:
            first = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), batch())
        assert first['inserted_count'] == 129 and len(calls) == 4
        calls.clear()
        with database.begin() as conn:
            second = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), batch())
        assert second['inserted_count'] == 0 and second['stored_day_count'] == 129 and len(calls) == 4
        changed = batch(251)
        changed[-1]['event_id'] = '0'
        changed[-1]['occurred_at'] = changed[0]['occurred_at']
        changed[-1]['payload_sha256'] = 'different'
        with pytest.raises(sync.SyncError, match='existing_event_changed'):
            with database.begin() as conn:
                sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), changed)
        with database.connect() as conn:
            assert conn.execute(text('SELECT COUNT(*) FROM vera_facegate_event')).scalar_one() == 129
    finally:
        sql_event.remove(database, 'before_cursor_execute', observe)


def seed_preview(database):
    with database.begin() as conn:
        sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), batch(1))
        conn.execute(text('UPDATE vera_facegate_sync_day SET last_synced_at=:at'),
                     {'at': f'{DAY + timedelta(days=1)}T01:00:00+07:00'})
        raw = [{'employeeInfo.Name': 'Ánh Thử', 'WorkDateStr': DAY.strftime('%d/%m/%Y'),
                'MachineTimeCheckInStr': DAY.strftime('%d/%m/%Y') + ' 09:59:00'}]
        conn.execute(text('INSERT INTO vera_dataset_cache VALUES (:key,CAST(:value AS jsonb))'),
                     {'key': 'timesoft_employee_checkin_' + DAY.strftime('%Y%m%d'), 'value': json.dumps(raw)})


def test_preview_real_route_reuses_one_connection_and_never_changes_source(database, monkeypatch):
    seed_preview(database)
    # A network attempt in a projection is a regression, even if it succeeds.
    import requests
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *_a, **_k: pytest.fail('Device network in preview'))
    app = FastAPI()
    install_facegate_attendance_routes(app, engine_instance=lambda: database,
        current_identity=lambda: SimpleNamespace(role='admin'), identity_type=SimpleNamespace)
    client = TestClient(app)
    response = client.get(f'/v2/devices/facegate-attendance/preview?start={DAY}&end={DAY}')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['source'] == 'timesoft' and result['attendance_cutover_ready'] is False
    assert result['records'][0]['employee_name'] == 'Ánh Thử'
    assert result['records'][0]['check_in'] == '09:59:00'
    assert result['evidence_differences'] == [] and result['incomplete_days'] == []
    assert result['differences'] == []
    assert result['payroll_and_penalties_written'] is False
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_facegate_event')).scalar_one() == 1
        assert conn.execute(text('SELECT COUNT(*) FROM vera_dataset_cache')).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM vera_app_setting WHERE category='attendance_source'")).scalar_one() == 0


def test_database_read_only_guard_rolls_back_accidental_writer(database, monkeypatch):
    import vera_web_v2_facegate_attendance as api
    app = FastAPI()
    def accidental_write(conn, *_):
        conn.execute(text("DELETE FROM vera_app_setting"))
    monkeypatch.setattr(api, 'preview', accidental_write)
    install_facegate_attendance_routes(app, engine_instance=lambda: database,
        current_identity=lambda: SimpleNamespace(role='admin'), identity_type=SimpleNamespace)
    response = TestClient(app, raise_server_exceptions=False).get(f'/v2/devices/facegate-attendance/preview?start={DAY}&end={DAY}')
    assert response.status_code == 500
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_app_setting')).scalar_one() == 3


def test_incomplete_archive_and_missing_mapping_are_blockers(database):
    seed_preview(database)
    with database.begin() as conn:
        conn.execute(text("UPDATE vera_app_setting SET value_json='[]'::jsonb WHERE category='facegate'"))
        conn.execute(text('UPDATE vera_facegate_sync_day SET last_observed_count=999'))
    with database.connect() as conn: result = fg.preview(conn, DAY, DAY)
    assert 'unmapped_employees' in result['blockers']
    assert 'incomplete_archive_days' in result['blockers']
    assert result['mapping_candidates'][0]['username_candidate'] == 'Ánh Thử'
    assert result['records'][0]['check_in'] == ''

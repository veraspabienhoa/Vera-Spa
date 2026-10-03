import copy
import hashlib
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
                department text,shift_code text,start_time text,end_time text,
                overtime_shift text, overtime_start_time text, overtime_end_time text)'''))
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
        original = batch()
        with database.begin() as conn:
            first = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), original)
        assert first == {'inserted_count': 129, 'already_stored_count': 0,
                         'conflict_count': 0, 'stored_day_count': 129}
        assert len(calls) == 4
        with database.connect() as conn:
            archived_before = [dict(row) for row in conn.execute(text(
                'SELECT * FROM vera_facegate_event ORDER BY event_id,occurred_at'
            )).mappings().all()]
        calls.clear()
        with database.begin() as conn:
            second = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), original)
        assert second == {'inserted_count': 0, 'already_stored_count': 129,
                          'conflict_count': 0, 'stored_day_count': 129}
        # Replay skips the empty event INSERT: read + day upsert + count.
        assert len(calls) == 3
        assert not any('INSERT INTO vera_facegate_event' in sql for sql in calls)

        changed = batch(251)
        observed = json.loads(changed[0]['payload_json'])
        observed['device_name'] = 'ANH THU UPDATED'
        changed[0]['payload_json'] = json.dumps(
            observed, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        changed[0]['payload_sha256'] = hashlib.sha256(
            changed[0]['payload_json'].encode('utf-8')).hexdigest()
        calls.clear()
        with database.begin() as conn:
            third = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), changed)
        assert third == {'inserted_count': 122, 'already_stored_count': 128,
                         'conflict_count': 1, 'stored_day_count': 251}
        assert len(calls) == 5  # read, new rows, audit, day upsert, count
        with database.connect() as conn:
            archived_after = {(r['event_id'], r['occurred_at']): dict(r) for r in conn.execute(
                text('SELECT * FROM vera_facegate_event')).mappings().all()}
            conflict = dict(conn.execute(text(
                'SELECT * FROM vera_facegate_event_conflict')).mappings().one())
        # Every byte/column of every previously archived event is unchanged.
        for row in archived_before:
            assert archived_after[(row['event_id'], row['occurred_at'])] == row
        assert conflict['stored_payload_sha256'] == original[0]['payload_sha256']
        assert conflict['observed_payload_sha256'] == changed[0]['payload_sha256']
        assert conflict['observed_payload_json'] == changed[0]['payload_json']
        assert conflict['observation_count'] == 1

        calls.clear()
        with database.begin() as conn:
            repeated = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), changed)
        assert repeated == {'inserted_count': 0, 'already_stored_count': 250,
                            'conflict_count': 1, 'stored_day_count': 251}
        assert len(calls) == 4  # no new events; the same conflict is audited again
        with database.connect() as conn:
            saved = conn.execute(text(
                'SELECT * FROM vera_facegate_event_conflict')).mappings().one()
            archive_repeated = {(r['event_id'], r['occurred_at']): dict(r) for r in conn.execute(
                text('SELECT * FROM vera_facegate_event')).mappings().all()}
        assert saved['observation_count'] == 2
        assert saved['first_observed_at'] == conflict['first_observed_at']
        assert archive_repeated == archived_after
    finally:
        sql_event.remove(database, 'before_cursor_execute', observe)


def test_postgres_new_events_remain_bounded_to_250_per_statement(database):
    calls, batch_sizes = [], []
    def observe(conn, cursor, statement, params, context, executemany):
        calls.append(statement)
        if params and 'batch' in params:
            batch_sizes.append(len(json.loads(params['batch'])))
    sql_event.listen(database, 'before_cursor_execute', observe)
    try:
        with database.begin() as conn:
            result = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), batch(501))
        assert result['inserted_count'] == result['stored_day_count'] == 501
        assert result['conflict_count'] == result['already_stored_count'] == 0
        assert len(calls) == 6  # read + three batches + day upsert + count
        assert batch_sizes == [250, 250, 1]
    finally:
        sql_event.remove(database, 'before_cursor_execute', observe)


def test_postgres_conflicts_are_batched_without_overwriting_archive(database):
    original = batch(501)
    with database.begin() as conn:
        sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), original)
        before = [dict(row) for row in conn.execute(text(
            'SELECT * FROM vera_facegate_event ORDER BY event_id,occurred_at')).mappings().all()]
    changed = copy.deepcopy(original)
    for row in changed:
        payload = json.loads(row['payload_json'])
        payload['device_name'] = 'ANH THU UPDATED'
        row['payload_json'] = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        row['payload_sha256'] = hashlib.sha256(row['payload_json'].encode('utf-8')).hexdigest()
    calls, batch_sizes = [], []
    def observe(conn, cursor, statement, params, context, executemany):
        calls.append(statement)
        if params and 'batch' in params:
            batch_sizes.append(len(json.loads(params['batch'])))
    sql_event.listen(database, 'before_cursor_execute', observe)
    try:
        with database.begin() as conn:
            result = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), changed)
        assert result == {'inserted_count': 0, 'already_stored_count': 0,
                          'conflict_count': 501, 'stored_day_count': 501}
        assert len(calls) == 6
        assert batch_sizes == [250, 250, 1]
    finally:
        sql_event.remove(database, 'before_cursor_execute', observe)
    with database.connect() as conn:
        after = [dict(row) for row in conn.execute(text(
            'SELECT * FROM vera_facegate_event ORDER BY event_id,occurred_at')).mappings().all()]
        assert after == before
        assert conn.execute(text('SELECT COUNT(*) FROM vera_facegate_event_conflict')).scalar_one() == 501
        assert conn.execute(text('SELECT SUM(observation_count) FROM vera_facegate_event_conflict')).scalar_one() == 501


def test_postgres_mixed_batch_rollback_keeps_archive_audit_and_day_atomic(database):
    with database.begin() as conn:
        sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), batch())
        before = [dict(row) for row in conn.execute(text(
            'SELECT * FROM vera_facegate_event ORDER BY event_id,occurred_at')).mappings().all()]
        day_before = dict(conn.execute(text('SELECT * FROM vera_facegate_sync_day')).mappings().one())
    changed = batch(251)
    payload = json.loads(changed[0]['payload_json'])
    payload['device_name'] = 'ANH THU UPDATED'
    changed[0]['payload_json'] = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    changed[0]['payload_sha256'] = hashlib.sha256(changed[0]['payload_json'].encode('utf-8')).hexdigest()
    with pytest.raises(RuntimeError, match='synthetic_rollback'):
        with database.begin() as conn:
            result = sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), changed)
            assert result['inserted_count'] == 122 and result['conflict_count'] == 1
            raise RuntimeError('synthetic_rollback')
    with database.connect() as conn:
        after = [dict(row) for row in conn.execute(text(
            'SELECT * FROM vera_facegate_event ORDER BY event_id,occurred_at')).mappings().all()]
        assert after == before
        assert conn.execute(text('SELECT COUNT(*) FROM vera_facegate_event_conflict')).scalar_one() == 0
        assert dict(conn.execute(text('SELECT * FROM vera_facegate_sync_day')).mappings().one()) == day_before


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


def test_missing_reference_stays_blocking_in_postgres_shadow_preview(database):
    seed_preview(database)
    with database.begin() as conn:
        raw = conn.execute(text('SELECT payload_json FROM vera_facegate_event')).scalar_one()
        payload = json.loads(raw)
        payload['registration_ref'] = None
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        conn.execute(text('UPDATE vera_facegate_event SET payload_json=:payload,payload_sha256=:digest'),
                     {'payload': encoded, 'digest': hashlib.sha256(encoded.encode('utf-8')).hexdigest()})
    with database.begin() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        result = fg.preview(conn, DAY, DAY)
    assert 'unresolved_events' in result['blockers']
    assert any(issue['reason'] == 'unmapped_reference' for issue in result['issues'])
    assert result['records'][0]['check_in'] == ''
    assert result['source'] == 'timesoft' and result['attendance_cutover_ready'] is False
    assert result['payroll_and_penalties_written'] is False
    with database.connect() as conn:
        assert conn.execute(text('SELECT payload_json FROM vera_facegate_event')).scalar_one() == encoded


def test_saved_overtime_definition_is_used_by_attendance_and_alerts(database):
    import vera_web_v2_attendance_query_perf as attendance
    import vera_missing_checkin_notifications as alerts
    with database.begin() as conn:
        conn.execute(text("UPDATE employees SET role='locker'"))
        conn.execute(text("INSERT INTO vera_work_shift_definition VALUES ('locker','Ca 1','09:30','17:30'),('locker','Ca 2','17:30','01:30')"))
        conn.execute(text("""INSERT INTO vera_work_schedule(work_date,employee_username,employee_name,department,
            shift_code,start_time,end_time,overtime_shift) VALUES (:day,'Ánh Thử','Nguyễn Ánh Thử','locker','Ca 2','','','TC Ca 1')"""), {'day': DAY})
        mapped = attendance._schedule_map(conn, DAY, DAY)[(DAY, 'anh thu')]
        scheduled = alerts._scheduled_rows(conn, DAY)[0]
        from vera_web_v2_department_attendance import scheduled_assignment
        department = scheduled_assignment(conn, DAY, 'Ánh Thử')
        assert (department['start_time'], department['end_time']) == ('09:30', '01:30')
        assert (mapped['start_time'], mapped['end_time']) == ('09:30', '01:30')
        assert (scheduled['start_time'], scheduled['end_time']) == ('09:30', '01:30')
        rows, issues, _ = fg.adapt_events([event('09:32:05')], MAP,
            [{'username': 'Ánh Thử', 'full_name': 'Nguyễn Ánh Thử', 'role': 'locker'}],
            ADDRESS, DAY, DAY, lambda profile, day: attendance._vera_shift_fields(profile, day, [], mapped))
        assert len(rows) == 1 and not issues
        assert rows[0]['StartWorkTime'] == '09:30'

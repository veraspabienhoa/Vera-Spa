"""Replay the real snapshot imports and canonical reader in fresh processes.

Only the clock, database transport and final financial writer are test doubles;
no attendance reader, projection or startup installer is substituted. Every
fixture is synthetic, and all database calls stay on the checked-out connection.
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 10, 10)
NOW = datetime(2026, 10, 10, 20, 30, tzinfo=timezone(timedelta(hours=7)))
ADDRESS = '192.168.1.26'
REFERENCE = {'file_type': 0, 'file_index': 1, 'file_position': 1420}
EMPLOYEE = 'Synthetic Therapist'


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class DelayedWriteDateTime(FrozenDateTime):
    calls = 0

    @classmethod
    def now(cls, tz=None):
        cls.calls += 1
        now = NOW + timedelta(seconds=301 if cls.calls > 1 else 0)
        return now.astimezone(tz) if tz else now.replace(tzinfo=None)


class Result:
    def __init__(self, rows=(), value=None):
        self.rows = list(rows)
        self.value = value

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalar(self):
        return self.value


class FixtureConnection:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def begin_nested(self):
        assert self.engine.active == 1
        self.engine.savepoints += 1
        yield self

    def execute(self, statement, parameters=None):
        sql = ' '.join(str(statement).split())
        parameters = parameters or {}
        self.engine.queries.append((id(self), sql))
        assert self.engine.active == 1
        assert sql.startswith('SELECT '), 'Projection/switch reads must not write or run DDL'
        if "category='auto_check'" in sql:
            self.engine.switch_reads += 1
            paused = self.engine.scenario == 'paused' or (
                self.engine.scenario == 'pause_before_write' and self.engine.switch_reads > 1)
            return Result(value={'status': 'PAUSED' if paused else 'RUNNING'})
        if "category='devices'" in sql:
            return Result(value={'devices': [{'id': 'facegate-current', 'address': ADDRESS}]})
        if "category='facegate'" in sql:
            return Result(value=self.engine.mappings if parameters['key'].startswith('mapping_') else None)
        if "category='shift'" in sql:
            return Result([{'setting_key': 'shift_definitions', 'value_json': self.engine.definitions}])
        if 'FROM vera_app_setting' in sql:
            return Result()
        if "to_regclass('vera_facegate_event')" in sql:
            return Result(value=True)
        if "to_regclass('vera_facegate_event_conflict')" in sql:
            return Result(value=True)
        if "to_regclass('vera_holiday_leave_period')" in sql:
            return Result(value=None)
        if 'FROM vera_facegate_event_conflict' in sql:
            return Result()
        if 'FROM vera_facegate_event' in sql:
            self.engine.archive_reads += 1
            if self.engine.archive_reads == 3:
                if self.engine.scenario == 'evidence_changed_before_write':
                    self.engine.events.append(self.engine.event(99, '15:00:00', device_name='Unknown Person',
                        registration_ref={'file_type': 0, 'file_index': 0, 'file_position': 9999}))
                    self.engine.syncs[0]['last_observed_count'] += 1
                elif self.engine.scenario == 'pair_changed_before_write':
                    for event in self.engine.events[-2:]:
                        event['occurred_at'] = event['occurred_at'].replace('17:15:', '17:25:')
            return Result(self.engine.events)
        if 'FROM vera_facegate_sync_day' in sql:
            return Result(self.engine.syncs)
        if 'FROM employees' in sql:
            return Result(self.engine.employees)
        if 'FROM vera_work_schedule' in sql or 'FROM leave_records' in sql:
            return Result()
        if 'FROM vera_dataset_cache' in sql:
            self.engine.legacy_reads += 1
            return Result([{'dataset_key': 'timesoft_employee_checkin_20261010_raw',
                            'payload': self.engine.legacy_rows}])
        raise AssertionError(f'Unexpected query in standalone fixture: {sql}')


class FixtureEngine:
    def __init__(self, scenario):
        self.scenario = scenario
        self.active = self.max_active = self.archive_reads = self.legacy_reads = 0
        self.switch_reads = 0
        self.savepoints = 0
        self.queries = []
        self.employees = [{'username': EMPLOYEE, 'full_name': 'Synthetic Full Name',
            'role': 'nhanvien', 'work_shift': 'Ca 1', 'shift_start_date': '2026-09-01',
            'rotation_cycle': 'Cố định (Không đổi)', 'employment_start_date': '', 'payload': {}}]
        self.definitions = [{'Tên ca': 'Ca 1', 'Giờ bắt đầu': '10:00', 'Giờ kết thúc': '23:00',
            'Bộ phận': 'Nhân viên + Leader', 'Áp dụng nghỉ giữa ca': scenario != 'break_disabled',
            'Duration nghỉ giữa ca (phút)': 90}]
        self.mappings = [{'profile_id': 142, 'username': EMPLOYEE, 'employee_code': 'SYN001',
            'registration_ref': REFERENCE, 'confirmed_by': 'admin', 'device_address': ADDRESS}]
        clocks = ['09:59:00', '15:30:00', '15:30:02', '17:15:00', '17:15:03']
        if scenario == 'open_break':
            clocks = clocks[:3]
        elif scenario == 'on_time':
            clocks[-2:] = ['16:59:00', '16:59:03']
        self.events = [self.event(index + 1, clock) for index, clock in enumerate(clocks)]
        if scenario == 'unmapped_evidence':
            self.events.append(self.event(99, '15:00:00', device_name='Unknown Person',
                registration_ref={'file_type': 0, 'file_index': 0, 'file_position': 9999}))
        synced = NOW - timedelta(seconds=30)
        if scenario == 'stale':
            synced = NOW - timedelta(seconds=301)
        elif scenario == 'future':
            synced = NOW + timedelta(seconds=1)
        elif scenario == 'naive':
            synced = synced.replace(tzinfo=None)
        self.syncs = [{'work_date': DAY.isoformat(), 'last_observed_count': len(self.events) +
            int(scenario == 'incomplete'), 'last_synced_at': synced.isoformat()}]
        self.legacy_rows = [{'WorkDateStr': DAY.strftime('%d/%m/%Y'), 'EmployeeName': EMPLOYEE,
            'MachineTimeCheckInStr': DAY.strftime('%d/%m/%Y') + ' ' + clock}
            for clock in ('09:58:00', '15:30:00', '17:06:00')]

    @staticmethod
    def event(event_id, clock, **changes):
        payload = {'device_name': EMPLOYEE, 'registration_ref': REFERENCE,
            'device_address': ADDRESS, 'status_code': '1', 'type_code': '0', **changes}
        return {'event_id': str(event_id), 'occurred_at': f'{DAY}T{clock}+07:00',
                'payload_json': json.dumps(payload)}

    @contextmanager
    def connect(self):
        assert self.active == 0, 'The canonical reader must not acquire a nested connection'
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            yield FixtureConnection(self)
        finally:
            self.active -= 1

    begin = connect


def _exercise_standalone(mode, scenario):
    # This is deliberately the production standalone import order. The broken
    # implementation worked only when an API test installed query_perf first.
    import timesoft_snapshot_job as job
    import vera_facegate_runtime as runtime
    import vera_web_v2_attendance_query_perf as query
    import vera_web_v2_attendance_v42 as attendance
    import vera_web_v2_attendance_break_window as break_window
    from vera_web_v2_break_return_penalty import confirmed_break_return_fact

    assert 'vera_web_v2_api' not in sys.modules
    assert not getattr(attendance, '_attendance_query_perf_release', '')
    assert attendance._records_v42.__name__ == '_records_v42'
    engine = FixtureEngine(scenario)
    original_reader = attendance._records_v42
    original_rules = (attendance._cluster_punches, attendance._pick_break_pair, attendance._break_from_punches)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(job.ts, 'datetime', DelayedWriteDateTime if scenario == 'elapsed_freshness' else FrozenDateTime)
        patch.setattr(runtime, 'datetime', FrozenDateTime)
        rows = job.ts._confirmed_break_return_records(engine, DAY)
        assert attendance._records_v42 is original_reader
        assert original_rules == (attendance._cluster_punches, attendance._pick_break_pair, attendance._break_from_punches)
        assert len(rows) == 1 and rows[0]['employee_name'] == EMPLOYEE
        row = rows[0]
        if mode == 'facegate':
            assert row['evidence_source'] == 'facegate'
            assert row['check_in'] == '09:59:00'
            assert engine.archive_reads == 1 and engine.legacy_reads == 0
            assert row['attendance_preview'] is False
            assert row['payable_minutes_verified'] is False  # Mid-shift evidence remains non-payroll.
        else:
            assert row.get('evidence_source') != 'facegate'
            assert engine.archive_reads == 0 and engine.legacy_reads == 1
            assert row['check_in'].endswith('09:58:00')
        fact = confirmed_break_return_fact(row, DAY)
        blocked = scenario in {'stale', 'future', 'naive', 'incomplete', 'unmapped_evidence',
                               'break_disabled', 'open_break', 'on_time'}
        assert (fact is None) == blocked
        if fact:
            assert fact['late_minutes'] == (15 if mode == 'facegate' else 6)
            assert fact['deadline'].strftime('%H:%M:%S') == '17:00:00'
        if scenario in {'stale', 'future', 'naive', 'incomplete', 'unmapped_evidence'}:
            assert row['attendance_fine_evidence_ready'] is False
        elif mode == 'facegate':
            assert row['attendance_fine_evidence_ready'] is True
        assert engine.max_active == 1 and engine.active == 0

        calls, events = [], set()
        reason = {'name': 'Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút', 'penalty': 100000}
        def save(conn, **kwargs):
            assert engine.active == 1
            assert engine.savepoints > 0 and id(conn) == engine.queries[-1][0]
            expected_return = fact['break_in'] + timedelta(minutes=10 if scenario == 'pair_changed_before_write' else 0)
            assert kwargs['approved_window'] == (fact['deadline'], expected_return)
            assert kwargs['source'] == f'ĐỒNG BỘ {mode.upper()} - NGHỈ GIỮA CA'
            calls.append(kwargs)
            key = (kwargs['work_date'], kwargs['employee'], kwargs['reason_item']['name'])
            if key in events:
                return True, 'SKIP_DUPLICATE'
            events.add(key)
            return True, 'ADDED'
        patch.setattr(job.ts.auto_check, 'save_violation', save)
        patch.setattr(job.ts, '_log', lambda *_args: None)
        catalog = {job.ts.auto_check._norm(reason['name']): reason}
        first = job.ts.process_break_return_penalties(engine, catalog)
        second = job.ts.process_break_return_penalties(engine, catalog)
        if blocked or scenario in {'paused', 'pause_before_write', 'evidence_changed_before_write', 'elapsed_freshness'}:
            assert first['added'] == second['added'] == 0
            assert not calls and not events
            if scenario in {'pause_before_write', 'evidence_changed_before_write', 'elapsed_freshness'}:
                assert first['eligible'] == first['skipped'] == 1
        elif scenario == 'pair_changed_before_write':
            assert first == {'eligible': 1, 'added': 0, 'skipped': 1, 'errors': 0}
            assert second == {'eligible': 1, 'added': 1, 'skipped': 0, 'errors': 0}
            assert len(calls) == len(events) == 1
            assert calls[0]['minutes'] == 25
        else:
            assert first == {'eligible': 1, 'added': 1, 'skipped': 0, 'errors': 0}
            assert second == {'eligible': 1, 'added': 0, 'skipped': 1, 'errors': 0}
            assert len(calls) == 2 and len(events) == 1
        assert first['errors'] == second['errors'] == 0
        assert attendance._records_v42 is original_reader
        row = job.ts._confirmed_break_return_records(engine, DAY)[0]
        # Compare with the same canonical reader after the web startup patches.
        # No API module is imported and no reader is stubbed in either direction.
        query.install()
        break_window.install_attendance_break_window(SimpleNamespace(state=SimpleNamespace(),
            get=lambda _path: lambda function: function))
        with engine.connect() as conn:
            api_rows = attendance._records_v42(conn, DAY, DAY)
        compared = ('employee_name', 'check_in', 'break_out', 'break_in', 'break_return_deadline',
                    'evidence_source', 'attendance_fine_evidence_ready', 'attendance_fine_evidence_reasons')
        assert {key: row.get(key) for key in compared} == {key: api_rows[0].get(key) for key in compared}

    print(json.dumps({'source': mode, 'scenario': scenario, 'ok': True}))


@pytest.mark.parametrize('mode,scenario', [('timesoft', 'fresh')] + [
    ('facegate', scenario) for scenario in ('fresh', 'stale', 'future', 'naive', 'incomplete',
        'unmapped_evidence', 'break_disabled', 'open_break', 'on_time', 'paused', 'pause_before_write',
        'evidence_changed_before_write', 'pair_changed_before_write', 'elapsed_freshness')])
def test_fresh_process_snapshot_reader_and_penalties(tmp_path, mode, scenario):
    policy = tmp_path / 'attendance-source.json'
    if mode == 'facegate':
        policy.write_text(json.dumps({'version': 1, 'source': 'facegate', 'effective_date': DAY.isoformat()}))
    env = {**os.environ, 'VERA_ATTENDANCE_SOURCE_FILE': str(policy),
           'VERA_FACEGATE_DEVICE_ID': 'synthetic-device',
           'PYTHONPATH': os.pathsep.join(filter(None, (str(ROOT), os.environ.get('PYTHONPATH', ''))))}
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), mode, scenario],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1])['ok'] is True


@pytest.mark.parametrize('value,expected', [(None, False), ({}, False),
    ({'status': 'RUNNING'}, False), ({'status': 'paused'}, True), ('{"status":"PAUSED"}', True)])
def test_pause_check_is_read_only_and_preserves_missing_config_default(value, expected):
    import vera_auto_check as auto_check
    queries = []
    class Connection:
        def execute(self, statement):
            queries.append(str(statement).strip())
            return Result(value=value)
    assert auto_check.penalties_paused(Connection()) is expected
    assert len(queries) == 1 and queries[0].startswith('SELECT ')


# Keep the subprocess entrypoint's import order faithful to production. Pytest
# alone imports this existing isolated PostgreSQL fixture for financial replay.
if __name__ != '__main__':
    from test_facegate_attendance_postgres import database


@pytest.mark.parametrize('mode', ['facegate', 'timesoft'])
def test_postgres_standalone_replay_commits_one_event_leave_and_outbox(database, monkeypatch, tmp_path, mode):
    from sqlalchemy import text
    import vera_auto_check as auto_check
    import vera_facegate_runtime as runtime
    import vera_facegate_sync as sync
    import timesoft_sync_job as ts

    fixture = FixtureEngine('fresh')
    policy = tmp_path / 'source.json'
    if mode == 'facegate':
        policy.write_text(json.dumps({'version': 1, 'source': 'facegate', 'effective_date': DAY.isoformat()}))
    monkeypatch.setenv('VERA_ATTENDANCE_SOURCE_FILE', str(policy))
    monkeypatch.setattr(ts, 'datetime', FrozenDateTime)
    monkeypatch.setattr(runtime, 'datetime', FrozenDateTime)
    monkeypatch.setattr(ts, '_log', lambda *_args: None)
    with database.begin() as conn:
        conn.execute(text('DELETE FROM employees'))
        conn.execute(text("""INSERT INTO employees(username,full_name,role,work_shift,shift_start_date,rotation_cycle)
            VALUES (:username,:full_name,:role,:work_shift,:shift_start_date,:rotation_cycle)"""), fixture.employees[0])
        for category, key, value in [('facegate', 'mapping_synthetic-device', fixture.mappings),
                ('shift', 'shift_definitions', fixture.definitions), ('auto_check', 'config', {'status': 'PAUSED'})]:
            conn.execute(text("""INSERT INTO vera_app_setting(category,setting_key,value_json)
                VALUES (:category,:key,CAST(:value AS jsonb)) ON CONFLICT(category,setting_key)
                DO UPDATE SET value_json=EXCLUDED.value_json"""),
                {'category': category, 'key': key, 'value': json.dumps(value)})
        raw = [{'event_id': int(item['event_id']), 'occurred_at': item['occurred_at'],
                **json.loads(item['payload_json'])} for item in fixture.events]
        batch = sync.prepare_batch({'source': 'facegate_control_log', 'total_count': len(raw),
            'truncated': False, 'records': raw}, DAY.isoformat(), ADDRESS)
        sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), batch)
        conn.execute(text('UPDATE vera_facegate_sync_day SET last_synced_at=:synced'),
            {'synced': (NOW - timedelta(seconds=30)).isoformat()})
        conn.execute(text('INSERT INTO vera_dataset_cache VALUES (:key,CAST(:payload AS jsonb))'),
            {'key': 'timesoft_employee_checkin_20261010_raw', 'payload': json.dumps(fixture.legacy_rows)})
        conn.execute(text("""CREATE TABLE leave_records (
            source_sheet_id text,source_row bigint,leave_date date,employee_name text,
            leave_reason text,leave_type text,detail text,calculated_days numeric,
            accumulated_leave numeric,penalty numeric,update_date text,update_time text,
            updated_by text,weekday_label text,payload jsonb,record_uid text,
            created_at timestamptz,updated_at timestamptz)"""))
        before_archive = list(conn.execute(text('SELECT * FROM vera_facegate_event ORDER BY event_id')))
        before_cache = list(conn.execute(text('SELECT * FROM vera_dataset_cache ORDER BY dataset_key')))

    reason = {'name': 'Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút', 'penalty': 100000}
    catalog = {auto_check._norm(reason['name']): reason}
    assert ts.process_break_return_penalties(database, catalog) == {
        'eligible': 0, 'added': 0, 'skipped': 0, 'errors': 0}
    with database.begin() as conn:
        # A paused direct call never reaches the schema-mutating writer.
        assert conn.execute(text("SELECT to_regclass('vera_auto_check_event')")).scalar() is None
        conn.execute(text("""UPDATE vera_app_setting SET value_json='{"status":"RUNNING"}'::jsonb
            WHERE category='auto_check' AND setting_key='config'"""))
    assert ts.process_break_return_penalties(database, catalog) == {
        'eligible': 1, 'added': 1, 'skipped': 0, 'errors': 0}
    assert ts.process_break_return_penalties(database, catalog) == {
        'eligible': 1, 'added': 0, 'skipped': 1, 'errors': 0}
    with database.connect() as conn:
        leaves = conn.execute(text('SELECT * FROM leave_records')).mappings().all()
        events = conn.execute(text('SELECT * FROM vera_auto_check_event')).mappings().all()
        assert len(leaves) == len(events) == 1
        assert float(leaves[0]['penalty']) == 100000
        assert leaves[0]['record_uid'] == events[0]['leave_record_uid']
        assert events[0]['status'] == 'added' and events[0]['employee_notified_at'] is None
        assert int(events[0]['minutes']) == (15 if mode == 'facegate' else 6)
        assert events[0]['source'] == f'ĐỒNG BỘ {mode.upper()} - NGHỈ GIỮA CA'
        assert list(conn.execute(text('SELECT * FROM vera_facegate_event ORDER BY event_id'))) == before_archive
        assert list(conn.execute(text('SELECT * FROM vera_dataset_cache ORDER BY dataset_key'))) == before_cache

    # A partially written candidate rolls back alone; another candidate still
    # reaches duplicate detection in the same caller-owned transaction.
    failed_employee = 'AAA Synthetic Failure'
    failed_reference = {**REFERENCE, 'file_position': 2420}
    with database.begin() as conn:
        conn.execute(text("""INSERT INTO employees(username,full_name,role,work_shift,shift_start_date,rotation_cycle)
            SELECT :username,:username,role,work_shift,shift_start_date,rotation_cycle FROM employees LIMIT 1"""),
            {'username': failed_employee})
        mappings = fixture.mappings + [{**fixture.mappings[0], 'username': failed_employee,
            'profile_id': 242, 'registration_ref': failed_reference}]
        conn.execute(text("""UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb)
            WHERE category='facegate' AND setting_key='mapping_synthetic-device'"""), {'value': json.dumps(mappings)})
        raw += [{**item, 'event_id': item['event_id'] + 100, 'device_name': failed_employee,
                 'registration_ref': failed_reference} for item in list(raw)]
        sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), sync.prepare_batch({
            'source': 'facegate_control_log', 'total_count': len(raw), 'truncated': False,
            'records': raw}, DAY.isoformat(), ADDRESS))
        conn.execute(text('UPDATE vera_facegate_sync_day SET last_synced_at=:synced'),
            {'synced': (NOW - timedelta(seconds=30)).isoformat()})
        legacy = fixture.legacy_rows + [{**row, 'EmployeeName': failed_employee} for row in fixture.legacy_rows]
        conn.execute(text('UPDATE vera_dataset_cache SET payload=CAST(:payload AS jsonb)'),
            {'payload': json.dumps(legacy)})
    original_save = auto_check.save_violation
    def record_then_fail(conn, **kwargs):
        result = original_save(conn, **kwargs)
        if kwargs['employee'] == failed_employee:
            raise RuntimeError('Synthetic error after financial writes')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(auto_check, 'save_violation', record_then_fail)
        assert ts.process_break_return_penalties(database, catalog) == {
            'eligible': 2, 'added': 0, 'skipped': 1, 'errors': 1}
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM leave_records')).scalar() == 1
        assert conn.execute(text('SELECT COUNT(*) FROM vera_auto_check_event')).scalar() == 1

    original_begin = database.begin
    @contextmanager
    def fail_before_commit():
        with original_begin() as conn:
            yield conn
            raise RuntimeError('Synthetic outer transaction failure')
    logs = []
    with monkeypatch.context() as patch:
        patch.setattr(database, 'begin', fail_before_commit)
        patch.setattr(ts, '_log', logs.append)
        assert ts.process_break_return_penalties(database, catalog) == {
            'eligible': 2, 'added': 0, 'skipped': 1, 'errors': 1}
    assert not any('DIRECT BREAK RETURN ADDED:' in message for message in logs)
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM leave_records')).scalar() == 1
        assert conn.execute(text('SELECT COUNT(*) FROM vera_auto_check_event')).scalar() == 1


if __name__ == '__main__':
    _exercise_standalone(*sys.argv[1:])

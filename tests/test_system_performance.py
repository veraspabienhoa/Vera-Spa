"""Performance regressions assert work bounds and isolation, not wall-clock speed."""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

import vera_request_metrics as metrics
import vera_web_v2_department_payroll as payroll
import vera_live_tour_lists as queries
from test_notification_schema_locking import database


def test_request_metrics_include_thread_sql_without_private_labels(monkeypatch):
    db = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    seen = []
    monkeypatch.setattr(metrics, '_record', lambda *args: seen.append(args))
    app = FastAPI()
    app.add_middleware(metrics.RequestMetricsMiddleware)

    @app.get('/items/{item_id}')
    def item(item_id: str):
        with db.connect() as conn:
            conn.execute(text('SELECT :secret'), {'secret': item_id})
        return {'ok': True}

    with TestClient(app) as client:
        first = client.get('/items/private-name?token=never-log')
        second = client.get('/items/other')
    assert first.headers['x-request-id'] != second.headers['x-request-id']
    assert len(seen) == 2
    for route, method, status, measure in seen:
        assert (route, method, status) == ('/items/{item_id}', 'GET', 200)
        assert measure['sql_count'] == 1 and measure['sql_ms'] >= 0
        assert measure['total_ms'] >= measure['sql_ms']
        assert measure['bytes'] == len(first.content)
    assert 'private-name' not in str(seen) and 'never-log' not in str(seen)
    assert metrics._request.get() is None
    db.dispose()


@pytest.mark.parametrize('source,field', [('schedule', 'employee_username'), ('attendance', 'employee_name')])
def test_grouped_payroll_matches_full_scans_and_keeps_historical_department(source, field):
    cfg = payroll.DEFAULT_CONFIG['letan']
    names = ['HẢI MY', '  hai my ', 'Another', '']
    records = [dict(employee_username=name, employee_name=name, work_date=date(2026, 9, 2),
                    date='02/09/2026', shift_code='Ca 2', shift='Ca 2',
                    schedule_department='locker', overtime_shift='TC Ca 1',
                    check_in='17:00', check_out='01:00') for name in names]
    records += [dict(records[0], shift_code='Nghỉ'), dict(records[0], date='bad', work_date=None),
                dict(records[2], evidence_source='facegate', attendance_pending=True)]
    definitions = {'locker': {'Ca 1': {'start': '09:00', 'end': '17:00'},
                              'Ca 2': {'start': '17:00', 'end': '01:00'}}}
    grouped = payroll._group_payroll_records(records, field, queries.normalize)
    def totals(rows, name):
        if source == 'schedule':
            return payroll._schedule_totals(rows, name, 'letan', definitions, cfg, queries.normalize)
        return payroll._attendance_totals(rows, name, queries.normalize, cfg)
    for name in names + ['missing']:
        assert totals(records, name) == totals(grouped.get(queries.normalize(name), []), name)


def test_combined_calculation_reads_period_inputs_once(monkeypatch):
    calls = []
    class Connection:
        def execute(self, statement, params=None):
            sql = str(statement)
            calls.append(sql)
            assert 'FROM vera_work_schedule' in sql or 'FROM vera_work_shift_definition' in sql
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))
    monkeypatch.setattr(payroll.work_schedule, '_ensure_schema', lambda conn: None)
    monkeypatch.setattr(payroll, '_probation_policies', lambda *args, **kwargs: {})
    monkeypatch.setattr(payroll, '_combo_sale_counts', lambda *args: {})
    config_calls, penalty_calls = [], []
    monkeypatch.setattr(payroll, '_employee_config_map', lambda conn: config_calls.append(1) or {})
    monkeypatch.setattr(payroll, '_penalty_maps', lambda *args: penalty_calls.append(1) or ({}, {}))
    monkeypatch.setattr(payroll, '_employees', lambda conn, dep: [{'username': dep, 'full_name': dep}])
    monkeypatch.setattr(payroll, '_settings', lambda conn, dep: {
        'department_label': dep, 'config': payroll.DEFAULT_CONFIG.get(dep, payroll.DEFAULT_CONFIG['support'])})
    monkeypatch.setattr(payroll.hr, 'admin_departments', lambda conn: {'letan': {}, 'locker': {}, 'support': {}})
    monkeypatch.setattr(payroll.payroll, '_setting', lambda *args: [])
    result = payroll._combined_calculation(Connection(), '2026-09', queries.normalize, 'schedule')
    assert len(result['rows']) == 3
    assert len(calls) == 2 and config_calls == [1] and penalty_calls == [1]


@pytest.mark.parametrize('component', ['schedule', 'booking', 'training', 'identity'])
def test_ready_schema_has_no_ddl_or_lock_and_rollback_is_not_cached(database, component):
    from vera_web_v2_work_schedule import _ensure_schema
    from vera_online_booking import ensure_schema
    from vera_web_v2_training import _schema
    from vera_web_v2_staff_security import _ensure_identity_table
    ensure = {'schedule': _ensure_schema, 'booking': ensure_schema, 'training': _schema, 'identity': _ensure_identity_table}[component]
    with database.connect() as conn:
        ensure(conn)
        conn.rollback()
        assert conn.execute(text("SELECT to_regclass('vera_read_path_schema')")).scalar() is None
    with database.begin() as conn:
        ensure(conn)
    statements = []
    with database.begin() as first:
        event.listen(first, 'before_cursor_execute', lambda conn, cursor, sql, *args: statements.append(sql))
        ensure(first)
        with database.begin() as second:
            second.execute(text("SET LOCAL lock_timeout='300ms'"))
            ensure(second)
    assert len(statements) == 2
    assert all(sql.lstrip().startswith('SELECT') and 'pg_advisory' not in sql for sql in statements)


def test_revenue_token_tracks_commits_all_writers_but_not_rollback(database):
    import vera_revenue_revision as revision
    with database.begin() as conn:
        for table in revision.SOURCES:
            conn.execute(text(f'CREATE TABLE {table}(id int PRIMARY KEY,category text)'))
        revision.install(conn)
    with database.connect() as reader:
        before = revision.read(reader)
        with database.connect() as writer:
            writer.execute(text("INSERT INTO vera_live_tour_report VALUES(1,'test')"))
            assert revision.read(reader) == before  # Uncommitted counter must be invisible.
            writer.commit()
            after = revision.read(reader)
            assert after != before
            writer.execute(text("UPDATE vera_live_tour_report SET category='rollback'"))
            writer.rollback()
            assert revision.read(reader) == after
        for table in revision.SOURCES:
            with database.begin() as conn:
                conn.execute(text(f"INSERT INTO {table} VALUES(2,'revenue')"))
            updated = revision.read(reader)
            assert updated != after
            after = updated
        with database.begin() as conn:
            conn.execute(text("INSERT INTO vera_app_setting VALUES(3,'unrelated')"))
        assert revision.read(reader) == after
        with database.begin() as conn:
            conn.execute(text('TRUNCATE vera_purchase_entry'))
        assert revision.read(reader) != after


def test_import_does_not_block_an_unrelated_request(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from uuid import uuid4
    import vera_web_v2_purchases as purchases
    entered, release = Event(), Event()
    def parse(content):
        entered.set()
        assert release.wait(3), "Excel parsing blocked the application's event loop"
        raise ValueError("Synthetic invalid workbook")
    monkeypatch.setattr(purchases.store, 'parse_workbook', parse)
    app = FastAPI()
    purchases.install_purchase_routes(app, engine_instance=lambda: pytest.fail('Invalid input must not reach DB'),
        current_identity=lambda: SimpleNamespace(role='admin'), require_feature=lambda *args: None,
        feature_allowed=lambda *args: True)
    @app.get('/unrelated')
    async def unrelated():
        release.set()
        return {'ok': True}
    with TestClient(app) as client, ThreadPoolExecutor(1) as pool:
        pending = pool.submit(client.post, f'/v2/purchases/import?request_id={uuid4()}', content=b'synthetic')
        assert entered.wait(2)
        assert client.get('/unrelated').status_code == 200
        assert pending.result(timeout=3).status_code == 400


def test_contract_export_batches_metadata_and_releases_connection_before_pdf(monkeypatch):
    from contextlib import contextmanager
    import vera_web_v2_contracts as contracts
    from test_notification_routing import Identity
    statements, active, bulk = [], [0], [True]
    class Engine:
        @contextmanager
        def begin(self):
            active[0] += 1
            try:
                yield self
            finally:
                active[0] -= 1
        def execute(self, statement, params):
            sql = str(statement)
            statements.append(sql)
            assert 'content' not in sql and 'UPDATE' not in sql
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [
                {'employee_username': name, 'side': 'front', 'ocr_payload': {
                    'permanent_address': 'Synthetic address', 'place_of_origin': 'Synthetic place'}}
                for name in params['usernames']]))
    monkeypatch.setattr(contracts, '_ensure_identity_table', lambda conn: None)
    monkeypatch.setattr(contracts, '_eligible_employee_rows', lambda *args: [
        {'username': name, 'full_name': name, 'birth_date': '2000-01-02', 'role': 'letan',
         'payload': {'Số CCCD': '000000000000', 'Ngày cấp CCCD': '2025-01-01', 'Nơi cấp CCCD': 'Synthetic'}}
        for name in ['one', 'two']])
    monkeypatch.setattr(contracts, '_settings', lambda *args: ({}, 0))
    def pdf(employees, contract_type):
        assert active[0] == 0 and len(employees) == 2
        return b'%PDF-synthetic'
    monkeypatch.setattr(contracts, '_merge_contract_pdfs', pdf)
    app = FastAPI()
    contracts.install_contract_1_routes(app, engine_instance=Engine,
        current_identity=lambda: Identity(employee_username='one'), require_feature=lambda *args: None,
        feature_allowed=lambda conn, ident, feature: bulk[0] if feature == 'contract_1_export_bulk' else True,
        norm=lambda value: str(value or '').lower(), identity_type=Identity)
    client = TestClient(app)
    body = {'contract_type': 'letan', 'scope': 'selected', 'usernames': ['one', 'two']}
    result = client.post('/v2/contracts/1/export.pdf', json=body)
    assert result.status_code == 200, result.text
    assert len(statements) == 1 and result.headers['x-contract-count'] == '2'
    bulk[0] = False
    assert client.post('/v2/contracts/1/export.pdf', json=body).status_code == 403
    assert len(statements) == 1 and active[0] == 0

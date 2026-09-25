"""Exercise production route, transactional invalidation and cache across workers."""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text

from vera_leave_month_schema import migrate
from vera_postgres_job_queue import ensure_schema_conn
from vera_web_v2_leave_month import MonthReader, install_month_api, month_bounds, revision


@pytest.fixture
def database():
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Real PostgreSQL required')
    schema = 'leave_month_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    try:
        with engine.begin() as conn:
            conn.execute(text('''CREATE TABLE leave_records (
                record_uid text PRIMARY KEY, leave_date date, weekday_label text,
                employee_name text, leave_reason text, leave_type text, detail text,
                penalty numeric, updated_by text, updated_at timestamptz DEFAULT now())'''))
            ensure_schema_conn(conn)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def insert(conn, uid, day, penalty=7.5):
    conn.execute(text('''INSERT INTO leave_records(record_uid,leave_date,employee_name,penalty)
        VALUES(:uid,:day,'Synthetic',:penalty)'''), {'uid': uid, 'day': day, 'penalty': penalty})


def test_snapshot_is_exact_month_and_cache_changes_across_workers(database):
    migrate(database)
    migrate(database)  # Repeat deployment must be safe.
    with database.begin() as conn:
        for uid, day in [('before','2026-08-31'),('first','2026-09-01'),('last','2026-09-30'),('after','2026-10-01')]:
            insert(conn, uid, day)
    first, other = MonthReader(lambda: database), MonthReader(lambda: database)
    calls = []
    def observe(conn, cursor, statement, params, context, executemany):
        if 'SELECT record_uid,leave_date' in statement:
            calls.append(statement)
    event.listen(database, 'before_cursor_execute', observe)
    scope = ('synthetic-admin', True)
    try:
        a = first.read('2026-09', scope)
        b = other.read('2026-09', scope)
        assert [r['record_uid'] for r in a['records']] == ['first','last']
        a['records'][0]['penalty'] = 999
        assert first.read('2026-09', scope)['records'][0]['penalty'] == 7.5
        assert len(calls) == 2
        with database.begin() as conn:
            conn.execute(text("UPDATE leave_records SET penalty=18.5 WHERE record_uid='first'"))
        assert other.read('2026-09', scope)['records'][0]['penalty'] == 18.5
        assert first.read('2026-09', scope)['revision'] > b['revision']
        assert len(calls) == 4
        with pytest.raises(RuntimeError):
            with database.begin() as conn:
                conn.execute(text("DELETE FROM leave_records WHERE record_uid='first'"))
                raise RuntimeError('rollback')
        assert len(first.read('2026-09', scope)['records']) == 2
        assert len(calls) == 4
        with database.begin() as conn:
            conn.execute(text("UPDATE leave_records SET leave_date='2026-10-02' WHERE record_uid='first'"))
        assert len(first.read('2026-09', scope)['records']) == 1
        assert len(other.read('2026-10', scope)['records']) == 2
        with database.begin() as conn:
            conn.execute(text('TRUNCATE leave_records'))
        assert first.read('2026-09', scope)['records'] == []
        assert other.read('2026-10', scope)['records'] == []
    finally:
        event.remove(database, 'before_cursor_execute', observe)


def test_bulk_statements_bump_once_and_delete_invalidates(database):
    migrate(database)
    start, _ = month_bounds('2026-09')
    with database.begin() as conn:
        conn.execute(text("INSERT INTO leave_records(record_uid,leave_date) SELECT 'row-'||n,'2026-09-15'::date FROM generate_series(1,100) n"))
        assert revision(conn, start) == 1
    reader = MonthReader(lambda: database)
    assert len(reader.read('2026-09', ())['records']) == 100
    with database.begin() as conn:
        conn.execute(text('DELETE FROM leave_records'))
        assert revision(conn, start) == 2
    assert reader.read('2026-09', ())['records'] == []


def test_route_checks_current_permissions_even_on_cache_hits(database):
    migrate(database)
    with database.begin() as conn:
        insert(conn, 'a', '2026-09-10')
        insert(conn, 'b', '2026-09-11')
    allowed = {'leave': True, 'penalty': True}
    identity = SimpleNamespace(employee_username='synthetic', role='nhanvien')
    def require(conn, ident, feature):
        if not allowed['leave']:
            raise HTTPException(403, 'revoked')
    app = FastAPI()
    install_month_api(app, engine_instance=lambda: database, current_identity=lambda: identity,
        require_feature=require, feature_allowed=lambda *args: allowed['penalty'])
    client = TestClient(app)
    url = '/v2/leave/month-records?month=2026-09&start=2026-09-10&end=2026-09-10'
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    assert len(response.json()['records']) == 1
    assert response.json()['records'][0]['penalty'] == 7.5
    allowed['penalty'] = False
    assert 'penalty' not in client.get(url).json()['records'][0]
    assert 'penalty' not in client.get(url + '&fresh=true').json()['records'][0]
    allowed['leave'] = False
    assert client.get(url).status_code == 403
    assert client.get('/v2/leave/month-records?month=2026-09&end=2026-10-01').status_code == 400
    assert client.get('/v2/leave/month-records?month=9999-12').status_code == 400


def test_migration_pending_uses_uncached_month_reads(database):
    reader = MonthReader(lambda: database)
    assert reader.read('2026-09', ())['revision'] is None
    with database.begin() as conn:
        insert(conn, 'a', '2026-09-10')
    assert len(reader.read('2026-09', ())['records']) == 1
    assert not reader.cache._entries
    migrate(database)
    assert reader.read('2026-09', ())['revision'] == 0
    assert len(reader.cache._entries) == 1


def test_uncommitted_changes_never_poison_cache(database):
    migrate(database)
    reader = MonthReader(lambda: database)
    with database.begin() as writer:
        insert(writer, 'a', '2026-09-10')
        assert reader.read('2026-09', ())['records'] == []
    assert len(reader.read('2026-09', ())['records']) == 1

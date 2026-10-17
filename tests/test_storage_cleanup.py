from datetime import date
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

import vera_storage_cleanup as cleanup
from vera_web_v2_storage import install_storage_routes

START, END = date(2026, 10, 1), date(2026, 10, 31)


def test_scope_validation_and_undated_rows():
    for args in [('bad', START, END), ('range', None, END), ('range', END, START)]:
        with pytest.raises(HTTPException):
            cleanup.validate_scope(*args)
    cleanup.validate_scope('all_time', None, None)
    assert cleanup.matches({}, 'payroll', 'all_time', None, None)
    assert not cleanup.matches({}, 'payroll', 'range', START, END)
    assert cleanup.matches({'Đến ngày': '31-10-2026'}, 'payroll', 'range', START, END)
    assert not cleanup.matches({'Đến ngày': '01-11-2026'}, 'payroll', 'range', START, END)
    with pytest.raises(HTTPException):
        cleanup.selected('employees; DROP TABLE employees')


@pytest.fixture
def database():
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Requires isolated PostgreSQL')
    schema = 'storage_test_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    with engine.begin() as conn:
        for sql in [
            'CREATE TABLE leave_records(id int PRIMARY KEY,leave_date date,note text)',
            'CREATE TABLE payroll_history_rows(id int PRIMARY KEY,period_end date,period_start date,payload jsonb)',
            'CREATE TABLE vera_facegate_event(id int PRIMARY KEY,work_date text)',
            'CREATE TABLE vera_mobile_station_event(id int PRIMARY KEY,occurred_at timestamptz)',
            'CREATE TABLE vera_purchase_entry(id int PRIMARY KEY,purchase_date date)',
            'CREATE TABLE vera_revenue_entry(id int PRIMARY KEY,transaction_date date)',
            'CREATE TABLE vera_dataset_cache(dataset_key text PRIMARY KEY,payload jsonb,row_count int,checksum text,source_version text,updated_at timestamptz)',
            'CREATE TABLE employees(username text)',
            'CREATE TABLE vera_sync_event(dataset_key text,event_type text,detail text,created_at timestamptz)',
        ]:
            conn.execute(text(sql))
        conn.execute(text("INSERT INTO employees VALUES('admin')"))
        conn.execute(text("INSERT INTO leave_records VALUES(1,'2026-10-01','old'),(2,'2026-11-01','keep')"))
        conn.execute(text("INSERT INTO payroll_history_rows VALUES(1,'2026-10-31',NULL,'{}'),(2,NULL,NULL,'{}')"))
        conn.execute(text("INSERT INTO vera_facegate_event VALUES(1,'2026-10-31'),(2,'2026-11-01')"))
        conn.execute(text("INSERT INTO vera_mobile_station_event VALUES(1,'2026-09-30 17:00+00'),(2,'2026-10-31 17:00+00')"))
        conn.execute(text("INSERT INTO vera_purchase_entry VALUES(1,'2026-10-31')"))
        conn.execute(text("INSERT INTO vera_revenue_entry VALUES(1,'2026-10-31')"))
        for key, payload in [('payroll_history', [{'Đến ngày': '31-10-2026'}, {}]),
                             ('timesoft_employee_checkin_today', [{'WorkDateStr': '2026-10-31'}, {}]),
                             ('employee_directory', [{'name': 'keep'}])]:
            conn.execute(text('INSERT INTO vera_dataset_cache(dataset_key,payload) VALUES(:key,CAST(:payload AS jsonb))'),
                         {'key': key, 'payload': json.dumps(payload)})
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
    admin.dispose()


def preview(engine, group='all', scope='range'):
    start, end = (START, END) if scope == 'range' else (None, None)
    with engine.connect() as conn:
        return cleanup.snapshot(conn, group, scope, start, end)


def remove(engine, before):
    with engine.begin() as conn:
        return cleanup.delete_checked(conn, before['dataset'], before['scope'], before['start'], before['end'], before['total'], before['fingerprint'])


def test_range_all_groups_preserves_outside_dates_and_accounts(database):
    before = preview(database)
    assert before['counts'] == {'attendance': 3, 'leave': 1, 'payroll': 2, 'purchases': 1, 'revenue': 1}
    remove(database, before)
    assert preview(database)['total'] == 0
    remaining = preview(database, scope='all_time')
    assert remaining['total'] == 6
    with database.connect() as conn:
        assert conn.execute(text('SELECT username FROM employees')).scalar_one() == 'admin'
        assert conn.execute(text("SELECT payload FROM vera_dataset_cache WHERE dataset_key='employee_directory'")).scalar_one() == [{'name': 'keep'}]


def test_all_time_includes_undated_and_all_copies(database):
    remove(database, preview(database, 'payroll', 'all_time'))
    assert preview(database, 'payroll', 'all_time')['total'] == 0
    assert preview(database, 'leave')['total'] == 1
    remove(database, preview(database, scope='all_time'))
    assert preview(database, scope='all_time')['total'] == 0


def test_equal_count_changed_content_rejected(database):
    before = preview(database)
    with database.begin() as conn:
        conn.execute(text("UPDATE leave_records SET note='changed' WHERE id=1"))
    with pytest.raises(HTTPException) as error:
        remove(database, before)
    assert error.value.status_code == 409
    assert preview(database)['total'] == before['total']


def test_failure_rolls_back_all_groups(database):
    before = preview(database)
    with database.begin() as conn:
        conn.execute(text("CREATE FUNCTION block_delete() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test failure'; END $$"))
        conn.execute(text('CREATE TRIGGER block_revenue BEFORE DELETE ON vera_revenue_entry FOR EACH ROW EXECUTE FUNCTION block_delete()'))
    with pytest.raises(Exception, match='test failure'):
        remove(database, before)
    assert preview(database)['fingerprint'] == before['fingerprint']


def client(engine, role):
    app = FastAPI()
    install_storage_routes(app, engine_instance=lambda: engine,
        current_identity=lambda: SimpleNamespace(role=role, employee_username='tester'),
        require_feature=lambda *args: None, delete_leave_uids=lambda *args: None,
        identity_type=SimpleNamespace)
    return TestClient(app)


def test_api_permissions_confirmation_and_audit(database):
    url = '/v2/storage/cleanup/preview?dataset=all&scope=all_time'
    assert client(database, 'letan').get(url).status_code == 403
    admin = client(database, 'admin')
    before = admin.get(url).json()
    body = {k: before[k] for k in ('dataset','scope','start','end','fingerprint')}
    body.update(expected_count=before['total'], confirmation='wrong')
    assert admin.request('DELETE', '/v2/storage/cleanup', json=body).status_code == 400
    body['confirmation'] = 'XÓA DỮ LIỆU'
    assert client(database, 'letan').request('DELETE', '/v2/storage/cleanup', json=body).status_code == 403
    assert admin.request('DELETE', '/v2/storage/cleanup', json=body).status_code == 200
    with database.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_sync_event')).scalar_one() == 1

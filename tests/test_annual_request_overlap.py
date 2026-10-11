"""Bounded, read-only overlap checks use the chosen application's date range."""
import json
from datetime import date
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import vera_web_v2_long_leave_admin as leave
import vera_postgres_phase14 as phase14
from test_revenue_auto_postgres import database
from test_live_tour_backend import RouteIdentity


@pytest.mark.parametrize('date_storage', ['canonical_text', 'date'])
def test_annual_request_overlap_deduplicates_people_and_checks_future_request(database, date_storage):
    if date_storage == 'canonical_text':
        phase14._ensure_schema(SimpleNamespace(is_enabled=lambda: True, get_engine=lambda: database))
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE employees(username text PRIMARY KEY, full_name text, role text, payload jsonb)'))
        if date_storage == 'date':
            conn.execute(text('''CREATE TABLE vera_phase14_record(logical_id text PRIMARY KEY,dataset text,
            employee_key text,record_type text,record_status text,date_from date,date_to date,payload jsonb,
            source_row int,revision bigint DEFAULT 1,updated_at timestamptz DEFAULT NOW())'''))
        for name,status in [('applicant','active'),('approved','active'),('pending','active'),('inactive','inactive')]:
            conn.execute(text('INSERT INTO employees VALUES (:name,:name,\'nhanvien\',CAST(:payload AS jsonb))'),
                         {'name':name,'payload':json.dumps({'employment_status':status})})
        def record(key,employee,start,end,status='Đã duyệt',**extra):
            if date_storage == 'canonical_text':
                start = date.fromisoformat(start).strftime('%d/%m/%Y')
                end = date.fromisoformat(end).strftime('%d/%m/%Y')
            payload={'Tên nhân viên':employee,**extra}
            conn.execute(text('''INSERT INTO vera_phase14_record
                (logical_id,dataset,employee_key,record_type,record_status,date_from,date_to,payload)
                VALUES (:id,:dataset,:employee,:kind,:status,:start,:end,CAST(:payload AS jsonb))'''),
                {'id':'long:'+key,'dataset':leave.LONG_LEAVE_DATASET,'employee':employee,'kind':leave.REQUEST_TYPE_ANNUAL,
                 'status':status,'start':start,'end':end,'payload':json.dumps(payload)})
        record('target','applicant','2026-11-20','2026-11-26','Chờ duyệt')
        record('same-person','applicant','2026-11-20','2026-11-26')
        record('approved-a','approved','2026-11-19','2026-11-23',**{'Ngày quay lại làm việc':'22/11/2026'})
        record('duplicate-person','approved','2026-11-20','2026-11-21','Chờ duyệt')
        record('pending-b','pending','2026-11-21','2026-11-30','Chờ duyệt')
        record('inactive','inactive','2026-11-20','2026-11-26')
        record('rejected','pending','2026-11-20','2026-11-26','Không duyệt')
        record('outside','approved','2026-12-01','2026-12-03')
    with database.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        target=leave._request_row(conn,'target')
        result=leave._request_overlap(conn,target)
        assert result['employee_count']==2 and result['peak_with_applicant']==3
        assert len(result['days'])==7
        assert result['start']=='2026-11-20' and result['end']=='2026-11-26'
        assert [row['other_count'] for row in result['days']]==[1,2,1,1,1,1,1]
        assert result['days'][0]['pending_count']==0
        assert result['days'][1]['approved_count']==result['days'][1]['pending_count']==1
        assert {row['id'] for row in result['requests']}=={'approved-a','duplicate-person','pending-b'}
    app=FastAPI()
    identity=SimpleNamespace(role='admin',employee_username='admin')
    def forbidden(*args,**kwargs):
        raise AssertionError('A preview must never write or use worksheet synchronization')
    leave.install_long_leave_admin_routes(app,engine_instance=lambda:database,current_identity=lambda:identity,
        identity_type=RouteIdentity,norm=str,google_client=forbidden,leave_sheet_id='test',vn_tz=ZoneInfo('Asia/Ho_Chi_Minh'),
        validate_and_prepare=forbidden,leave_create_type=forbidden,sheet_row_for_record=forbidden,insert_record=forbidden)
    client=TestClient(app)
    response=client.get('/v2/long-leave/admin/requests/target/overlap')
    assert response.status_code==200,response.text
    assert response.json()['days']==result['days']
    assert client.get('/v2/long-leave/admin/requests/missing/overlap').status_code==404
    identity.role='letan'
    assert client.get('/v2/long-leave/admin/requests/target/overlap').status_code==403


@pytest.fixture
def canonical_client(database):
    phase14._ensure_schema(SimpleNamespace(is_enabled=lambda: True, get_engine=lambda: database))
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE employees(username text PRIMARY KEY, full_name text, role text, payload jsonb)'))
        for name in ('applicant', 'other'):
            conn.execute(text("INSERT INTO employees VALUES (:name,:name,'nhanvien','{}')"), {'name': name})

    def record(key, start, end, employee='other', **payload):
        with database.begin() as conn:
            conn.execute(text('''INSERT INTO vera_phase14_record
                (dataset,logical_id,employee_key,record_type,record_status,date_from,date_to,payload)
                VALUES (:dataset,:id,:employee,:kind,'Chờ duyệt',:start,:end,CAST(:payload AS jsonb))'''),
                {'dataset': leave.LONG_LEAVE_DATASET, 'id': 'long:' + key, 'employee': employee,
                 'kind': leave.REQUEST_TYPE_ANNUAL, 'start': start, 'end': end,
                 'payload': json.dumps({'Tên nhân viên': employee, **payload})})

    identity = SimpleNamespace(role='admin', employee_username='admin')
    def forbidden(*args, **kwargs):
        raise AssertionError('Overlap checks must not write or synchronize business records')
    app = FastAPI()
    leave.install_long_leave_admin_routes(app, engine_instance=lambda: database, current_identity=lambda: identity,
        identity_type=RouteIdentity, norm=str, google_client=forbidden, leave_sheet_id='test', vn_tz=ZoneInfo('Asia/Ho_Chi_Minh'),
        validate_and_prepare=forbidden, leave_create_type=forbidden, sheet_row_for_record=forbidden, insert_record=forbidden)
    return TestClient(app), identity, record


def test_canonical_text_formats_month_boundaries_and_malformed_rows(canonical_client, database):
    client, _, record = canonical_client
    record('target', '  ', '', 'applicant', **{'Từ ngày': '30/11/2026', 'Đến ngày': '03/12/2026'})
    record('slash', '30/11/2026', '01/12/2026')
    record('dash', '1-12-2026', '2-12-2026')
    record('iso', '2026-12-2', '2026-12-3')
    record('fallback', '\t\n ', '\u00a0', **{'Từ ngày': '\n03/12/2026', 'Đến ngày': '03/12/2026\t'})
    record('whitespace', '\t2026-12-02\n', '\u20072026-12-03\u3000')
    record('ambiguous-day-first', '01/12/2026', '02/12/2026')
    record('month-before', '30/10/2026', '03/11/2026')
    record('next-year', '30/11/2027', '03/12/2027')
    record('malformed', 'not-a-date', '03/12/2026')
    record('impossible', '31/11/2026', '03/12/2026')
    record('empty', '', '')
    record('reversed', '03/12/2026', '01/12/2026')
    record('returned-before', '30/11/2026', '03/12/2026', **{'Ngày quay lại làm việc': '01/01/0001'})
    with database.connect() as conn:
        before = conn.execute(text('SELECT to_jsonb(r) FROM vera_phase14_record r ORDER BY logical_id')).scalars().all()
    statements = []
    from sqlalchemy import event
    def observe(conn, cursor, statement, parameters, context, many):
        statements.append(statement.strip())
    event.listen(database, 'before_cursor_execute', observe)
    try:
        response = client.get('/v2/long-leave/admin/requests/target/overlap')
    finally:
        event.remove(database, 'before_cursor_execute', observe)
    assert response.status_code == 200, response.text
    result = response.json()
    assert {row['id'] for row in result['requests']} == {'slash', 'dash', 'iso', 'fallback', 'ambiguous-day-first', 'whitespace'}
    assert result['employee_count'] == 1
    assert len(result['days']) == 4
    assert all(row['other_count'] == 1 for row in result['days'])
    assert len(statements) == 3  # one caller connection: read-only guard + target + bounded candidates
    assert statements[0] == 'SET TRANSACTION READ ONLY'
    assert all(statement.startswith(('SET TRANSACTION READ ONLY', 'SELECT')) for statement in statements)
    with database.connect() as conn:
        after = conn.execute(text('SELECT to_jsonb(r) FROM vera_phase14_record r ORDER BY logical_id')).scalars().all()
    assert before == after


@pytest.mark.parametrize('start,end', [('2026-02-28', '2026-03-01'), ('2028-02-28', '2028-03-01'),
                                      ('2026-12-30', '2027-01-02')])
def test_date_keys_preserve_calendar_and_year_boundaries(canonical_client, start, end):
    client, _, record = canonical_client
    record('target', start, end, 'applicant')
    record('us', date.fromisoformat(start).strftime('%m/%d/%Y'), date.fromisoformat(end).strftime('%d/%m/%Y'))
    response = client.get('/v2/long-leave/admin/requests/target/overlap')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['employee_count'] == 1
    assert len(result['days']) == (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


@pytest.mark.parametrize('start,end', [('', ''), ('31/02/2026', '03/03/2026'),
                                      ('03/12/2026', '01/12/2026'), ('01/01/2026', '31/12/2027')])
def test_bad_target_dates_have_explicit_client_error(canonical_client, start, end):
    client, _, record = canonical_client
    record('target', start, end, 'applicant')
    response = client.get('/v2/long-leave/admin/requests/target/overlap')
    assert response.status_code == 400
    assert 'Khoảng ngày' in response.json()['detail']


@pytest.mark.parametrize('role', ['letan', 'quanly', 'nhanvien', 'leader', ''])
def test_non_admin_check_never_queries_records(canonical_client, database, role):
    client, identity, _ = canonical_client
    identity.role = role
    from sqlalchemy import event
    def forbidden(*args):
        raise AssertionError('Unauthorized identity must not query business records')
    event.listen(database, 'before_cursor_execute', forbidden)
    try:
        assert client.get('/v2/long-leave/admin/requests/target/overlap').status_code == 403
    finally:
        event.remove(database, 'before_cursor_execute', forbidden)


def test_parallel_checks_are_read_only_and_return_consistent_results(canonical_client, database):
    from concurrent.futures import ThreadPoolExecutor
    client, _, record = canonical_client
    record('target', '01/12/2026', '07/12/2026', 'applicant')
    record('other', '05/12/2026', '09/12/2026')
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: client.get('/v2/long-leave/admin/requests/target/overlap'), range(12)))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    with database.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_phase14_record')).scalar() == 2
        assert conn.execute(text('SELECT bool_and(revision=1 AND record_status=:status) FROM vera_phase14_record'),
                            {'status': leave.STATUS_PENDING}).scalar()

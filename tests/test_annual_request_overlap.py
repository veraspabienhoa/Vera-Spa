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
from test_revenue_auto_postgres import database
from test_live_tour_backend import RouteIdentity


def test_annual_request_overlap_deduplicates_people_and_checks_future_request(database):
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE employees(username text PRIMARY KEY, full_name text, role text, payload jsonb)'))
        conn.execute(text('''CREATE TABLE vera_phase14_record(logical_id text PRIMARY KEY,dataset text,
            employee_key text,record_type text,record_status text,date_from date,date_to date,payload jsonb,
            source_row int,revision bigint DEFAULT 1,updated_at timestamptz DEFAULT NOW())'''))
        for name,status in [('applicant','active'),('approved','active'),('pending','active'),('inactive','inactive')]:
            conn.execute(text('INSERT INTO employees VALUES (:name,:name,\'nhanvien\',CAST(:payload AS jsonb))'),
                         {'name':name,'payload':json.dumps({'employment_status':status})})
        def record(key,employee,start,end,status='Đã duyệt',**extra):
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

"""Approved-request corrections preserve unrelated leave and roll back as one unit."""
from datetime import date
import json
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, text

import vera_web_v2_long_leave_admin as admin
import vera_web_v2_long_leave_changes as changes
from test_revenue_auto_postgres import database
from test_live_tour_backend import RouteIdentity


@pytest.fixture
def setup(database):
    with database.begin() as conn:
        conn.execute(text('''CREATE TABLE vera_phase14_record(dataset text,logical_id text PRIMARY KEY,
            source_row int,employee_key text,record_type text,record_status text,date_from text,date_to text,
            payload jsonb,revision bigint DEFAULT 1,updated_by text,updated_at timestamptz DEFAULT now())'''))
        conn.execute(text('''CREATE TABLE leave_records(record_uid text PRIMARY KEY,employee_name text,
            leave_date date,leave_reason text,detail text,source_row int,calculated_days numeric DEFAULT 1)'''))
        payload = {'ID': 'test', 'Tên nhân viên': 'A', 'Trạng thái': 'Đã duyệt',
                   'Từ ngày': '10/10/2026', 'Đến ngày': '11/10/2026'}
        conn.execute(text('''INSERT INTO vera_phase14_record(dataset,logical_id,source_row,employee_key,
            record_type,record_status,date_from,date_to,payload) VALUES(:dataset,'long:test',2,'A',
            :kind,'Đã duyệt','10/10/2026','11/10/2026',CAST(:p AS jsonb))'''),
            {'dataset': admin.LONG_LEAVE_DATASET, 'kind': admin.REQUEST_TYPE_ANNUAL, 'p': json.dumps(payload)})
        for uid, day, detail in [('keep', '2026-10-10', 'Phép năm được Admin duyệt từ đơn test'),
                                ('remove', '2026-10-11', 'Phép năm được Admin duyệt từ đơn test'),
                                ('unrelated', '2026-10-15', 'Đăng ký riêng')]:
            conn.execute(text('INSERT INTO leave_records VALUES(:uid,\'A\',:day,:kind,:detail,3,1)'),
                         {'uid': uid, 'day': day, 'kind': admin.REQUEST_TYPE_ANNUAL, 'detail': detail})
    def validate(conn, body, ident, **kwargs):
        assert kwargs['skip_registration_timing'] is True
        assert conn.execute(text("SELECT count(*) FROM leave_records WHERE record_uid='remove'")).scalar() == 0
        return {**body.__dict__, 'record_uid': str(uuid4())}, []
    def insert(conn, record, source_row):
        assert source_row is None
        conn.execute(text('''INSERT INTO leave_records(record_uid,employee_name,leave_date,leave_reason,detail)
            VALUES(:record_uid,:employee_name,:leave_date,:leave_reason,:detail)'''), record)
    ident = SimpleNamespace(role='admin', employee_username='admin')
    args = dict(request_row=admin._request_row, norm=lambda x:str(x).strip().casefold(),
                validate_and_prepare=validate, leave_create_type=lambda **x:SimpleNamespace(**x),
                insert_record=insert, vn_tz=ZoneInfo('Asia/Ho_Chi_Minh'))
    return database, ident, args


def test_edit_keeps_matching_uids_releases_removed_days_and_audits_original(setup):
    engine, ident, args = setup
    body = changes.ApprovedRequestEdit(revision=1,start_date=date(2026,10,9),end_date=date(2026,10,10))
    with engine.begin() as conn:
        changes.mutate(conn,'test',body,ident,cancel=False,**args)
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT record_uid,leave_date FROM leave_records')).all()
        assert ('keep',date(2026,10,10)) in rows and ('unrelated',date(2026,10,15)) in rows
        assert all(uid!='remove' for uid,_ in rows)
        assert {day for _,day in rows} == {date(2026,10,9),date(2026,10,10),date(2026,10,15)}
        audit = conn.execute(text('SELECT * FROM vera_long_leave_change')).mappings().one()
        assert audit['removed_rows'][0]['record_uid']=='remove' and audit['before_payload']['revision']==1
        assert audit['mirror_pending']
        assert conn.execute(text("SELECT revision FROM vera_phase14_record")).scalar()==2


def test_quota_failure_rolls_back_request_and_daily_deletions(setup):
    engine, ident, args=setup
    def fail(*a,**kw): raise HTTPException(400,'Quota exceeded')
    args['validate_and_prepare']=fail
    with pytest.raises(HTTPException):
        with engine.begin() as conn:
            changes.mutate(conn,'test',changes.ApprovedRequestEdit(revision=1,
                start_date=date(2026,10,9),end_date=date(2026,10,10)),ident,cancel=False,**args)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar()==3
        assert conn.execute(text('SELECT revision FROM vera_phase14_record')).scalar()==1


@pytest.mark.parametrize('kind',[admin.REQUEST_TYPE_ANNUAL,'Nghỉ dài hạn',admin.REQUEST_TYPE_RESIGNATION])
def test_cancel_is_audited_and_only_annual_generated_rows_are_removed(setup,kind):
    engine, ident,args=setup
    with engine.begin() as conn:
        conn.execute(text('UPDATE vera_phase14_record SET record_type=:kind'),{'kind':kind})
        changes.mutate(conn,'test',changes.ApprovedRequestCancel(revision=1,note='Không nghỉ nữa'),
                       ident,cancel=True,**args)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT record_status FROM vera_phase14_record')).scalar()=='Đã hủy'
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar()==(1 if kind==admin.REQUEST_TYPE_ANNUAL else 3)
        assert conn.execute(text('SELECT action FROM vera_long_leave_change')).scalar()=='cancel'


def test_stale_revision_and_changed_generated_reason_do_not_write(setup):
    engine,ident,args=setup
    for stale in [True,False]:
        with engine.begin() as conn:
            if not stale:conn.execute(text("UPDATE leave_records SET leave_reason='Nghỉ CÓ phép' WHERE record_uid='remove'"))
        with pytest.raises(HTTPException) as error:
            with engine.begin() as conn:
                changes.mutate(conn,'test',changes.ApprovedRequestCancel(revision=2 if stale else 1,note='Hủy'),
                               ident,cancel=True,**args)
        assert error.value.status_code==409
    with engine.connect() as conn: assert conn.execute(text('SELECT revision FROM vera_phase14_record')).scalar()==1


def test_admin_route_commits_before_mirror_and_blocks_non_admin(setup):
    engine,ident,args=setup
    app=FastAPI(); active=[0]
    event.listen(engine,'checkout',lambda *a:active.__setitem__(0,active[0]+1))
    event.listen(engine,'checkin',lambda *a:active.__setitem__(0,active[0]-1))
    def mirror():
        assert active[0]==0,'no connection held during network I/O'
        raise RuntimeError('offline worksheet')
    changes.install(app,engine_instance=lambda:engine,current_identity=lambda:ident,
        identity_type=RouteIdentity,google_client=mirror,leave_sheet_id='test',
        sheet_row_for_record=lambda *a:None,require_admin=admin._require_admin,
        sheet_request_row=admin._sheet_request_row,**args)
    client=TestClient(app)
    ident.role='letan'
    assert client.request('DELETE','/v2/long-leave/admin/requests/test',json={'revision':1,'note':'Hủy'}).status_code==403
    ident.role='admin'
    response=client.request('DELETE','/v2/long-leave/admin/requests/test',json={'revision':1,'note':'Hủy'})
    assert response.status_code==200,response.text
    assert response.json()['mirror_pending']
    assert client.get('/v2/long-leave/admin/pending-changes').json()['request_ids']==['test']
    assert client.post('/v2/long-leave/admin/requests/test/sync').json()['mirror_pending']
    with engine.connect() as conn:
        assert conn.execute(text('SELECT record_status FROM vera_phase14_record')).scalar()=='Đã hủy'
        assert conn.execute(text('SELECT syncing_until FROM vera_long_leave_change')).scalar() is None

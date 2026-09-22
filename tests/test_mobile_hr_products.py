from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import json
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
import vera_web_v2_products as products
import vera_web_v2_hr_enhancements as hr
from vera_web_v2_live_tour_payment import default_settings, settings_update


def engine():
    sqlite3.register_adapter(Decimal, str)
    return create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)


def test_product_permissions_duplicate_sku_revision_and_persistence(monkeypatch):
    db=engine()
    with db.begin() as conn:
        conn.connection.create_function('NOW',0,lambda:'2026-09-22')
        conn.execute(text('CREATE TABLE vera_product_catalog (id TEXT PRIMARY KEY,sku TEXT,name TEXT,category TEXT,unit TEXT,price NUMERIC,active BOOLEAN,note TEXT,revision INTEGER DEFAULT 1,updated_by TEXT,updated_at TEXT)'))
        conn.execute(text('CREATE UNIQUE INDEX sku_unique ON vera_product_catalog(lower(sku))'))
    monkeypatch.setattr(products,'_schema',lambda c:None)
    ident=SimpleNamespace(role='letan',employee_username='test')
    app=FastAPI();products.install_product_routes(app,engine_instance=lambda:db,current_identity=lambda:ident,identity_type=SimpleNamespace)
    client=TestClient(app)
    body={'sku':' SP001 ','name':' Dầu massage ','price':120000}
    assert client.get('/v2/products').status_code==403
    assert client.post('/v2/products',json=body).status_code==403
    ident.role='admin'
    created=client.post('/v2/products',json=body)
    assert created.status_code==200,created.text
    product=created.json()['product']
    assert product['name']=='Dầu massage' and product['sku']=='SP001'
    assert client.post('/v2/products',json={**body,'sku':'sp001'}).status_code==409
    saved=client.put('/v2/products/'+product['id'],json={**product,'active':False})
    assert saved.status_code==200,saved.text
    assert saved.json()['product']['revision']==2
    assert client.put('/v2/products/'+product['id'],json=product).status_code==409
    assert client.get('/v2/products').json()['products'][0]['active']==0
    ident.role='nhanvien'
    assert client.put('/v2/products/'+product['id'],json=product).status_code==403


@pytest.mark.parametrize('patch',[{'name':'  '},{'sku':' '},{'price':-1},{'price':'NaN'},{'price':'Infinity'},{'price':'1.5'}])
def test_product_validation(patch):
    with pytest.raises(ValidationError): products.ProductInput(**{'sku':'SP','name':'Sản phẩm',**patch})


def test_customer_screen_settings_validated_and_preserved():
    payload=default_settings();payload['customer_screen']={'enabled':True,'width':500,'height':700,'qr_size':320}
    money=lambda value,**kw:int(value)
    assert settings_update(payload,money)['customer_screen']==payload['customer_screen']
    for size in [1,2000,True,'500']:
        payload['customer_screen']['width']=size
        with pytest.raises(HTTPException):settings_update(payload,money)


def test_overlap_includes_pending_excludes_inactive_and_counts_people(monkeypatch):
    db=engine()
    with db.begin() as conn:
        conn.connection.create_function('btrim',1,lambda s:s.strip() if s else s)
        conn.execute(text('CREATE TABLE employees(username TEXT,role TEXT,payload JSON)'))
        conn.execute(text('CREATE TABLE vera_hr_leave_period(request_id TEXT,employee_username TEXT,department_id TEXT,leave_type TEXT,scheduled_start DATE,scheduled_end DATE,status TEXT)'))
        for name,status in [('one','active'),('two','active'),('three','active'),('former','Nghỉ việc')]:
            conn.execute(text('INSERT INTO employees VALUES(:name,\'nhanvien\',:payload)'),{'name':name,'payload':json.dumps({'employment_status':status})})
        for key,name,status,day in [('1','one','pending','22'),('2','one','approved','22'),('3','two','approved','22'),('4','three','pending','22'),('5','former','approved','22'),('6','one','pending','23'),('7','two','approved','23')]:
            conn.execute(text('INSERT INTO vera_hr_leave_period VALUES(:id,:name,\'nhanvien\',\'Nghỉ Phép năm\',:day,:day,:status)'),{'id':key,'name':name,'day':'2026-09-'+day,'status':status})
    monkeypatch.setattr(hr,'sync_leave_periods',lambda c:None)
    class Adapt:
        def __init__(self,c):self.c=c
        def execute(self,q,p=None):return self.c.execute(text(str(q).replace('COUNT(*)::int','COUNT(*)')),p or {})
    class DB:
        @contextmanager
        def begin(self):
            with db.begin() as c:yield Adapt(c)
    app=FastAPI();hr.install_hr_enhancement_routes(app,engine_instance=DB,current_identity=lambda:SimpleNamespace(role='admin'),identity_type=SimpleNamespace)
    result=TestClient(app).get('/v2/hr/leaves/overlap?start=2026-09-22&end=2026-09-23').json()
    assert result['days'][0]['leave_count']==3
    assert result['days'][0]['pending_count']==2
    assert result['days'][0]['has_alert'] is True
    assert result['days'][1]['leave_count']==2 and result['days'][1]['has_alert'] is False
    assert result['days'][0]['departments'][0]['headcount']==3


def test_return_after_scheduled_end_replays_duplicate_and_uses_earliest_punch(monkeypatch):
    monkeypatch.setattr(hr,'_resolve_username',lambda c,n,code='':n)
    writes=[];tz=ZoneInfo('Asia/Ho_Chi_Minh')
    leave={'request_id':'L1','scheduled_start':date(2026,9,18),'scheduled_end':date(2026,9,20),'end_source':''}
    class Result:
        def __init__(self,value=None):self.value=value
        def scalar_one_or_none(self):return self.value
        def mappings(self):return self
        def first(self):return self.value
    class Connection:
        def execute(self,q,p=None):
            sql=str(q)
            if 'INSERT INTO vera_hr_attendance_log' in sql:return Result(None)
            if 'SELECT id FROM vera_hr_attendance_log' in sql:return Result('existing')
            if 'SELECT * FROM vera_hr_leave_period' in sql:
                assert 'scheduled_end>=' not in sql
                assert p['checkin_date']==date(2026,9,22)
                return Result(leave)
            if 'SELECT id,checkin_at' in sql:return Result({'id':'first','checkin_at':datetime(2026,9,21,10,tzinfo=tz)})
            if 'SELECT payload FROM vera_phase14_record' in sql:return Result({'payload':{'ID':'L1'}})
            writes.append((sql,p));return Result()
    result=hr.record_checkin(Connection(),username='one',checkin_at=datetime(2026,9,22,10),source='timesoft-cache',sync_projection=False)
    assert result['inserted'] is False and result['leave_closed'] is True
    payload=json.loads(next(p['payload'] for q,p in writes if 'UPDATE vera_phase14_record' in q))
    assert payload['Ngày quay lại làm việc']=='21/09/2026'
    assert payload['Trạng thái kỳ nghỉ']=='Đã kết thúc'
    assert result['attendance_log_id']=='first'
    leave['end_source']='manual';writes.clear()
    assert hr.record_checkin(Connection(),username='one',checkin_at=datetime(2026,9,22,10),source='timesoft-cache',sync_projection=False)['manual_override']
    assert not writes

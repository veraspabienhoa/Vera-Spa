"""Payroll source/count/exclusion regressions against isolated PostgreSQL schemas."""
from datetime import datetime
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
import vera_web_v2_department_payroll as dep
import vera_web_v2_payroll as payroll


@pytest.fixture
def database(monkeypatch):
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('VERA_TEST_POSTGRES_URL required')
    schema = 'department_payroll_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 26, 12, tzinfo=dep.VN_TZ)
    monkeypatch.setattr(dep, 'datetime', Clock)
    monkeypatch.setattr(dep.attendance, '_records', lambda *args: [])
    try:
        with engine.begin() as conn:
            conn.execute(text('''CREATE TABLE vera_app_setting(category text,setting_key text,value_json jsonb,
                source text,updated_by text,revision bigint,created_at timestamptz,updated_at timestamptz,
                PRIMARY KEY(category,setting_key))'''))
            conn.execute(text('''CREATE TABLE employees(username text PRIMARY KEY,full_name text,email text,
                role text,stt int,payload jsonb DEFAULT '{}'::jsonb)'''))
            conn.execute(text('CREATE TABLE leave_records(employee_name text,leave_date date,leave_reason text,penalty numeric)'))
            dep.work_schedule._ensure_schema(conn)
            for name, role, flag in [('a','letan',False),('b','quanly',False),('c','locker',False),('excluded','admin',True),('excluded-text','giamdoc','YES')]:
                conn.execute(text('INSERT INTO employees(username,full_name,role,payload) VALUES(:name,:name,:role,CAST(:payload AS jsonb))'),
                             dict(name=name,role=role,payload=json.dumps({'Không tính lương':flag})))
            for name, count, role in [('a',5,'letan'),('b',3,'quanly')]:
                for n in range(count):
                    conn.execute(text('''INSERT INTO vera_work_schedule_combo_sale(id,sale_date,employee_username,department,customer_name,combo_ticket)
                        VALUES(:id,'2026-09-05',:name,:role,'Synthetic','Synthetic')'''),dict(id=f'{name}-{n}',name=name,role=role))
            for key, day, role in [('old','2026-08-31','letan'),('future','2026-09-27','letan'),('wrong-source','2026-09-05','locker')]:
                conn.execute(text('''INSERT INTO vera_work_schedule_combo_sale(id,sale_date,employee_username,department,customer_name,combo_ticket)
                    VALUES(:id,:day,'a',:role,'Synthetic','Synthetic')'''),dict(id=key,day=day,role=role))
            payroll._put_setting(conn,'department_employee_salary_configs',{'a':{'default_combo_sales':100000},'b':{'default_combo_sales':100000},'c':{'default_combo_sales':999999}},'synthetic')
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


@pytest.fixture
def client(database):
    app = FastAPI()
    ident = SimpleNamespace(role='admin',employee_username='synthetic',allowed=True)
    def require(conn, who, feature):
        if not who.allowed:
            raise HTTPException(403,'No permission')
    dep.install_department_payroll_routes(app,engine_instance=lambda:database,current_identity=lambda:ident,
        require_feature=require,identity_type=SimpleNamespace,norm=lambda value:str(value or '').strip().casefold())
    with TestClient(app) as http:
        yield http, ident


@pytest.mark.parametrize('source',['schedule','attendance'])
def test_combo_is_count_times_100000_with_cutoff_and_excluded_employees(database, client, source):
    http,_ = client
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if 'GROUP BY lower(btrim(employee_username))' in statement:
            statements.append(statement)
    event.listen(database,'before_cursor_execute',capture)
    try:
        response=http.get(f'/v2/department-payroll/combined/calculate?month=2026-09&source={source}')
        assert response.status_code==200,response.text
        result={row['employee_username']:row for row in response.json()['rows']}
        assert set(result)=={'a','b','c'}
        assert (result['a']['combo_count'],result['a']['combo_sales'])==(5,500000)
        assert (result['b']['combo_count'],result['b']['combo_sales'])==(3,300000)
        assert result['c']['combo_sales']==0,'zero sales must not receive a default commission'
        assert len(statements)==1,'one grouped read for all payroll departments'
        with database.begin() as conn:
            conn.execute(text("DELETE FROM vera_work_schedule_combo_sale WHERE id='a-0'"))
        again=http.get(f'/v2/department-payroll/combined/calculate?month=2026-09&source={source}').json()
        assert next(r for r in again['rows'] if r['employee_username']=='a')['combo_sales']==400000
    finally:
        event.remove(database,'before_cursor_execute',capture)


def test_saved_drafts_hide_excluded_without_rewriting_history_and_reject_stale_writes(database,client):
    http,ident=client
    saved=[{'employee_username':'a','department':'letan','combo_sales':123,'net_salary':456},
           {'employee_username':'excluded','department':'admin','combo_sales':999,'net_salary':999}]
    history=[{'id':'historic','month':'2026-09','month_label':'09/2026','rows':saved}]
    with database.begin() as conn:
        payroll._put_setting(conn,'department_payroll_combined_draft_2026-09',saved,'synthetic')
        payroll._put_setting(conn,'department_payroll_combined_history',history,'synthetic')
    visible=http.get('/v2/department-payroll/combined/draft?month=2026-09').json()['rows']
    assert len(visible)==1 and visible[0]['combo_sales']==123 and visible[0]['net_salary']==456
    with database.connect() as conn:
        assert payroll._setting(conn,'department_payroll_combined_draft_2026-09',[])==saved
    opened=http.post('/v2/department-payroll/combined/history/historic/open').json()['rows']
    assert len(opened)==1 and opened[0]['combo_sales']==123
    for method,path in [('put','draft'),('post','complete'),('post','export.xlsx')]:
        result=getattr(http,method)(f'/v2/department-payroll/combined/{path}',json={'month':'2026-09','rows':saved})
        assert result.status_code==400,result.text
    with database.connect() as conn:
        assert payroll._setting(conn,'department_payroll_combined_history',[])==history
    settings=http.get('/v2/department-payroll/settings').json()
    assert all(not r['employee_username'].startswith('excluded') for r in settings['salary_employee_catalog'])
    ident.allowed=False
    assert http.get('/v2/department-payroll/combined/calculate?month=2026-09').status_code==403

"""Production-like draft/official guards; retain all stored history and profiles."""
from datetime import date, datetime
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_department_payroll_postgres import database, client
import vera_web_v2_department_payroll as dep
import vera_web_v2_payroll as payroll


@pytest.mark.parametrize('source', ['attendance', 'schedule'])
def test_september_support_calculates_drafts_exports_and_replaces_history_once(database, client, monkeypatch, source):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return datetime(2026, 10, 6, 12, tzinfo=dep.VN_TZ)
    monkeypatch.setattr(dep, 'datetime', Clock)
    http, ident = client
    names = ['admin', 'akamen', 'letan', 'Ms Tuyết']
    saved = [{'employee_username': 'a', 'department': 'letan', 'net_salary': 12345},
             {'employee_username': 'Ms Tuyết', 'department': 'support', 'net_salary': 45678}]
    history = [{'id': 'approved-before-suspension', 'month': '2026-09', 'rows': saved}]
    with database.begin() as conn:
        for name in names:
            conn.execute(text("INSERT INTO employees(username,full_name,role) VALUES(:name,:name,'admin')"), {'name': name})
        payroll._put_setting(conn, 'hr_registry', {'assignments': {name:'support' for name in names}}, 'synthetic')
        payroll._put_setting(conn, 'department_support_config', {
            'rate_ca1':20000, 'rate_ca2_before_22':25000, 'rate_ca2_after_22':30000}, 'synthetic')
        payroll._put_setting(conn, 'department_employee_salary_configs', {'Ms Tuyết':{'rate_ca1':35000}}, 'synthetic')
        for name in ['letan', 'Ms Tuyết']:
            conn.execute(text("""INSERT INTO vera_work_schedule(work_date,employee_username,employee_name,department,shift_code)
                VALUES('2026-09-28',:name,:name,'letan','Ca 1')"""), {'name':name})
        payroll._put_setting(conn, 'department_payroll_combined_draft_2026-09', saved, 'synthetic')
        payroll._put_setting(conn, 'department_payroll_combined_history', history, 'synthetic')
        profiles = [tuple(r) for r in conn.execute(text('SELECT * FROM employees ORDER BY username'))]
    monkeypatch.setattr(dep.attendance, '_records', lambda *_: [
        {'employee_name':name, 'date':'28/09/2026', 'shift':'Ca 1', 'check_in':'09:00', 'check_out':'17:00', 'total_minutes':480}
        for name in ['letan','Ms Tuyết']])
    response = http.get(f'/v2/department-payroll/combined/calculate?month=2026-09&source={source}')
    assert response.status_code == 200, response.text
    rows = response.json()['rows']; by_name = {r['employee_username']:r for r in rows}
    assert {'letan','Ms Tuyết'}.issubset(by_name)
    assert not {'admin','akamen'}.intersection(by_name)
    assert by_name['letan']['department'] == by_name['Ms Tuyết']['department'] == 'support'
    assert by_name['letan']['salary'] > 0 and by_name['Ms Tuyết']['salary'] > by_name['letan']['salary']
    assert response.json()['end'] == '2026-09-30'
    draft = http.get('/v2/department-payroll/combined/draft?month=2026-09').json()['rows']
    assert {r['employee_username'] for r in draft} == {'a','Ms Tuyết'}
    # Merely calculating or opening the saved view cannot rewrite approved money.
    with database.connect() as conn:
        assert payroll._setting(conn,'department_payroll_combined_history',[]) == history
        assert [tuple(r) for r in conn.execute(text('SELECT * FROM employees ORDER BY username'))] == profiles
    # A partial save must retain previously approved Support money until replaced.
    partial = http.post('/v2/department-payroll/combined/complete', json={
        'month':'2026-09','rows':[dict(saved[0],calculation_source='schedule')]})
    assert partial.status_code == 200, partial.text
    with database.connect() as conn:
        kept = payroll._setting(conn,'department_payroll_combined_history',[])[0]['rows']
        assert next(r for r in kept if r['employee_username']=='Ms Tuyết') == saved[1]
    assert http.put('/v2/department-payroll/combined/draft', json={'month':'2026-09','rows':rows}).status_code == 200
    assert http.post('/v2/department-payroll/combined/export.xlsx', json={'month':'2026-09','rows':rows}).status_code == 200
    for _ in range(2):
        result = http.post('/v2/department-payroll/combined/complete', json={'month':'2026-09','rows':rows})
        assert result.status_code == 200, result.text
    with database.connect() as conn:
        items = payroll._setting(conn,'department_payroll_combined_history',[])
        assert len(items) == 1 and items[0]['id'] == history[0]['id']
        completed = items[0]['rows']
        assert len([r for r in completed if r['employee_username']=='Ms Tuyết']) == 1
        assert next(r for r in completed if r['employee_username']=='Ms Tuyết')['salary'] == by_name['Ms Tuyết']['salary']
    support_rows = [r for r in rows if r['department']=='support']
    for method, path in [('put','draft'),('post','save'),('post','export.xlsx')]:
        result = getattr(http,method)(f'/v2/department-payroll/{path}', json={'month':'2026-09','department':'support','rows':support_rows})
        assert result.status_code == 200, result.text
    for month in ['2026-08','2026-10']:
        result = http.get(f'/v2/department-payroll/combined/calculate?month={month}&source={source}')
        assert result.status_code == 200, result.text
        assert {'letan','Ms Tuyết'}.issubset({r['employee_username'] for r in result.json()['rows']})


def test_tip_period_update_keeps_suspended_money_and_passes_old_deductions_to_hook(database, monkeypatch):
    start, end = date(2026, 9, 16), date(2026, 9, 30)
    label = payroll._period_label(start, end)
    old = {'Mã bản lưu': label, 'Tên Hệ thống': 'Ms Tuyết', 'Tiền Lương': 123456,
           'Vi phạm kỳ trước': 10000, 'Số tiền thực nhận': 113456}
    with database.begin() as conn:
        conn.execute(text('ALTER TABLE employees ADD COLUMN bank_account text, ADD COLUMN bank_name text'))
        conn.execute(text("UPDATE employees SET role='nhanvien' WHERE username='a'"))
        conn.execute(text("INSERT INTO employees(username,full_name,role) VALUES('Ms Tuyết','Ms Tuyết','nhanvien')"))
        conn.execute(text('''CREATE TABLE payroll_history_rows(batch_id text,employee_name text,
            period_start date,period_end date,payload jsonb,saved_at timestamptz)'''))
        conn.execute(text('''CREATE TABLE vera_dataset_cache(dataset_key text PRIMARY KEY,payload jsonb,
            row_count int,checksum text,source_version text,updated_at timestamptz,expires_at timestamptz)'''))
        conn.execute(text('''INSERT INTO payroll_history_rows VALUES(:label,'Ms Tuyết',:start,:end,
            CAST(:payload AS jsonb),'2026-09-29T12:00:00Z')'''),
            {'label': label, 'start': start, 'end': end, 'payload': json.dumps(old)})
        before = tuple(conn.execute(text("SELECT * FROM payroll_history_rows WHERE employee_name='Ms Tuyết'")).one())
    monkeypatch.setattr(payroll, '_payload', lambda _: ([old], '', None))
    app = FastAPI()
    ident = SimpleNamespace(role='admin', employee_username='synthetic')
    payroll.install_payroll_routes(app, engine_instance=lambda: database,
        current_identity=lambda: ident, require_feature=lambda *_: None,
        norm=lambda name: str(name or '').casefold(), identity_type=SimpleNamespace, google_client=lambda: None)
    reconciled = []
    app.state.payroll_before_save_hook = lambda **kwargs: reconciled.append(kwargs['prepared_rows']) or {}
    with TestClient(app) as http:
        for _ in range(2):
            result = http.post('/v2/payroll/save', json={'start': str(start), 'end': str(end),
                'rows': [{'Tên Hệ thống': 'a', 'Tiền Lương': 100000}]})
            assert result.status_code == 200, result.text
        denied = http.post('/v2/payroll/save', json={'start': str(start), 'end': str(end), 'rows': [old]})
        assert denied.status_code == 409, denied.text
    assert all(old in rows for rows in reconciled)
    with database.connect() as conn:
        assert tuple(conn.execute(text("SELECT * FROM payroll_history_rows WHERE employee_name='Ms Tuyết'")).one()) == before
        assert conn.execute(text("SELECT COUNT(*) FROM payroll_history_rows WHERE employee_name='a'")).scalar() == 1
        cached = conn.execute(text("SELECT payload FROM vera_dataset_cache WHERE dataset_key='payroll_history'")).scalar()
        assert next(r for r in cached if r['Tên Hệ thống'] == 'Ms Tuyết') == old

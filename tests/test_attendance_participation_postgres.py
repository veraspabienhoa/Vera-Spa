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
def test_suspension_filters_calculation_and_blocks_stale_finalization(database, client, monkeypatch, source):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return datetime(2026, 9, 29, 22, tzinfo=dep.VN_TZ)
    monkeypatch.setattr(dep, 'datetime', Clock)
    http, ident = client
    suspended = ['admin', 'akamen', 'letan', 'Ms Tuyết']
    before_enrollment = ['Cậu Tưởng', 'Nguyễn Thị Sen', 'Nguyễn Thị Thu Hiền', 'Ngô Sĩ Đạt', 'Vũ Tân']
    saved = [{'employee_username': 'a', 'department': 'letan', 'net_salary': 12345},
             {'employee_username': 'Ms Tuyết', 'department': 'letan', 'net_salary': 45678}]
    history = [{'id': 'approved-before-suspension', 'month': '2026-09', 'rows': saved}]
    with database.begin() as conn:
        for name in suspended + before_enrollment:
            conn.execute(text("INSERT INTO employees(username,full_name,role) VALUES(:name,:name,'letan')"), {'name': name})
        payroll._put_setting(conn, 'department_payroll_combined_draft_2026-09', saved, 'synthetic')
        payroll._put_setting(conn, 'department_payroll_combined_history', history, 'synthetic')
        profiles = [tuple(r) for r in conn.execute(text('SELECT * FROM employees ORDER BY username'))]
    result = http.get(f'/v2/department-payroll/combined/calculate?month=2026-09&source={source}')
    assert result.status_code == 200, result.text
    users = {r['employee_username'] for r in result.json()['rows']}
    assert not users.intersection(suspended)
    assert set(before_enrollment).issubset(users), 'enrollment deferred, not payroll-exempt'
    result = http.get('/v2/department-payroll/combined/draft?month=2026-09')
    assert [r['employee_username'] for r in result.json()['rows']] == ['a']
    for method, path in [('put', 'draft'), ('post', 'complete'), ('post', 'export.xlsx')]:
        response = getattr(http, method)(f'/v2/department-payroll/combined/{path}',
            json={'month': '2026-09', 'rows': [dict(row, calculation_source=source) for row in saved]})
        assert response.status_code == 409, response.text
    for method, path in [('put', 'draft'), ('post', 'save'), ('post', 'export.xlsx')]:
        response = getattr(http, method)(f'/v2/department-payroll/{path}',
            json={'month': '2026-09', 'department': 'letan', 'rows': saved})
        assert response.status_code == 409, response.text
    with database.connect() as conn:
        assert payroll._setting(conn, 'department_payroll_combined_history', []) == history
        assert payroll._setting(conn, 'department_payroll_combined_draft_2026-09', []) == saved
        assert [tuple(r) for r in conn.execute(text('SELECT * FROM employees ORDER BY username'))] == profiles
    historic = http.get(f'/v2/department-payroll/combined/calculate?month=2026-08&source={source}')
    historic_users = {r['employee_username'] for r in historic.json()['rows']}
    assert {'letan', 'Ms Tuyết'}.issubset(historic_users)
    assert not {'admin', 'akamen'}.intersection(historic_users)
    # Completing other employees must not erase the suspended account's saved money.
    response = http.post('/v2/department-payroll/combined/complete', json={
        'month': '2026-09', 'rows': [dict(saved[0], calculation_source='schedule')]})
    assert response.status_code == 200, response.text
    assert [r['employee_username'] for r in response.json()['rows']] == ['a']
    with database.connect() as conn:
        completed = payroll._setting(conn, 'department_payroll_combined_history', [])[0]['rows']
        assert next(r for r in completed if r['employee_username'] == 'Ms Tuyết') == saved[1]

    class OctoberClock(datetime):
        @classmethod
        def now(cls, tz=None): return datetime(2026, 10, 1, 12, tzinfo=dep.VN_TZ)
    monkeypatch.setattr(dep, 'datetime', OctoberClock)
    resumed = http.get(f'/v2/department-payroll/combined/calculate?month=2026-10&source={source}')
    assert resumed.status_code == 200, resumed.text
    resumed_users = {r['employee_username'] for r in resumed.json()['rows']}
    assert {'letan', 'Ms Tuyết'}.issubset(resumed_users)
    assert not {'admin', 'akamen'}.intersection(resumed_users)


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

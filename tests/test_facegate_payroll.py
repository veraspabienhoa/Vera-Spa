from datetime import date
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import vera_facegate_payroll as fg
import vera_web_v2_facegate_attendance as routes
from vera_web_v2_department_payroll import DEFAULT_CONFIG

DAY = date(2026, 9, 28)
TODAY = date(2026, 9, 29)
ROW = {'date': '28/09/2026', 'employee_name': 'Test', 'check_in': '17:30:00',
       'check_out': '01:30:00', 'shift': 'Ca 2', 'shift_start': '17:30', 'shift_end': '01:30',
       'attendance_expected': True}


def calc(rows=None, report=None, config=None, **kwargs):
    return fg.calculate_employee([ROW] if rows is None else rows, 'Test', config or DEFAULT_CONFIG['letan'],
        DAY, DAY, report or {}, kwargs.get('today', TODAY))


def test_saved_rates_and_overnight_split_use_existing_payroll_formula():
    result = calc(config={**DEFAULT_CONFIG['letan'], 'rate_ca2_before_22': 41000, 'rate_ca2_after_22': 45000})
    assert result['status'] == 'estimated'
    assert result['hours'] == 8
    assert result['basic_salary_estimate'] == 4.5 * 41000 + 3.5 * 45000


@pytest.mark.parametrize('case', ['missing_day','missing_exit','unmapped','open_day','incomplete','unresolved','missing_shift','zero_rate','duplicate'])
def test_incomplete_evidence_is_pending_not_zero_pay(case):
    rows, report, cfg, today = [dict(ROW)], {}, dict(DEFAULT_CONFIG['letan']), TODAY
    if case == 'missing_day': rows=[]
    elif case == 'missing_exit': rows[0]['check_out']=''
    elif case == 'unmapped': report['unmapped_employees']=['Test']
    elif case == 'open_day': today=DAY
    elif case == 'incomplete': report['incomplete_days']=['2026-09-29']
    elif case == 'unresolved': report['blocking_issue_count']=1
    elif case == 'missing_shift': rows[0]['shift']=''
    elif case == 'zero_rate': cfg['rate_ca2_after_22']=0
    else: rows.append(dict(ROW))
    result=calc(rows,report,cfg,today=today)
    assert result['status']=='pending'
    assert result['basic_salary_estimate'] is None and result['hours'] is None
    assert result['pending_reasons']


def test_yen_linh_without_test_scans_has_no_invented_checkout_or_salary():
    result = calc([{**ROW, 'check_in':'09:02:57','check_out':'','punch_times':['09:02:57']}])
    assert result['basic_salary_estimate'] is None
    assert result['daily_records'][0]['check_out']==''


@pytest.mark.parametrize('role', ['letan','nhanvien','quanly'])
def test_payroll_preview_denies_non_admin_before_database_checkout(role):
    app=FastAPI()
    def forbidden(): raise AssertionError('no database access')
    routes.install_facegate_attendance_routes(app,engine_instance=forbidden,
        current_identity=lambda:SimpleNamespace(role=role),identity_type=SimpleNamespace)
    assert TestClient(app).get('/v2/devices/facegate-attendance/payroll-preview?start=2026-09-28&end=2026-09-28').status_code==403


def test_out_of_range_rejected_before_database_checkout():
    app=FastAPI()
    def forbidden(): raise AssertionError('no database access')
    routes.install_facegate_attendance_routes(app,engine_instance=forbidden,
        current_identity=lambda:SimpleNamespace(role='admin'),identity_type=SimpleNamespace)
    assert TestClient(app).get('/v2/devices/facegate-attendance/payroll-preview?start=2026-09-01&end=2026-09-29').status_code==400


def test_endpoint_uses_one_read_only_transaction_and_no_device_calls(monkeypatch):
    calls=[]
    class Conn:
        def execute(self,sql): calls.append(str(sql))
        def __enter__(self): return self
        def __exit__(self,*args): pass
    conn=Conn()
    class Engine:
        def begin(self): calls.append('begin'); return conn
    def calculate(c,start,end):
        assert c is conn
        assert 'READ ONLY' in calls[1]
        return {'ok':True,'rows':[],'official_payroll_written':False}
    monkeypatch.setattr(fg,'calculate',calculate)
    app=FastAPI()
    routes.install_facegate_attendance_routes(app,engine_instance=Engine,
        current_identity=lambda:SimpleNamespace(role='admin'),identity_type=SimpleNamespace)
    response=TestClient(app).get('/v2/devices/facegate-attendance/payroll-preview?start=2026-09-28&end=2026-09-28')
    assert response.status_code==200
    assert response.json()['official_payroll_written'] is False
    assert len(calls)==3

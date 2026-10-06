from datetime import date
import pytest
from fastapi import HTTPException
from vera_department_probation import apply, qualifying_month, policies
import vera_web_v2_department_payroll as dep
from vera_employee_names import identity_index

POLICY = {'rate': .75, 'start': '2026-10-20', 'qualifying_month': None}


def punches(month, count):
    return [{'employee_name': 'worker', 'date': f'{i+1:02d}/{month[5:]}/{month[:4]}', 'total_minutes': 480} for i in range(count)]


def test_first_month_below_15_then_qualifying_month_and_next_month():
    index = identity_index([{'username': 'worker', 'payload': {}}])
    evidence = punches('2026-10', 10) + punches('2026-11', 26)
    args = (evidence, 'worker', date(2026,10,1))
    assert qualifying_month(*args, date(2026,10,31), index, dep._interval_minutes) is None
    assert qualifying_month(*args, date(2026,11,30), index, dep._interval_minutes) == '2026-11'


def test_unique_actual_days_only_and_exact_15_boundary():
    index = identity_index([{'username': 'worker', 'payload': {}}])
    evidence = punches('2026-10', 14)
    evidence += [evidence[0], {'employee_name':'worker','date':'15/10/2026','attendance_pending':True,'total_minutes':480},
                 {'employee_name':'other','date':'16/10/2026','total_minutes':480},
                 {'employee_name':'worker','date':'17/10/2026','total_minutes':0}]
    assert qualifying_month(evidence,'worker',date(2026,10,1),date(2026,10,31),index,dep._interval_minutes) is None
    evidence += [{'employee_name':'worker','date':'15/10/2026','total_minutes':1}]
    assert qualifying_month(evidence,'worker',date(2026,10,1),date(2026,10,31),index,dep._interval_minutes) == '2026-10'
    assert qualifying_month(evidence,'worker',date(2026,10,2),date(2026,10,31),index,dep._interval_minutes) is None


@pytest.mark.parametrize('department', ['letan','locker','support','tapvu'])
def test_income_scaled_once_deductions_unchanged_save_export_email(department):
    cfg = {**dep.DEFAULT_CONFIG[department], 'default_base_salary': 8_000_000, 'rate_ca1': 30_000}
    raw = {'base_salary':8_000_000,'work_days':26,'hours_ca1':200,'full_allowance':300_000,
           'attendance_bonus':400_000,'responsibility':200_000,'seniority':100_000,'combo_sales':200_000,
           'advance':1_000_000,'violation_penalty':100_000,'late_penalty':50_000}
    normal = dep._recalculate(raw,cfg)
    trial = dep._recalculate(apply(raw,POLICY),cfg)
    assert trial['salary'] == normal['salary'] * .75
    assert trial['base_salary'] == 6_000_000
    assert trial['total_salary'] == normal['total_salary'] * .75
    assert trial['net_salary'] == trial['total_salary'] - 1_150_000
    for field in ('advance','violation_penalty','late_penalty'):
        assert trial[field] == raw[field]
    saved = dep._recalculate(apply(trial,POLICY,saved=True),cfg)
    assert saved == trial
    assert dep._recalculate(saved,cfg) == saved
    _,plain,html = dep._email_content(saved,date(2026,10,1),date(2026,10,31),[])
    assert dep.payroll._email_money(saved['salary']) in plain
    assert dep.payroll._email_money(saved['net_salary']) in html


def test_stale_policy_requires_recalculation_and_pending_stays_pending():
    with pytest.raises(HTTPException) as exc:
        apply({'probation_rate':.75}, {'rate':1}, saved=True)
    assert exc.value.status_code == 409
    row = dep._recalculate(apply({'attendance_pending':True,'advance':100}, POLICY), dep.DEFAULT_CONFIG['letan'])
    assert row['salary'] is row['total_salary'] is row['net_salary'] is None
    assert row['advance'] == 100


class Result:
    def __init__(self, rows): self.rows=rows
    def mappings(self): return self
    def all(self): return self.rows

class Conn:
    def __init__(self, employees): self.employees=employees;self.calls=0
    def execute(self, query, params=None):
        self.calls += 1
        if 'AS employment_start_date' in str(query): return Result(self.employees)
        return Result([{'username':'worker','payload':{}}])


def test_policy_uses_one_borrowed_connection_read_and_next_month_only():
    conn = Conn([{'username':'worker','employment_start_date':'01/10/2026'}]); calls=[]
    def evidence(given,start,end):
        assert given is conn
        calls.append((start,end))
        return punches('2026-10',10)+punches('2026-11',26)
    kwargs=dict(parse_date=dep.payroll._parse_date,records=evidence,minutes=dep._interval_minutes,period_end=date(2026,12,31))
    assert policies(conn,'2026-11',**kwargs)['worker']['rate']==.75
    assert policies(conn,'2026-12',**kwargs)['worker']['rate']==1
    assert calls == [(date(2026,10,1),date(2026,10,31)),(date(2026,10,1),date(2026,11,30))]


def test_no_probation_does_not_read_attendance_and_missing_start_fails_closed():
    def unexpected(*args): raise AssertionError('must not read attendance')
    kwargs=dict(parse_date=dep.payroll._parse_date,records=unexpected,minutes=dep._interval_minutes,period_end=date(2026,12,31))
    assert policies(Conn([]),'2026-12',**kwargs)=={}
    with pytest.raises(HTTPException): policies(Conn([{'username':'worker','employment_start_date':''}]),'2026-12',**kwargs)


def test_probation_status_is_valid_and_remains_active_for_tour():
    from vera_web_v2_staff import STATUS_OPTIONS, _status_value, _effective_status
    from vera_web_v2_auth_gateway import _normalize
    from vera_web_v2_live_tour_roster import eligible
    assert 'Thử việc' in STATUS_OPTIONS
    assert _status_value('Thử việc', _normalize) == 'Thử việc'
    employee={'username':'worker','role':'nhanvien','payload':{'Trạng thái làm việc':'Thử việc'}}
    assert _effective_status(employee,_normalize)=='Thử việc'
    assert eligible(employee)
    employee['payload']['Trạng thái làm việc']='Đã nghỉ việc'
    assert not eligible(employee)

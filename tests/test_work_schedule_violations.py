from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
import vera_web_v2_work_schedule as schedule
import vera_web_v2_department_payroll as payroll


class Result:
    def __init__(self, value=None, rows=None): self.value, self.rows = value, rows or []
    def scalar(self): return self.value
    def mappings(self): return self
    def all(self): return self.rows


class Connection:
    def __init__(self): self.records = []; self.executed = []
    def execute(self, statement, params=None):
        sql = str(statement); self.executed.append((sql, params))
        if 'SELECT payload' in sql:
            return Result(next((json.loads(r['payload']) for r in self.records if r['uid'] == params['uid']), None))
        if 'MIN(source_row)' in sql: return Result(-len(self.records)-1)
        if 'INSERT INTO leave_records' in sql: self.records.append(params.copy())
        return Result()


class Engine:
    def __init__(self): self.conn = Connection()
    @contextmanager
    def begin(self): yield self.conn


def setup(monkeypatch, allowed=True):
    engine = Engine(); app = FastAPI()
    monkeypatch.setattr(schedule, '_allowed_department', lambda *args: allowed)
    monkeypatch.setattr(schedule, '_combo_employee', lambda conn, department, username: {'username': 'linh', 'full_name': 'Yên Linh'})
    schedule.install_work_schedule_routes(app, engine_instance=lambda: engine, current_identity=lambda: None, feature_allowed=lambda *args: allowed)
    route = next(r.endpoint for r in app.routes if r.path == '/v2/work-schedule/violations' and 'POST' in r.methods)
    return engine, route


def body(**changes):
    return schedule.ScheduleViolationCreate(**dict(request_id=uuid4(), department='letan', employee_username='linh', violation_date=date(2026,10,6), reason='Không đúng đồng phục', amount=50000, **changes))


def actor(role): return SimpleNamespace(role=role, employee_username='operator')


@pytest.mark.parametrize('role', ['letan','leader','nhanvien','locker','tapvu'])
def test_non_managers_cannot_write(monkeypatch, role):
    engine, route = setup(monkeypatch)
    with pytest.raises(HTTPException) as exc: route(body(), actor(role))
    assert exc.value.status_code == 403 and not engine.conn.executed


@pytest.mark.parametrize('role', ['admin','quanly'])
def test_retries_are_idempotent_and_record_is_zero_day_financial_entry(monkeypatch, role):
    engine, route = setup(monkeypatch); request = body()
    route(request, actor(role)); route(request, actor(role))
    assert len(engine.conn.records) == 1
    record = engine.conn.records[0]
    assert record['amount'] == 50000 and record['employee'] == 'linh' and record['actor'] == 'operator'
    sql = next(sql for sql, params in engine.conn.executed if 'INSERT INTO leave_records' in sql)
    assert "'Vi phạm'" in sql and ':note,0,0,:amount' in sql
    with pytest.raises(HTTPException) as exc: route(request.model_copy(update={'amount':60000}), actor(role))
    assert exc.value.status_code == 409 and len(engine.conn.records) == 1


def test_department_denial_never_writes(monkeypatch):
    engine, route = setup(monkeypatch, False)
    with pytest.raises(HTTPException): route(body(), actor('quanly'))
    assert not engine.conn.records


def test_penalty_is_in_existing_payroll_source_and_reduces_net():
    class FinancialConnection:
        def execute(self, *args): return Result(rows=[{'employee_name':'linh','leave_reason':'Vi phạm · Đồng phục','penalty':50000}])
    other, late = payroll._penalty_maps(FinancialConnection(), date(2026,10,1), date(2026,10,31), lambda value: value.lower())
    assert other == {'linh':50000} and late == {}
    row = payroll._recalculate({'hours_ca1':8, 'violation_penalty':other['linh']}, payroll.DEFAULT_CONFIG['locker'])
    assert row['net_salary'] == row['total_salary'] - 50000


def test_invalid_amount_rejected():
    for amount in [-1, float('nan'), 1_000_000_001]:
        with pytest.raises(ValidationError): body().model_validate({**body().model_dump(), 'amount':amount})


@pytest.mark.parametrize('method', ['PUT','DELETE'])
@pytest.mark.parametrize('role', ['quanly','letan','leader','nhanvien'])
def test_only_admin_can_edit_or_delete_before_database(monkeypatch, method, role):
    app = FastAPI()
    schedule.install_work_schedule_routes(app, engine_instance=lambda: pytest.fail('no database for denied role'),
        current_identity=lambda: None, feature_allowed=lambda *args: True)
    endpoint = next(r.endpoint for r in app.routes if r.path == '/v2/work-schedule/violations/{violation_id}' and method in r.methods)
    from datetime import datetime, timezone
    values = dict(department='letan',expected_updated_at=datetime.now(timezone.utc))
    model = schedule.ScheduleViolationRevision(**values) if method == 'DELETE' else schedule.ScheduleViolationUpdate(
        **values,violation_date=date(2026,10,6),reason='Đồng phục',amount=10000)
    with pytest.raises(HTTPException) as exc: endpoint('uid',model,actor(role))
    assert exc.value.status_code == 403


def test_edit_delete_archive_and_stale_guard(monkeypatch):
    from datetime import datetime, timezone
    updated = datetime(2026,10,6,2,tzinfo=timezone.utc)
    row = dict(record_uid='uid',employee_name='linh',leave_date=date(2026,10,6),leave_reason='Vi phạm · Đồng phục',
        leave_type='Vi phạm',source_sheet_id='postgres:work_schedule_violation',penalty=50000,detail='Old',
        payload={'schedule_violation':{'original':'kept'}},updated_at=updated,updated_by='manager')
    class MutationConnection:
        def __init__(self): self.writes=[]
        def execute(self,sql,params=None):
            if 'SELECT *' in str(sql): return SimpleNamespace(mappings=lambda:SimpleNamespace(first=lambda:row))
            if 'UPDATE leave_records' in str(sql): self.writes.append(params)
            return Result()
    conn=MutationConnection()
    monkeypatch.setattr(schedule,'_employee_catalog',lambda *args:[{'username':'linh'}])
    model=schedule.ScheduleViolationUpdate(department='letan',expected_updated_at=updated,violation_date='2026-10-05',
        reason='Đồng phục sửa',amount=80000,note='Updated')
    assert schedule._mutate_schedule_violation(conn,'uid',model,actor('admin'))['ok']
    saved=conn.writes[-1];payload=json.loads(saved['payload'])
    assert saved['amount']==80000 and saved['day']==date(2026,10,5)
    assert payload['schedule_violation']=={'original':'kept'}
    assert payload['schedule_violation_changes'][-1]['before']['penalty']=='50000'
    assert payload['schedule_violation_changes'][-1]['actor']=='operator'
    stale=model.model_copy(update={'expected_updated_at':datetime(2026,10,6,1,tzinfo=timezone.utc)})
    with pytest.raises(HTTPException) as exc: schedule._mutate_schedule_violation(conn,'uid',stale,actor('admin'))
    assert exc.value.status_code==409 and len(conn.writes)==1
    schedule._mutate_schedule_violation(conn,'uid',model,actor('admin'),deleting=True)
    saved=conn.writes[-1];payload=json.loads(saved['payload'])
    assert saved['amount']==0 and payload['__schedule_violation_deleted'] is True
    assert payload['schedule_violation_changes'][-1]['action']=='delete'
    assert saved['day']==row['leave_date'], 'financial deletion preserves source attendance/leave date'

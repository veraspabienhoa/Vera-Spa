from datetime import date
from types import SimpleNamespace
import asyncio
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
import vera_web_v2_work_schedule as schedule
from test_live_tour_resource_postgres import database


def identity(role):
    return SimpleNamespace(role=role, employee_username='operator')


def routes(engine, allowed=True):
    app = FastAPI()
    schedule.install_work_schedule_routes(app, engine_instance=lambda: engine,
        current_identity=lambda: identity('letan'), feature_allowed=lambda *args: allowed)
    return {(r.path, method): r.endpoint for r in app.routes for method in (r.methods or [])}


def body(department='letan', username='reception-test'):
    return schedule.ScheduleSave(rows=[schedule.ScheduleWriteRow(expected_revision=0, work_date=date(2026, 10, 1),
        employee_username=username, employee_name='Test', department=department, shift_code='Ca 1')])


@pytest.mark.parametrize('role', ['admin', 'quanly', 'letan', 'leader', 'nhanvien', 'locker', 'tapvu'])
@pytest.mark.parametrize('department', ['letan', 'quanly', 'locker', 'tapvu'])
def test_schedule_editor_matrix(role, department):
    assert schedule._can_edit_schedule(identity(role), department) == (
        role in {'admin', 'quanly'} or (role == 'letan' and department == 'letan'))


@pytest.mark.parametrize('role', ['admin', 'quanly', 'letan'])
def test_reception_save_and_delete(database, monkeypatch, role):
    monkeypatch.setattr(schedule, '_employee_catalog', lambda *args: [{'username':'reception-test'}])
    endpoints = routes(database)
    result = endpoints['/v2/work-schedule', 'PUT'](body(), identity(role))
    assert result['saved'] == 1
    assert endpoints['/v2/work-schedule', 'DELETE'](date(2026,10,1), 'reception-test', result['revisions'][0]['revision'], identity(role))['deleted'] == 1


def test_reception_rejects_other_departments_before_database():
    endpoints = routes(None)
    for department in ['locker', 'quanly', 'tapvu']:
        with pytest.raises(HTTPException) as exc:
            endpoints['/v2/work-schedule','PUT'](body(department), identity('letan'))
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            asyncio.run(endpoints['/v2/work-schedule/import.xlsx','POST'](
                None, date(2026,10,1), date(2026,10,1), department, identity('letan')))
        assert exc.value.status_code == 403


def test_reception_cannot_spoof_employee_or_overwrite_other_department(database, monkeypatch):
    monkeypatch.setattr(schedule, '_employee_catalog', lambda *args: [{'username':'reception-test'}])
    endpoints = routes(database)
    with pytest.raises(HTTPException) as exc:
        endpoints['/v2/work-schedule','PUT'](body(username='manager'), identity('letan'))
    assert exc.value.status_code == 403
    endpoints['/v2/work-schedule','PUT'](body('locker'), identity('admin'))
    with pytest.raises(HTTPException) as exc:
        endpoints['/v2/work-schedule','PUT'](body(), identity('letan'))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        endpoints['/v2/work-schedule','DELETE'](date(2026,10,1), 'reception-test', 1, identity('letan'))
    assert exc.value.status_code == 403
    with database.begin() as conn:
        assert conn.execute(text('SELECT department FROM vera_work_schedule')).scalar_one() == 'locker'


def test_reception_still_needs_department_feature(database, monkeypatch):
    monkeypatch.setattr(schedule, '_employee_catalog', lambda *args: [{'username':'reception-test'}])
    with pytest.raises(HTTPException) as exc:
        routes(database, allowed=False)['/v2/work-schedule','PUT'](body(), identity('letan'))
    assert exc.value.status_code == 403

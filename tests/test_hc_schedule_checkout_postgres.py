import json
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from sqlalchemy import text

import vera_web_v2_work_schedule as schedule
import vera_web_v2_attendance_query_perf as attendance
from vera_web_v2_attendance_v42 import _eligible_aliases
from test_facegate_attendance_postgres import database


def test_hr_roster_checkout_and_schedule_catalog_use_assignment_without_leaking_roles(database):
    with database.begin() as conn:
        conn.execute(text("""INSERT INTO employees(username,full_name,role,payload) VALUES
            ('support-a','Support A','support','{}'),('cashier','Cashier','letan','{}'),
            ('director','Director','giamdoc','{}'),('custom','Custom','warehouse','{}'),
            ('off','Off','support','{}'),('tech','Tech','nhanvien','{}')"""))
        state = {'assignments': {'cashier': 'thungan', 'off': 'inactive', 'tech': 'support'},
                 'departments': {'warehouse': {'name': 'Kho', 'active': True, 'salary_mode': 'hourly'},
                                 'inactive': {'name': 'Inactive', 'active': False, 'salary_mode': 'monthly'}}}
        conn.execute(text("INSERT INTO vera_app_setting VALUES ('payroll','hr_registry',CAST(:state AS jsonb))"), {'state': json.dumps(state)})
        assert [r['username'] for r in schedule._employee_catalog(conn, 'support')] == ['support-a']
        assert [r['username'] for r in schedule._employee_catalog(conn, 'thungan')] == ['cashier']
        assert schedule._employee_catalog(conn, 'letan') == []
        assert schedule._employee_catalog(conn, 'inactive') == []
        roster = {r['username']: r for r in attendance._active_roster(conn)}
        assert all(roster[name]['hc_checkout_eligible'] for name in ('support-a', 'cashier', 'director', 'custom'))
        assert not roster['off']['hc_checkout_eligible']
        assert not roster['tech']['hc_checkout_eligible']
        aliases, roles = _eligible_aliases(conn)
        assert aliases['director'] == 'director' and roles['director'] == 'giamdoc'
        assert aliases['custom'] == 'custom' and roles['custom'] == 'warehouse'


def test_new_department_metadata_requires_explicit_feature_and_has_no_invented_shift(database):
    app = FastAPI()
    identity = SimpleNamespace(role='quanly', employee_username='manager')
    allowed = {'work_schedule_letan'}
    schedule.install_work_schedule_routes(app, engine_instance=lambda: database,
        current_identity=lambda: identity, feature_allowed=lambda conn, ident, feature: feature in allowed)
    endpoint = next(route.endpoint for route in app.routes if route.path == '/v2/work-schedule/departments')
    assert endpoint(identity)['departments'] == [{'code': 'letan', 'label': 'Lễ tân', 'mode': 'shift'}]
    allowed.add('work_schedule_hc')
    catalog = {item['code']: item for item in endpoint(identity)['departments']}
    assert catalog['support']['mode'] == catalog['thungan']['mode'] == catalog['giamdoc']['mode'] == 'time'
    assert 'leader' not in catalog and 'nhanvien' not in catalog and 'admin' not in catalog


from test_notification_schema_locking import database as blank_database


def test_new_hc_schedule_write_validates_membership_and_keeps_cas(blank_database):
    from fastapi import HTTPException
    import pytest
    with blank_database.begin() as conn:
        conn.execute(text("CREATE TABLE vera_app_setting(category text, setting_key text, value_json jsonb)"))
        conn.execute(text("CREATE TABLE employees(username text PRIMARY KEY, full_name text, role text, payload jsonb DEFAULT '{}'::jsonb)"))
        conn.execute(text("INSERT INTO employees VALUES ('hc','HC','support','{}'), ('tech','Tech','nhanvien','{}')"))
    identity = SimpleNamespace(role='admin', employee_username='operator')
    app = FastAPI()
    schedule.install_work_schedule_routes(app, engine_instance=lambda: blank_database,
        current_identity=lambda: identity, feature_allowed=lambda *_: True)
    save = next(route.endpoint for route in app.routes if route.path == '/v2/work-schedule' and 'PUT' in route.methods)
    row = schedule.ScheduleWriteRow(work_date=date(2026, 10, 1), employee_username='hc',
        department='support', shift_code='Giờ làm', start_time='09:00', end_time='17:00', expected_revision=0)
    first = save(schedule.ScheduleSave(rows=[row]), identity)
    assert first['saved'] == 1
    with pytest.raises(HTTPException) as error:
        save(schedule.ScheduleSave(rows=[row]), identity)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        save(schedule.ScheduleSave(rows=[row.model_copy(update={'employee_username':'tech'})]), identity)
    assert error.value.status_code == 403
    with blank_database.connect() as conn:
        stored = conn.execute(text('SELECT employee_username, employee_name, department, start_time, end_time FROM vera_work_schedule')).mappings().one()
        assert dict(stored) == {'employee_username':'hc','employee_name':'HC','department':'support','start_time':'09:00','end_time':'17:00'}

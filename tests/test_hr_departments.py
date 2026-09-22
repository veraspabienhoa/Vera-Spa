from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_web_v2_hr as hr
import vera_web_v2_payroll as payroll
import vera_web_v2_department_payroll as department_payroll


@pytest.fixture
def setup(monkeypatch):
    saved = {}
    people = [{'username': 'cashier', 'full_name': 'Thu Ngân A', 'role': 'letan', 'employment_status': 'Đang làm việc'}]

    class Connection:
        def execute(self, query, params=None):
            sql = str(query)
            if 'pg_advisory' in sql:
                return None
            if 'FROM employees' in sql:
                return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: deepcopy(people)))
            raise AssertionError(sql)

    conn = Connection()

    class Engine:
        @contextmanager
        def connect(self):
            yield conn

        @contextmanager
        def begin(self):
            before = deepcopy(saved)
            try:
                yield conn
            except Exception:
                saved.clear(); saved.update(before)
                raise

    monkeypatch.setattr(payroll, '_setting', lambda conn, key, default: deepcopy(saved.get(key, default)))
    monkeypatch.setattr(payroll, '_put_setting', lambda conn, key, value, actor: saved.update({key: deepcopy(value)}))
    identity = SimpleNamespace(role='admin', employee_username='admin')
    app = FastAPI()
    hr.install_hr_routes(app, engine_instance=Engine, current_identity=lambda: identity, identity_type=SimpleNamespace)
    return TestClient(app), saved, people, identity, conn


def save(client, code, mode, revision=0, **extra):
    return client.put('/v2/hr/departments', json={'code': code, 'name': code, 'salary_mode': mode, 'revision': revision, **extra})


def test_cashier_department_does_not_change_receptionist_permissions(setup):
    client, saved, people, _, conn = setup
    assert client.put('/v2/hr/employees/cashier/department', json={'department': 'thungan', 'revision': 0}).status_code == 200
    result = client.get('/v2/hr').json()
    assert result['employees'][0]['department'] == 'thungan'
    assert result['employees'][0]['role'] == 'letan'
    assert people[0]['role'] == 'letan'
    # An authorization-role change cannot change an already assigned department.
    hr.preserve_employee_department(conn, 'cashier', 'letan', 'admin')
    people[0]['role'] = 'quanly'
    assert client.get('/v2/hr').json()['employees'][0]['department'] == 'thungan'


def test_legacy_role_edit_pins_old_department(setup):
    client, _, people, _, conn = setup
    hr.preserve_employee_department(conn, 'cashier', 'letan', 'admin')
    people[0]['role'] = 'quanly'
    assert client.get('/v2/hr').json()['employees'][0]['department'] == 'letan'


def test_only_admin_can_manage_or_read_hr(setup):
    client, saved, _, identity, _ = setup
    identity.role = 'letan'
    assert client.get('/v2/hr').status_code == 403
    assert save(client, 'new', 'hourly').status_code == 403
    assert client.put('/v2/hr/employees/cashier/department', json={'department':'thungan','revision':0}).status_code == 403
    assert client.request('DELETE', '/v2/hr/departments/letan', json={'revision':0}).status_code == 403
    assert saved == {}


def test_cannot_delete_occupied_department_and_stale_writes_are_rejected(setup):
    client, saved, _, _, _ = setup
    assert client.request('DELETE', '/v2/hr/departments/letan', json={'revision':0}).status_code == 409
    assert save(client, 'warehouse', 'monthly', creating=True).status_code == 200
    assert save(client, 'warehouse', 'tip', 0).status_code == 409
    assert saved[hr.KEY]['departments']['warehouse']['salary_mode'] == 'monthly'
    assert client.request('DELETE', '/v2/hr/departments/warehouse', json={'revision':1}).status_code == 200
    assert not client.get('/v2/hr').json()['departments']['warehouse']['active']
    assert save(client, 'warehouse', 'hourly', 2).status_code == 409


@pytest.mark.parametrize('mode', ['hourly', 'monthly', 'tip'])
def test_new_department_supports_each_pay_mode(setup, mode):
    client, _, _, _, conn = setup
    assert save(client, 'new_team', mode, creating=True).status_code == 200
    assert hr.departments(conn)['new_team']['salary_mode'] == mode
    assert ('new_team' in hr.admin_departments(conn)) == (mode != 'tip')
    if mode == 'tip':
        with pytest.raises(Exception) as exc:
            department_payroll._settings(conn, 'new_team')
        assert exc.value.status_code == 400
    else:
        cfg = department_payroll._settings(conn, 'new_team')['config']
        assert cfg['calculation_mode'] == mode
        cfg.update(rate_ca1=30_000)
        result = department_payroll._recalculate({'base_salary':7_800_000, 'work_days':13, 'hours_ca1':8}, cfg)
        assert result['salary'] == (3_900_000 if mode == 'monthly' else 240_000)


def test_mode_change_keeps_existing_payroll_history_intact(setup):
    client, saved, _, _, conn = setup
    history = [{'rows':[{'employee_username':'cashier','net_salary':7_800_000}]}]
    saved['department_payroll_combined_history'] = deepcopy(history)
    assert save(client, 'letan', 'monthly').status_code == 200
    assert department_payroll._settings(conn, 'letan')['config']['calculation_mode'] == 'monthly'
    assert saved['department_payroll_combined_history'] == history


def test_reject_invalid_mode_duplicate_name_and_code(setup):
    client, _, _, _, _ = setup
    assert save(client, 'new', 'invalid').status_code == 422
    assert save(client, 'bad-code', 'hourly').status_code == 422
    assert save(client, 'new', 'hourly', name='Lễ tân').status_code == 409
    assert save(client, 'letan', 'monthly', creating=True).status_code == 409


def test_moved_employee_keeps_original_schedule_hours():
    from datetime import date
    totals = department_payroll._schedule_totals([{
        'work_date':date(2026,9,22), 'employee_username':'cashier', 'schedule_department':'letan',
        'shift_code':'Ca 2',
    }], 'cashier', 'thungan', {'letan':{'Ca 2':{'start':'17:00','end':'01:00'}}},
        department_payroll.DEFAULT_CONFIG['support'], lambda value: str(value or '').lower())
    assert totals['minutes_ca2_before_22'] == 300
    assert totals['minutes_ca2_after_22'] == 180

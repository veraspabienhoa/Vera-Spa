"""Mixed-version payroll requests fail closed across rollout and rollback."""
from contextlib import contextmanager
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

import vera_web_v2_department_payroll as dep

OLD = '/v2/department-payroll'
NEW = '/v2/department-payroll-v2'


class Identity(BaseModel):
    employee_username: str = 'admin'
    role: str = 'admin'


class Database:
    @contextmanager
    def begin(self):
        yield self

    connect = begin

    def execute(self, *args, **kwargs):
        return None


def installed_app():
    app = FastAPI()
    dep.install_department_payroll_routes(app, engine_instance=Database,
        current_identity=Identity, require_feature=lambda *args: None,
        identity_type=Identity, norm=lambda value: str(value or '').casefold())
    return app


def test_versioned_routes_have_identical_handlers_permissions_and_models():
    app = installed_app()
    legacy = [route for route in app.routes if route.path.startswith(OLD + '/')]
    versioned = [route for route in app.routes if route.path.startswith(NEW + '/')]
    assert len(legacy) == len(versioned) == 19
    for route in legacy:
        alias = next(r for r in versioned if r.path == route.path.replace(OLD, NEW, 1) and r.methods == route.methods)
        assert alias.endpoint is route.endpoint
        assert alias.response_model == route.response_model
        if route.body_field is not None:
            assert alias.body_field.field_info.annotation is route.body_field.field_info.annotation
        else:
            assert alias.body_field is None


@pytest.mark.parametrize('prefix', [OLD, NEW])
def test_settings_capability_and_config_revision_are_atomic(monkeypatch, prefix):
    statements = []
    monkeypatch.setattr(Database, 'execute', lambda self, sql, *args: statements.append(str(sql)))
    monkeypatch.setattr(dep.hr, 'admin_departments', lambda conn: {'letan': {'name': 'Lễ tân', 'salary_mode': 'hourly'}})
    monkeypatch.setattr(dep, '_employee_settings_snapshot', lambda conn: ({}, {}, 4))
    monkeypatch.setattr(dep, '_salary_config_tables', lambda *args: {})
    monkeypatch.setattr(dep, '_salary_employee_catalog', lambda *args: [])
    snapshots = []
    def snapshot(conn, key, default):
        snapshots.append(key)
        return {'rate_ca1': 32123}, 9
    monkeypatch.setattr(dep, '_setting_snapshot', snapshot)
    def other_setting(conn, key, default):
        assert not key.endswith('_config'), 'configuration value must share its revision read'
        return default
    monkeypatch.setattr(dep.payroll, '_setting', other_setting)
    with TestClient(installed_app()) as client:
        response = client.get(prefix + '/settings')
    assert response.status_code == 200
    payload = response.json()
    assert payload['hc_payroll_contract'] == 1
    assert payload['employee_config_revision'] == 4
    assert payload['departments']['letan']['config_revision'] == 9
    assert payload['departments']['letan']['config']['rate_ca1'] == 32123
    assert snapshots == ['department_letan_config']
    assert any('pg_advisory_xact_lock_shared' in statement for statement in statements)


MUTATIONS = [
    ('PUT', '/settings/employees', {}),
    ('PUT', '/settings/letan', {'config': {}, 'email_template': {'subject': 'Subject', 'body': 'Body'}}),
    ('PUT', '/combined/draft', {'month': '2026-10', 'rows': [{}]}),
    ('DELETE', '/combined/draft?month=2026-10', None),
    ('POST', '/combined/history/saved/open', None),
    ('POST', '/combined/complete', {'month': '2026-10', 'rows': [{}]}),
    ('PUT', '/draft', {'month': '2026-10', 'department': 'letan', 'rows': [{}]}),
    ('POST', '/save', {'month': '2026-10', 'department': 'letan', 'rows': [{}]}),
]


@pytest.mark.parametrize('method,suffix,payload', MUTATIONS)
@pytest.mark.parametrize('prefix', [OLD, NEW])
def test_old_clients_missing_revisions_cannot_write(monkeypatch, prefix, method, suffix, payload):
    writes = []
    monkeypatch.setattr(dep, '_employee_settings_snapshot', lambda conn: ({'a': {'rate_ca1': 32123}}, {}, 2))
    monkeypatch.setattr(dep, '_setting_snapshot', lambda *args: ([{'id': 'saved', 'month': '2026-10'}], 2))
    monkeypatch.setattr(dep.payroll, '_put_setting', lambda *args: writes.append(args))
    with TestClient(installed_app()) as client:
        response = client.request(method, prefix + suffix, json=payload)
    assert response.status_code == 409, response.text
    assert writes == []


@pytest.mark.parametrize('suffix,method', [
    ('/settings/employees', 'PUT'), ('/settings/letan', 'PUT'),
    ('/combined/draft', 'PUT'), ('/combined/draft', 'DELETE'),
    ('/combined/history/saved/open', 'POST'), ('/combined/complete', 'POST'),
    ('/combined/calculate', 'GET'), ('/calculate', 'GET'),
    ('/combined/export.xlsx', 'POST'), ('/combined/export.pdf', 'POST'),
    ('/combined/export.png', 'POST'), ('/export.xlsx', 'POST'),
    ('/email', 'POST'), ('/draft', 'PUT'), ('/save', 'POST'),
])
def test_versioned_requests_cannot_reach_old_backend_after_cached_capability(suffix, method):
    # Reproduce the destructive old source-only transport semantics. A previous
    # capability read from another/new worker cannot make these new paths exist.
    old_app = FastAPI()
    original = {'a': {'rate_ca1': 32123}, 'b': {'default_base_salary': 7800000}}
    stored = deepcopy(original)
    class OldConfigBody(BaseModel):
        rows: list[dict] = []
    @old_app.put(OLD + '/settings/employees')
    def unsafe_old_save(body: OldConfigBody):
        stored.clear()
        stored.update({row['employee_username']: row for row in body.rows})
        return {'ok': True}
    new_payload = {'salary_sources': [{'employee_username': 'a', 'salary_source': 'attendance'}], 'expected_revision': 2}
    with TestClient(old_app) as client:
        response = client.request(method, NEW + suffix, json=new_payload)
        assert response.status_code == 404
        assert stored == original
        # Control proves this representative baseline really would erase rates
        # if a client ever fell back to the legacy mutation URL.
        assert client.put(OLD + '/settings/employees', json=new_payload).status_code == 200
        assert stored == {}


def test_versioned_department_settings_requires_and_advances_its_revision(monkeypatch):
    writes, statements = [], []
    monkeypatch.setattr(Database, 'execute', lambda self, sql, *args: statements.append(str(sql)))
    monkeypatch.setattr(dep, '_setting_snapshot', lambda *args: ({'rate_ca1': 27000}, 2))
    monkeypatch.setattr(dep, '_settings', lambda *args: {'config': dep.DEFAULT_CONFIG['letan']})
    monkeypatch.setattr(dep.payroll, '_put_setting', lambda conn, key, value, actor: writes.append((key, value, actor)))
    body = {'config': {'rate_ca1': 34567}, 'email_template': {'subject': 'Subject', 'body': 'Body'}, 'expected_revision': 2}
    with TestClient(installed_app()) as client:
        assert client.put(NEW + '/settings/letan', json={**body, 'expected_revision': 1}).status_code == 409
        assert writes == []
        response = client.put(NEW + '/settings/letan', json=body)
    assert response.status_code == 200
    assert response.json()['config_revision'] == 3
    assert len(writes) == 3 and writes[0][1]['rate_ca1'] == 34567
    assert any("pg_advisory_xact_lock(hashtext('vera:department-employee-salary'))" in statement for statement in statements)

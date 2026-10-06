from contextlib import contextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pytest
import vera_web_v2_department_payroll as dep

class Identity(BaseModel):
    employee_username: str = 'admin'

class Database:
    @contextmanager
    def begin(self):
        yield self

def route(monkeypatch, allowed=True):
    writes = []
    def permission(conn, ident, feature):
        assert feature == 'payroll_save'
        if not allowed:
            raise HTTPException(403, 'Denied')
    monkeypatch.setattr(dep.payroll, '_put_setting', lambda conn, key, value, actor: writes.append((key, value, actor)))
    app = FastAPI()
    dep.install_department_payroll_routes(app, engine_instance=Database, current_identity=Identity,
        require_feature=permission, identity_type=Identity, norm=lambda v: str(v).casefold())
    endpoint = next(r.endpoint for r in app.routes if r.path == '/v2/department-payroll/combined/draft' and 'DELETE' in r.methods)
    return endpoint, writes

def test_delete_only_selected_month_draft(monkeypatch):
    endpoint, writes = route(monkeypatch)
    assert endpoint('2026-10', Identity())['ok']
    assert writes == [('department_payroll_combined_draft_2026-10', [], 'admin')]
    with pytest.raises(HTTPException):
        endpoint('invalid', Identity())
    assert len(writes) == 1

def test_delete_requires_save_permission(monkeypatch):
    endpoint, writes = route(monkeypatch, False)
    with pytest.raises(HTTPException) as error:
        endpoint('2026-10', Identity())
    assert error.value.status_code == 403
    assert writes == []

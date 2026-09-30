from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import text
import pytest

from vera_live_tour_leave_queue_policy import REASONS, install_routes, load_policy
from test_live_tour_resource_postgres import database


class Identity(BaseModel):
    role: str = 'admin'
    employee_username: str = 'Admin Test'


def client_for(database, identity):
    app = FastAPI()
    install_routes(app, engine_instance=lambda: database, current_identity=lambda: identity,
                   require_feature=lambda conn, ident, feature: None, identity_type=Identity)
    return TestClient(app)


@pytest.mark.parametrize('role', ['letan', 'quanly', 'leader', 'nhanvien'])
def test_non_admin_cannot_change_queue_policy(role):
    client = client_for(None, Identity(role=role))
    response = client.put('/v2/rules/live-tour-leave-queue', json={'enabled': False, 'reasons': [], 'expected_revision': 0})
    assert response.status_code == 403


def test_admin_save_readback_conflict_and_invalid_reason(database):
    with database.begin() as conn:
        conn.execute(text('ALTER TABLE vera_app_setting ADD COLUMN source text, ADD COLUMN updated_by text, ADD COLUMN created_at timestamptz'))
        initial = load_policy(conn)
    assert initial['enabled'] and initial['reasons'] == list(REASONS) and initial['revision'] == 0
    client = client_for(database, Identity())
    payload = {'enabled': True, 'reasons': [REASONS[5]], 'expected_revision': 0}
    saved = client.put('/v2/rules/live-tour-leave-queue', json=payload)
    assert saved.status_code == 200 and saved.json()['revision'] == 1
    with database.connect() as conn:
        assert load_policy(conn)['reasons'] == [REASONS[5]]
    assert client.put('/v2/rules/live-tour-leave-queue', json=payload).status_code == 409
    assert client.put('/v2/rules/live-tour-leave-queue', json={**payload, 'reasons': ['Unknown'], 'expected_revision': 1}).status_code == 422
    assert client.put('/v2/rules/live-tour-leave-queue', json={**payload, 'reasons': [REASONS[0]] * 2, 'expected_revision': 1}).status_code == 422
    off = client.put('/v2/rules/live-tour-leave-queue', json={'enabled': False, 'reasons': [], 'expected_revision': 1})
    assert off.status_code == 200 and off.json()['enabled'] is False and off.json()['revision'] == 2
    all_on = client.put('/v2/rules/live-tour-leave-queue', json={'enabled': True, 'reasons': list(REASONS), 'expected_revision': 2})
    assert all_on.status_code == 200 and all_on.json()['reasons'] == list(REASONS)

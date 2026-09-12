from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import RouteEngine, RouteIdentity, employee, state_with


class Identity(RouteIdentity):
    role: str


@pytest.mark.parametrize('role,expected', [('admin', 200), ('letan', 409), ('quanly', 409)])
@pytest.mark.parametrize('action', ['start', 'start_room'])
def test_only_admin_can_start_leave_employee_without_shift(monkeypatch, role, expected, action):
    state = state_with(employee('e1', 'An'))
    state['employees'][0].update(work_status='Nghỉ phép', shift='', status='Đang chờ',
                                 room='1.1', service='Body 90', duration=90)
    monkeypatch.setattr(live, '_read_state', lambda *args, **kwargs: (deepcopy(state), 1))
    written = []
    monkeypatch.setattr(live, '_write_state', lambda conn, value, revision, actor: written.append(deepcopy(value)) or 2)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine,
        current_identity=lambda: Identity(role=role), require_feature=lambda *args: None,
        feature_allowed=lambda *args: True, identity_type=Identity)
    payload = {'_admin_start': True, **({'employee_id': 'e1'} if action == 'start' else {'room': '1'})}
    response = TestClient(app).post('/v2/live-tour/action', json={
        'action': action, 'payload': payload, 'expected_revision': 1, 'idempotency_key': f'{role}-{action}'})
    assert response.status_code == expected, response.text
    if expected == 200:
        worker = written[-1]['employees'][0]
        assert worker['status'] == 'Đang thực hiện'
        assert worker['tour_count'] == 1
        assert worker['shift'] == '' and worker['work_status'] == 'Nghỉ phép'
    else:
        assert not written

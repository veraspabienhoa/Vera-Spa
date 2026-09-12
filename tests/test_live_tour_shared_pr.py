from copy import deepcopy

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with, RouteEngine
from test_live_tour_daily_settings import route_client
from test_live_tour_server_only import SettingsDatabase
from test_live_tour_safety import api_client


def shared_state():
    state = state_with(employee('e1', 'An'), employee('e2', 'Bình'), employee('e3', 'Chi'))
    live._apply_action(state, 'booking', {'employee_id': 'e1', 'room': '2.1', 'service': 'VIP 90 PR'}, 'reception', NOW)
    return state


@pytest.mark.parametrize('role,expected', [('letan', 200), ('admin', 200), ('quanly', 200), ('nhanvien', 403), ('leader', 403)])
def test_shared_pr_booking_requires_operator_role_and_preserves_bed_lock(monkeypatch, role, expected):
    _, shared = api_client(monkeypatch, shared_state())
    client = route_client(RouteEngine(), role=role)
    body = {'action': 'booking', 'expected_revision': shared['revision'], 'idempotency_key': 'share-room-2',
            'payload': {'employee_id': 'e2', 'room': '2.2', 'service': 'VIP 90 PR', 'share_private_room': True}}
    response = client.post('/v2/live-tour/action', json=body)
    assert response.status_code == expected, response.text
    if expected == 200:
        state = shared['state']
        assert state['employees'][0]['private_room_share_group'] == state['employees'][1]['private_room_share_group']
        live._apply_action(state, 'start_room', {'room': '2'}, 'reception', NOW)
        assert all(row['status'] == 'Đang thực hiện' for row in state['employees'][:2])
        before = deepcopy(state)
        with pytest.raises(HTTPException):
            live._apply_action(state, 'booking', {**body['payload'], 'employee_id': 'e3'}, 'reception', NOW)
        assert state == before
        live._apply_action(state, 'finish_room', {'room': '2'}, 'reception', NOW)
        assert all(not row.get('private_room_share_group') for row in state['employees'][:2])


def test_pr_default_stays_locked_until_explicit_shared_booking():
    state = shared_state()
    with pytest.raises(HTTPException):
        live._apply_action(state, 'booking', {'employee_id': 'e2', 'room': '2.2', 'service': 'VIP 90 PR'}, 'reception', NOW)


def test_multi_booking_cannot_bypass_role_gate():
    db = SettingsDatabase(shared_state())
    client = route_client(db, role='nhanvien')
    response = client.post('/v2/live-tour/action', json={'action': 'multi_booking', 'expected_revision': db.revision,
        'idempotency_key': 'share-room-multi', 'payload': {'bookings': [
            {'employee_id': 'e2', 'room': '2.2', 'service': 'VIP 90 PR', 'share_private_room': True}]}})
    assert response.status_code == 403

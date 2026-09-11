"""Room transitions select current services on the server and remain atomic."""
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteEngine, RouteIdentity, employee, state_with
from test_live_tour_safety import api_client


def act(state, action, payload):
    return live._apply_action(state, action, payload, 'operator', NOW)


def mixed_room():
    state = state_with(*(employee(f'e{i}', f'Nhân viên {i}') for i in range(1, 8)))
    assignments = [('e1', '1.1', False), ('e2', '1.2', False), ('e3', '1.3', True),
                   ('e4', '2.1', False), ('e5', '2.2', True), ('e6', '1.4', True)]
    for identifier, room, start in assignments:
        act(state, 'booking', {'employee_id': identifier, 'room': room, 'service': 'Body 90',
                              'start_now': start, 'customer_name': f'Khách {identifier}'})
    act(state, 'complete', {'employee_id': 'e6'})
    state['employees'][1]['hidden'] = True
    return state


def test_start_room_selects_waiting_only_including_hidden_and_ignores_unrelated_selection():
    state = mixed_room()
    before = deepcopy(state)
    result = act(state, 'start_room', {'room': '1', 'employee_ids': ['e4']})
    assert result['count'] == 2
    assert {item['employee']['id'] for item in result['items']} == {'e1', 'e2'}
    assert all(worker['status'] == 'Đang thực hiện' and worker['tour_count'] == 1 for worker in state['employees'][:2])
    assert state['employees'][1]['hidden'] is True
    assert state['employees'][2:] == before['employees'][2:]
    assert act(state, 'finish_room', {'room': '1'})['count'] == 3
    assert all(not worker['service'] for worker in state['employees'][:3])


def test_finish_room_preserves_waiting_other_rooms_and_separate_customer_receipts():
    state = mixed_room()
    act(state, 'start', {'employee_id': 'e2'})
    # Existing work remains finishable if a worker later leaves the roster.
    state['employees'][2]['roster_eligible'] = False
    before = deepcopy(state)
    result = act(state, 'finish_room', {'room': '1'})
    assert result['count'] == 2 and len(state['pending']) == 2
    assert {row['customer_name'] for row in state['pending']} == {'Khách e2', 'Khách e3'}
    assert all(len(row['entries']) == 1 for row in state['pending'])
    assert {row['entries'][0]['employee_id'] for row in state['pending']} == {'e2', 'e3'}
    for index in [0, 3, 4, 5, 6]:
        assert state['employees'][index] == before['employees'][index]
    assert all(not state['employees'][index]['service'] for index in [1, 2])
    assert state['employees'][1]['tour_count'] == 1
    assert live._room_available(state, '1.2') and live._room_available(state, '1.3')


def test_room_start_rolls_back_every_employee_when_one_cannot_start():
    state = mixed_room()
    state['employees'][1]['work_status'] = 'Nghỉ'
    before = deepcopy(state)
    with pytest.raises(HTTPException, match='Đi làm'):
        act(state, 'start_room', {'room': '1'})
    assert state == before


@pytest.mark.parametrize('action', ['start_room', 'finish_room'])
def test_room_requests_reject_empty_unknown_and_no_matching_work_without_changes(action):
    state = mixed_room()
    for room in ['', 'Không tồn tại', '19']:
        before = deepcopy(state)
        with pytest.raises(HTTPException):
            act(state, action, {'room': room})
        assert state == before


def test_room_counts_and_actions_use_configured_area_names_not_bed_prefixes():
    state = mixed_room()
    for room in state['rooms']:
        if room['name'] in {'1.1', '1.2'}:
            room.update(area_name='Phòng Sen', area_id='sen', area_kind='room')
    result = act(state, 'start_room', {'room': 'phòng sen'})
    assert result['count'] == 2 and result['room'] == 'Phòng Sen'
    assert live._room_action_counts(state)['Phòng Sen'] == {'waiting': 0, 'doing': 2}
    assert act(state, 'finish_room', {'room': 'Phòng Sen'})['count'] == 2
    assert state['employees'][2]['status'] == 'Đang thực hiện'


@pytest.mark.parametrize('action', ['start_room', 'finish_room'])
def test_http_retries_do_not_change_new_work_in_the_same_room(monkeypatch, action):
    state = mixed_room()
    client, shared = api_client(monkeypatch, state)
    body = {'action': action, 'payload': {'room': '1'}, 'expected_revision': 1, 'idempotency_key': 'room-transition-once'}
    first = client.post('/v2/live-tour/action', json=body)
    assert first.status_code == 200, first.text
    # A later assignment must not be picked up by replaying the old room request.
    if action == 'finish_room':
        act(shared['state'], 'booking', {'employee_id': 'e3', 'room': '1.3', 'service': 'Body 90', 'start_now': True})
    else:
        act(shared['state'], 'booking', {'employee_id': 'e7', 'room': '1.5', 'service': 'Body 90'})
    shared['revision'] += 1
    before = deepcopy(shared)
    assert client.post('/v2/live-tour/action', json=body).json()['duplicate'] is True
    assert shared == before
    assert action in live.PROTECTED_IDEMPOTENCY_ACTIONS
    without_key = {key: value for key, value in body.items() if key != 'idempotency_key'}
    assert client.post('/v2/live-tour/action', json=without_key).status_code == 400
    stale = {**body, 'idempotency_key': 'another-room-request'}
    assert client.post('/v2/live-tour/action', json=stale).status_code == 409
    assert shared == before


def test_room_http_requires_operate_and_redacts_customer_data(monkeypatch):
    client, shared = api_client(monkeypatch, mixed_room())
    grants = {'live_tour_view', 'live_tour_payment'}
    def require(_conn, _identity, feature):
        if feature not in grants:
            raise HTTPException(403, 'Permission denied')
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=require, feature_allowed=lambda _conn, _ident, feature: feature in grants, identity_type=RouteIdentity)
    client = TestClient(app)
    for action in ['start_room', 'finish_room']:
        assert client.post('/v2/live-tour/action', json={'action': action, 'payload': {'room': '1'},
            'expected_revision': 1, 'idempotency_key': 'denied-' + action}).status_code == 403
    assert client.get('/v2/live-tour').json()['room_action_counts'] == {}
    grants.remove('live_tour_payment')
    grants.add('live_tour_operate')
    data = client.get('/v2/live-tour').json()
    assert data['room_action_counts']['1'] == {'waiting': 2, 'doing': 1}
    assert len([record for record in data['records'] if record.get('Phòng', '').startswith('1.')]) == 3
    # Completion clears the room cell, while retaining the invoice source.
    assert len([record for record in data['state']['employees'] if record.get('room', '').startswith('1.')]) == 4
    unpaid = [record for record in data['records'] if record.get('_payment_pending')]
    assert unpaid and all(record['Phòng'] == '' and record['Dịch vụ'] == '' for record in unpaid)
    response = client.post('/v2/live-tour/action', json={'action': 'finish_room', 'payload': {'room': '1'},
        'expected_revision': shared['revision'], 'idempotency_key': 'allowed-room-finish'})
    assert response.status_code == 200, response.text
    assert response.json()['result']['count'] == 1
    assert 'Khách e3' not in response.text
    assert response.json()['pending_payments'] == []


def test_frontend_room_handler_keeps_full_area_name_and_does_not_send_selected_employee_ids():
    root = Path(__file__).parents[1]
    script = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source = fs.readFileSync('src/pages/LiveTourPage.jsx', 'utf8');
const handler = source.slice(source.indexOf('const runRoomAction = async'), source.indexOf('const roomServiceActions =')).replace('const runRoomAction = ', '').trim();
const calls = [], notices = [];
const run = new Function('executeAction', 'setSelectedRoomKey', 'setNotice', 'areaKey', 'areaLabel', `return ${handler}`)(
  async (...args) => { calls.push(args); return {result:{count:2}} }, () => {}, value => notices.push(value), value => value, value => value);
await run('Phòng Sen', 'start_room');
await run('VIP 19', 'finish_room');
assert.deepEqual(calls, [['start_room', {room:'Phòng Sen'}, []], ['finish_room', {room:'VIP 19'}, []]]);
assert.match(notices[1], /chờ thanh toán/);
'''
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=root / 'web-v2', capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

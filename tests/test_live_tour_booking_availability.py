"""Bookings may reserve a soon-free bed, while starts still require a free place."""
from copy import deepcopy
from datetime import timedelta
import json
import re
from pathlib import Path
import subprocess

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from vera_web_v2_live_tour_availability import place_status
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_safety import api_client


def fixture(service='Body 90', room='1.1'):
    state = state_with(*(employee(f'e{i}', f'Nhân viên {i}') for i in range(1, 5)))
    live._booking(state, {'employee_id': 'e1', 'room': room, 'service': service, 'start_now': True}, NOW)
    return state


def act(state, action, payload, now=NOW):
    return live._apply_action(state, action, payload, 'operator', now)


def status(state, room, now, *, service='Body 90', employee_id='e2', reserve=True):
    worker = live._employee(state, employee_id)
    return place_status(live._booking_occupancy(state, now), room=room, group=live._catalog_room_group(state, room),
        private=live._catalog_private_service(state, service), candidate=live._booking_occupant(state, worker, now), now=now, reserve=reserve)


@pytest.mark.parametrize('remaining,allowed', [(1801, False), (1800, False), (1799, True), (60, True), (0, True), (-60, True)])
def test_exact_30_minute_boundary_and_countdown(remaining, allowed):
    state = fixture()
    now = NOW + timedelta(seconds=5400 - remaining)
    check = status(state, '1.1', now)
    assert check['allowed'] is allowed and check['can_start'] is False
    assert check['remaining_seconds'] == remaining
    before = deepcopy(state)
    if allowed:
        act(state, 'booking', {'employee_id': 'e2', 'room': '1.1', 'service': 'Body 90'}, now)
        assert state['employees'][1]['status'] == 'Đang chờ'
    else:
        with pytest.raises(HTTPException):
            act(state, 'booking', {'employee_id': 'e2', 'room': '1.1', 'service': 'Body 90'}, now)
        assert state == before


@pytest.mark.parametrize('mutation', [{'status': 'Đang chờ'}, {'duration': None}, {'started_at': ''}])
def test_waiting_and_unknown_time_are_not_bookable(mutation):
    state = fixture()
    state['employees'][0].update(mutation)
    assert status(state, '1.1', NOW + timedelta(minutes=89))['allowed'] is False
    assert status(state, '1.2', NOW)['allowed'] is True


def test_reservation_cannot_start_early_or_accept_another_waiting_booking():
    state = fixture()
    now = NOW + timedelta(minutes=61)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'booking', {'employee_id': 'e2', 'room': '1.1', 'service': 'Body 90', 'start_now': True}, now)
    assert state == before
    act(state, 'booking', {'employee_id': 'e2', 'room': '1.1', 'service': 'Body 90'}, now)
    for action, payload in [('start', {'employee_id': 'e2'}), ('start_room', {'room': '1'}),
                            ('booking', {'employee_id': 'e3', 'room': '1.1', 'service': 'Body 90'})]:
        before = deepcopy(state)
        with pytest.raises(HTTPException):
            act(state, action, payload, now)
        assert state == before
    act(state, 'finish_to_pending', {'employee_id': 'e1'}, now)
    assert state['employees'][1]['status'] == 'Đang chờ' and len(state['pending']) == 1
    act(state, 'start', {'employee_id': 'e2'}, now)
    assert state['employees'][1]['status'] == 'Đang thực hiện'
    assert state['employees'][1]['tour_count'] == 1


@pytest.mark.parametrize('service', ['VIP 90 PR', 'P.Riêng tùy chỉnh'])
def test_private_service_applies_threshold_to_every_bed_in_its_area(service):
    state = state_with(*(employee(f'e{i}', f'Nhân viên {i}') for i in range(1, 5)))
    if service != 'VIP 90 PR':
        act(state, 'service_upsert', {'name': service, 'duration': 90, 'price': 100000, 'private': True})
    act(state, 'booking', {'employee_id': 'e1', 'room': '19.1', 'service': service, 'start_now': True})
    assert status(state, '19.2', NOW + timedelta(minutes=60))['allowed'] is False
    now = NOW + timedelta(minutes=61)
    assert status(state, '19.2', now)['remaining_seconds'] == 1740
    assert status(state, '1.1', now)['can_start'] is True
    act(state, 'booking', {'employee_id': 'e2', 'room': '19.2', 'service': 'Body 90'}, now)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'start', {'employee_id': 'e2'}, now)
    assert state == before
    act(state, 'finish_to_pending', {'employee_id': 'e1'}, now)
    act(state, 'start', {'employee_id': 'e2'}, now)


def test_selecting_private_service_waits_for_all_existing_room_services():
    state = fixture(room='19.1')
    act(state, 'booking', {'employee_id': 'e2', 'room': '19.2', 'service': 'Body 90', 'start_now': True}, NOW + timedelta(minutes=20))
    assert status(state, '19.3', NOW + timedelta(minutes=61), service='VIP 90 PR', employee_id='e3')['allowed'] is False
    now = NOW + timedelta(minutes=81)
    assert status(state, '19.3', now, service='VIP 90 PR', employee_id='e3')['remaining_seconds'] == 1740
    act(state, 'booking', {'employee_id': 'e3', 'room': '19.3', 'service': 'VIP 90 PR'}, now)
    assert status(state, '19.4', now, employee_id='e4')['allowed'] is False
    act(state, 'finish_to_pending', {'employee_id': 'e1'}, now)
    with pytest.raises(HTTPException):
        act(state, 'start', {'employee_id': 'e3'}, now)
    act(state, 'finish_to_pending', {'employee_id': 'e2'}, now)
    act(state, 'start', {'employee_id': 'e3'}, now)


def test_service_edits_preserve_existing_queue_and_do_not_expand_into_reserved_beds():
    state = fixture()
    now = NOW + timedelta(minutes=61)
    act(state, 'booking', {'employee_id': 'e2', 'room': '1.1', 'service': 'Body 90'}, now)
    act(state, 'add_minutes', {'employee_id': 'e1', 'minutes': 30}, now)
    # An already accepted reservation remains editable if the first service is extended.
    assert status(state, '1.1', now)['allowed'] is True
    assert status(state, '1.1', now)['remaining_seconds'] == 3540
    act(state, 'update_booking', {'employee_id': 'e2', 'room': '1.1', 'service': 'Body 90', 'note': 'Lịch đã giữ'}, now)
    act(state, 'add_service', {'employee_id': 'e1', 'service': 'Body 90'}, now)
    assert state['employees'][1]['note'] == 'Lịch đã giữ'
    act(state, 'booking', {'employee_id': 'e3', 'room': '1.2', 'service': 'Body 90'}, now)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'update_booking', {'employee_id': 'e1', 'room': '1.2', 'service': 'Body 90'}, now)
    assert state == before
    with pytest.raises(HTTPException):
        act(state, 'update_booking', {'employee_id': 'e1', 'room': '1.1', 'service': 'VIP 90 PR'}, now)
    assert state == before
    act(state, 'finish_to_pending', {'employee_id': 'e1', 'room': '1.1', 'service_items': [{'service_id': next(row['id'] for row in state['services'] if row['name'] == 'Body 90'), 'quantity': 1}]}, now)
    assert state['employees'][1]['status'] == 'Đang chờ'


def test_occupancy_includes_hidden_work_but_never_customer_identity():
    state = fixture()
    state['employees'][0].update(hidden=True, roster_eligible=False, customer_name='Private customer', customer_phone='Private phone')
    data = live._state_response(state, 1, NOW, can_operate=True, can_payment=False)
    assert data['booking_occupancy'][0]['employee_id'] == 'e1'
    assert 'Private' not in json.dumps(data['booking_occupancy'])
    assert live._state_response(state, 1, NOW, can_operate=False)['booking_occupancy'] == []


def test_frontend_options_match_server_and_count_down_while_dialog_stays_open():
    state = fixture()
    for room in state['rooms']:
        if room['name'].startswith('1.'):
            room.update(area_name='Phòng Sen', area_id='sen')
    data = live._state_response(state, 1, NOW, can_operate=True)
    root = Path(__file__).parents[1]
    script = r'''
import assert from 'node:assert/strict';
import {bookingPlaces, bookingPlaceNotice, isPrivateCatalogService} from './src/lib/liveTourAvailability.js';
const data = DATA, start = Date.parse(START);
let options = bookingPlaces(data, {employeeId:'e2',now:start+3600000});
assert.equal(options.some(row=>row.name==='1.1'),false);
assert.equal(options.some(row=>row.name==='1.2'),true);
options = bookingPlaces(data, {employeeId:'e2',now:start+3601000});
assert.equal(options.find(row=>row.name==='1.1').can_start,false);
assert.match(options.find(row=>row.name==='1.1').notice,/29 phút 59 giây/);
assert.equal(bookingPlaces(data,{employeeId:'e2',now:start+3600000,privateService:true}).some(row=>row.name==='1.2'),false);
assert.equal(bookingPlaces(data,{employeeId:'e2',now:start+3601000,privateService:true}).some(row=>row.name==='1.2'),true);
assert.equal(bookingPlaces(data,{employeeId:'e2',now:start+3601000,reserve:false}).some(row=>row.name==='1.1'),false);
assert.equal(isPrivateCatalogService({name:'Tùy chỉnh',private:true}),true);
assert.equal(isPrivateCatalogService({name:'Body P.Riêng'}),true);
assert.match(bookingPlaceNotice({can_start:false,remaining_seconds:-5}),/đã hết giờ/);
data.booking_occupancy[0].status='Đang chờ';
assert.equal(bookingPlaces(data,{employeeId:'e2',now:start+5400000}).some(row=>row.name==='1.1'),false);
'''.replace('DATA', json.dumps(data, ensure_ascii=False)).replace('START', json.dumps(NOW.isoformat()))
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=root / 'web-v2', capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_http_prevents_stale_client_from_reserving_bed_after_another_waiting_booking(monkeypatch):
    state = fixture()
    state['employees'][0]['started_at'] = live._iso(NOW - timedelta(minutes=61))
    client, shared = api_client(monkeypatch, state)
    # Using an overdue deadline keeps this fixture independent of the wall clock.
    first = client.post('/v2/live-tour/action', json={'action': 'booking', 'payload': {'employee_id': 'e2', 'room': '1.1', 'service': 'Body 90'}, 'expected_revision': 1, 'idempotency_key': 'first-reservation'})
    assert first.status_code == 200, first.text
    before = deepcopy(shared)
    second = client.post('/v2/live-tour/action', json={'action': 'booking', 'payload': {'employee_id': 'e3', 'room': '1.1', 'service': 'Body 90'}, 'expected_revision': 1, 'idempotency_key': 'second-reservation'})
    assert second.status_code == 409 and shared == before


def test_room_single_click_only_opens_details_and_double_click_requires_operate():
    root = Path(__file__).parents[1]
    source = (root / 'web-v2/src/pages/LiveTourPage.jsx').read_text()
    handlers = re.search(r'className="tour-room-booking-button" onClick=\{(.*?)\} onDoubleClick=\{(.*?)\} title=', source)
    assert handlers
    script = r'''
import assert from 'node:assert/strict';
const single = SINGLE, double = DOUBLE;
const calls = [];
const handler = (code, allowed=true, busy=false) => new Function('setSelectedRoomKey','setError','setBookingContext','key','canOperate','actionBusy','areaLabel','room',`return (${code})`)(
  key=>calls.push(['details',key]),()=>{},context=>calls.push(['booking',context.roomLabel]),'19',allowed,busy,value=>value,'VIP 19');
handler(single)();
assert.deepEqual(calls,[['details','19']]);
handler(double)();
assert.deepEqual(calls,[['details','19'],['booking','VIP 19']]);
handler(double,false)();handler(double,true,true)();
assert.equal(calls.length,2);
'''.replace('SINGLE', json.dumps(handlers.group(1))).replace('DOUBLE', json.dumps(handlers.group(2)))
    result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

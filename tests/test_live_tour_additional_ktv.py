from copy import deepcopy
from datetime import timedelta

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from vera_live_tour_resource_store import action_resources


def setup_booking():
    state = state_with(employee('e1', 'An'), employee('e2', 'Bình'), employee('e3', 'Chi'))
    main = next(row for row in state['services'] if row['name'] == 'VIP 90 PR')
    state['services'].append({'id': 'extra-ktv', 'name': 'Thêm 1 KTV', 'duration': 30,
                              'price': 100000, 'active': True})
    payload = {'employee_id': 'e1', 'additional_ktv_id': 'e2', 'room': '19.1', 'request': '',
               'service_items': [{'service_id': main['id'], 'quantity': 1},
                                 {'service_id': 'extra-ktv', 'quantity': 1}]}
    return state, payload


def test_pair_duration_revenue_room_and_roundtrip():
    state, payload = setup_booking()
    live._apply_action(state, 'booking', payload, 'admin', NOW)
    main, extra, other = state['employees']
    assert main['duration'] == extra['duration'] == 90
    assert extra['service_price'] == 100000
    assert main['service_price'] == next(row['price'] for row in state['services'] if row['name'] == 'VIP 90 PR')
    assert len(main['service_items']) == len(extra['service_items']) == 1
    assert main['room'] == extra['room'] == '19.1'
    restored = live._normalize_state(deepcopy(state), NOW)
    assert restored['employees'][0]['additional_ktv_id'] == 'e2'
    live._apply_action(state, 'start', {'employee_ids': ['e1', 'e2']}, 'admin', NOW)
    assert all(row['status'] == 'Đang thực hiện' for row in state['employees'][:2])
    with pytest.raises(HTTPException):
        live._booking(state, {**payload, 'employee_id': 'e3', 'service_items': payload['service_items'][:1]}, NOW)
    live._apply_action(state, 'complete', {'employee_ids': ['e1', 'e2']}, 'admin', NOW + timedelta(minutes=90))
    result = live._apply_action(state, 'move_pending', {'employee_ids': ['e1', 'e2']}, 'admin', NOW + timedelta(minutes=90))
    entries = result['pending']['entries']
    assert len(entries) == 2
    assert {row['employee_id']: row['price'] for row in entries}['e2'] == 100000
    assert all(row['duration'] == 90 for row in entries)


@pytest.mark.parametrize('case', ['missing', 'same', 'busy', 'leave', 'no_shift', 'break', 'quantity', 'no_main'])
def test_invalid_pair_is_atomic(case):
    state, payload = setup_booking()
    if case == 'missing': payload.pop('additional_ktv_id')
    if case == 'same': payload['additional_ktv_id'] = 'e1'
    if case == 'busy': state['employees'][1]['service'] = 'Already busy'
    if case == 'leave': state['employees'][1]['work_status'] = 'Nghỉ phép'
    if case == 'no_shift': state['employees'][1]['shift'] = ''
    if case == 'break': state['employees'][1]['break_started_at'] = NOW.isoformat()
    if case == 'quantity': payload['service_items'][1]['quantity'] = 2
    if case == 'no_main': payload['service_items'] = payload['service_items'][1:]
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, 'booking', payload, 'admin', NOW)
    assert state == before


def test_edit_reassign_remove_and_lock_both_old_and_new_workers():
    state, payload = setup_booking()
    live._apply_action(state, 'booking', payload, 'admin', NOW)
    payload['additional_ktv_id'] = 'e3'
    keys = action_resources(state, 'update_booking', payload, 'request')
    assert all(('live_tour_employee', key) in keys for key in ['e1', 'e2', 'e3'])
    live._apply_action(state, 'update_booking', payload, 'admin', NOW)
    assert not state['employees'][1]['service']
    assert state['employees'][2]['duration'] == 90
    payload['service_items'][0]['quantity'] = 2
    live._apply_action(state, 'update_booking', payload, 'admin', NOW)
    assert state['employees'][0]['duration'] == state['employees'][2]['duration'] == 180
    payload['service_items'] = payload['service_items'][:1]
    live._apply_action(state, 'update_booking', payload, 'admin', NOW)
    assert not state['employees'][2]['service']
    assert not state['employees'][0]['additional_ktv_id']


def test_started_helper_cannot_be_removed_and_completed_main_keeps_pr_locked():
    state, payload = setup_booking()
    live._apply_action(state, 'booking', payload, 'admin', NOW)
    live._apply_action(state, 'start', {'employee_ids': ['e1', 'e2']}, 'admin', NOW)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, 'update_booking', {**payload, 'additional_ktv_id': 'e3'}, 'admin', NOW)
    assert state == before
    live._apply_action(state, 'complete', {'employee_id': 'e1'}, 'admin', NOW + timedelta(minutes=90))
    with pytest.raises(HTTPException):
        live._booking(state, {'employee_id': 'e3', 'room': '19.2',
                             'service_items': payload['service_items'][:1]}, NOW)
    assert live._state_response(state, 1, NOW)['room_assignments'][0]['paired_booking_id']


def test_existing_unsplit_addon_is_moved_once_to_selected_worker():
    state, payload = setup_booking()
    live._booking(state, payload, NOW)
    assert state['employees'][0]['duration'] == 120
    old_total = state['employees'][0]['service_price']
    live._apply_action(state, 'update_booking', payload, 'admin', NOW)
    assert state['employees'][0]['duration'] == state['employees'][1]['duration'] == 90
    assert sum(row.get('service_price') or 0 for row in state['employees']) == old_total
    live._apply_action(state, 'update_booking', payload, 'admin', NOW)
    assert sum(row.get('service_price') or 0 for row in state['employees']) == old_total

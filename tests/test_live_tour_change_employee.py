from copy import deepcopy
from datetime import timedelta

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_cancel_booking import waiting


def running(request=''):
    source, target = waiting(), employee('e2', 'Bình')
    for key in ('combo_purchase_id', 'combo_reserved_units', 'combo_reserved_components'):
        source.pop(key, None)
    source.update(request=request, customer_id='customer1', customer_name='Khách', note='Giữ nguyên',
                  service_items=[{'service_id': 's1', 'quantity': 1}])
    target.update(tour_count=7, appointment='Hẹn riêng', last_assignment_display={'TG bắt đầu thực hiện': '11/09/2026 09:00:00'})
    state = state_with(source, target, employee('e3', 'Chi'))
    live._apply_action(state, 'start', {'employee_id': 'e1'}, 'admin', NOW)
    return state, source, target


def change(state, seconds=300, source='e1', target='e2'):
    return live._apply_action(state, 'change_employee', {'employee_id': source, 'target_employee_id': target}, 'admin', NOW + timedelta(seconds=seconds))


@pytest.mark.parametrize('seconds', [0, 599, 600])
@pytest.mark.parametrize('request_kind,counter', [('', 'tour_count'), ('YC', 'request_count')])
def test_change_in_first_ten_minutes_restores_order_and_moves_counter(seconds, request_kind, counter):
    state, source, target = running(request_kind)
    source.update(combo_purchase_id='c1', combo_reserved_units=1)
    booking = deepcopy(source)
    original = source['pre_start_tour_position']
    source['sort_index'] = 100
    before_target = target[counter]
    change(state, seconds)
    for key in ('booking_id', 'booked_at', 'room', 'service', 'service_items', 'service_price', 'duration', 'customer_id', 'customer_name', 'combo_purchase_id', 'combo_reserved_units', 'note', 'started_at'):
        assert target[key] == booking[key]
    assert target['status'] == 'Đang thực hiện'
    assert target[counter] == before_target + 1
    assert source[counter] == booking[counter] - 1
    assert target['appointment'] == 'Hẹn riêng'
    assert not source['room'] and not source['service'] and not source.get('combo_purchase_id')
    assert source['sort_index'] == original['sort_index']
    assert source['last_assignment_display'] == original['display']
    assert live._ordered_employees(state['employees'], NOW)[0]['id'] == 'e1'
    assert live._remaining(target, NOW + timedelta(seconds=seconds))[1] == live._remaining(booking, NOW + timedelta(seconds=seconds))[1]
    assert state['audit'][-1]['action'] == 'change_employee'


@pytest.mark.parametrize('seconds', [-1, 601, 1800])
def test_reject_time_outside_window_atomically(seconds):
    state, _, _ = running(); before = deepcopy(state)
    with pytest.raises(HTTPException): change(state, seconds)
    assert state == before


def test_waiting_and_legacy_without_snapshot_are_rejected():
    state = state_with(waiting(), employee('e2', 'Bình'))
    with pytest.raises(HTTPException): change(state)
    state['employees'][0].update(status='Đang thực hiện', started_at=live._iso(NOW))
    with pytest.raises(HTTPException): change(state)


@pytest.mark.parametrize('changes', [
    {'service': 'Body'}, {'status': 'CHO THANH TOÁN'}, {'status': 'Đang chờ'},
    {'break_started_at': live._iso(NOW)}, {'work_status': 'Nghỉ phép'},
    {'shift': ''}, {'roster_eligible': False},
])
def test_unavailable_target_does_not_mutate_booking(changes):
    state, _, target = running(); target.update(changes); before = deepcopy(state)
    with pytest.raises(HTTPException): change(state)
    assert state == before


def test_replacement_does_not_restart_window_and_restores_second_employee():
    state, _, target = running(); old_display = deepcopy(target['last_assignment_display'])
    change(state, 300)
    change(state, 500, 'e2', 'e3')
    assert target['last_assignment_display']['TG bắt đầu thực hiện'] == old_display['TG bắt đầu thực hiện']
    assert target['tour_count'] == 7
    assert state['employees'][2]['started_at'] == live._iso(NOW)
    with pytest.raises(HTTPException): change(state, 601, 'e3', 'e1')


def test_counter_rollover_does_not_restore_yesterday_counts():
    state, source, target = running()
    started = NOW.replace(hour=9, minute=55)
    source['started_at'] = live._iso(started)
    source['pre_start_tour_position']['counter_day'] = live._counter_business_date(started).isoformat()
    state['counter_business_date'] = live._counter_business_date(started).isoformat()
    live._apply_action(state, 'change_employee', {'employee_id': 'e1', 'target_employee_id': 'e2'}, 'admin', started + timedelta(minutes=6))
    assert source['tour_count'] == target['tour_count'] == 0

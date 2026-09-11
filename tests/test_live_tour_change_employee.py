from copy import deepcopy

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_cancel_booking import waiting


def test_transfer_waiting_booking_preserves_booking_and_employee_counters():
    source, target = waiting(), employee('e2', 'Bình')
    source.update(customer_id='customer1', customer_name='Khách', note='Giữ nguyên', service_items=[{'service_id': 's1', 'quantity': 1}])
    target.update(tour_count=7, appointment='Hẹn riêng')
    state = state_with(source, target)
    live._ensure_counter_day(state, NOW)
    booking = deepcopy(source)
    live._apply_action(state, 'change_employee', {'employee_id': 'e1', 'target_employee_id': 'e2'}, 'admin', NOW)
    for key in ('booking_id', 'booked_at', 'room', 'service', 'service_items', 'service_price', 'duration', 'customer_id', 'customer_name', 'combo_purchase_id', 'combo_reserved_units', 'combo_reserved_components', 'note'):
        assert target[key] == booking[key]
    assert target['tour_count'] == 7 and source['tour_count'] == 4
    assert target['appointment'] == 'Hẹn riêng'
    assert not source['room'] and not source['service'] and not source.get('combo_purchase_id')
    assert state['audit'][-1]['action'] == 'change_employee'
    assert 'change_employee' in live.IDEMPOTENCY_REQUIRED_ACTIONS
    assert live._required_action_feature('change_employee') == 'live_tour_operate'


@pytest.mark.parametrize('changes', [
    {'service': 'Body'}, {'status': 'CHO THANH TOÁN'}, {'status': 'Đang chờ'},
    {'break_started_at': live._iso(NOW)}, {'work_status': 'Nghỉ phép'},
    {'shift': ''}, {'roster_eligible': False},
])
def test_busy_or_unavailable_target_does_not_mutate_booking(changes):
    target = employee('e2', 'Bình'); target.update(changes)
    state = state_with(waiting(), target)
    live._ensure_counter_day(state, NOW); before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, 'change_employee', {'employee_id': 'e1', 'target_employee_id': 'e2'}, 'admin', NOW)
    assert state == before


def test_started_booking_and_same_employee_are_rejected():
    state = state_with(waiting(), employee('e2', 'Bình'))
    with pytest.raises(HTTPException):
        live._apply_action(state, 'change_employee', {'employee_id': 'e1', 'target_employee_id': 'e1'}, 'admin', NOW)
    state['employees'][0].update(status='Đang thực hiện', started_at=live._iso(NOW))
    live._ensure_counter_day(state, NOW); before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, 'change_employee', {'employee_id': 'e1', 'target_employee_id': 'e2'}, 'admin', NOW)
    assert state == before

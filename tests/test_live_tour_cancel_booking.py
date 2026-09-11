from copy import deepcopy

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with


def waiting(identifier='e1'):
    row = employee(identifier, identifier)
    row.update(status='Đang chờ', service='90 PR VIP', room='1.1',
               duration=90, service_price=500000, booked_at=live._iso(NOW),
               booking_id='booking-' + identifier, tour_count=4, request_count=2,
               combo_purchase_id='combo1', combo_reserved_units=1,
               combo_reserved_components=[{'component_id': 'c1', 'quantity': 1}])
    return row


def test_cancel_releases_assignment_without_changing_history_or_balance():
    state = state_with(waiting())
    live._ensure_counter_day(state, NOW)
    state['invoices'] = [{'id': 'paid1', 'total': 100000}]
    state['combo_purchases'] = [{'id': 'combo1', 'remaining': 3}]
    preserved = deepcopy({key: state[key] for key in ('invoices', 'combo_purchases', 'reports', 'pending')})
    result = live._apply_action(state, 'cancel_booking', {'employee_id': 'e1'}, 'admin', NOW)
    row = result['employee']
    assert result['cancelled_booking_id'] == 'booking-e1'
    assert row['room'] == row['service'] == row['status'] == row['booking_id'] == ''
    assert not row.get('combo_purchase_id') and not row.get('combo_reserved_units')
    assert not row.get('combo_reserved_components')
    assert row['tour_count'] == 4 and row['request_count'] == 2
    assert {key: state[key] for key in preserved} == preserved
    assert state['audit'][-1]['action'] == 'cancel_booking'
    assert 'cancel_booking' in live.IDEMPOTENCY_REQUIRED_ACTIONS
    assert live._required_action_feature('cancel_booking') == 'live_tour_operate'


@pytest.mark.parametrize('status,started', [('Đang thực hiện', live._iso(NOW)), ('CHO THANH TOÁN', ''), ('', ''), ('Đang chờ', live._iso(NOW))])
def test_cancel_rejects_non_waiting_or_started_service(status, started):
    row = waiting()
    row.update(status=status, started_at=started)
    state = state_with(row)
    live._ensure_counter_day(state, NOW)
    before = deepcopy(state)
    with pytest.raises(HTTPException) as error:
        live._apply_action(state, 'cancel_booking', {'employee_id': 'e1'}, 'admin', NOW)
    assert error.value.status_code == 409
    assert state == before


def test_batch_cancel_rolls_back_if_any_booking_started():
    a, b = waiting(), waiting('e2')
    b.update(status='Đang thực hiện', started_at=live._iso(NOW))
    state = state_with(a, b)
    live._ensure_counter_day(state, NOW)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, 'cancel_booking', {'employee_ids': ['e1', 'e2']}, 'admin', NOW)
    assert state == before
    state['employees'][1].update(status='Đang chờ', started_at='')
    result = live._apply_action(state, 'cancel_booking', {'employee_ids': ['e1', 'e2']}, 'admin', NOW)
    assert result['count'] == 2
    assert all(not row['service'] for row in state['employees'])

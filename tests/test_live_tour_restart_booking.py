from copy import deepcopy
import pytest
from fastapi import HTTPException
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with


def running(request=''):
    row = employee('e1', 'An')
    row.update(status='Đang chờ', service='Body 90', room='1.1', duration=90, request=request, booked_at=live._iso(NOW))
    state = state_with(row)
    live._ensure_counter_day(state, NOW)
    live._start_employee(state, row, NOW)
    return state, row


def test_restart_booking_returns_running_to_waiting_without_double_count():
    state, row = running()
    assert row['tour_count'] == 1
    live._apply_action(state, 'restart_booking', {'employee_id':'e1'}, 'admin', NOW)
    assert row['status'] == 'Đang chờ' and row['started_at'] == ''
    assert row['tour_count'] == 0
    live._start_employee(state, row, NOW)
    assert row['tour_count'] == 1


def test_restart_booking_request_counter_is_reversible():
    state, row = running('YC')
    assert row['request_count'] == 1
    live._apply_action(state, 'restart_booking', {'employee_id':'e1'}, 'admin', NOW)
    assert row['request_count'] == 0


def test_restart_booking_rejects_waiting():
    row = employee('e1','An'); row.update(status='Đang chờ', service='Body 90', room='1.1')
    state = state_with(row)
    with pytest.raises(HTTPException):
        live._apply_action(state, 'restart_booking', {'employee_id':'e1'}, 'admin', NOW)


def test_restart_booking_requires_admin_feature():
    assert live._required_action_feature('restart_booking') == 'live_tour_admin'

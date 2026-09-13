from copy import deepcopy
from io import BytesIO

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with


def test_booking_threshold_is_saved_and_visible_without_payment_permission():
    state = state_with(employee('e1', 'An'))
    assert live._state_response(state, 1, NOW, can_booking=True)['booking_settings']['employee_available_minutes'] == 30
    payload = {**live._default_payment_settings(), 'booking_available_minutes': 45}
    live._apply_action(state, 'payment_settings_update', payload, 'admin', NOW)
    response = live._state_response(deepcopy(state), 2, NOW, can_booking=True)
    assert response['booking_settings']['employee_available_minutes'] == 45
    assert response['payment_settings'] == {}  # No bank/TIP disclosure is needed to book.
    assert live._required_action_feature('payment_settings_update') == 'live_tour_admin'


@pytest.mark.parametrize('value', [0, -1, 181, 12.5, '45', True, None, ''])
def test_invalid_threshold_does_not_change_saved_settings(value):
    state = state_with(employee('e1', 'An'))
    before = deepcopy(state)
    with pytest.raises(HTTPException) as error:
        live._apply_action(state, 'payment_settings_update', {**live._default_payment_settings(), 'booking_available_minutes': value}, 'admin', NOW)
    assert error.value.status_code == 400
    assert state == before


def test_export_dates_are_vietnamese_without_changing_stored_values():
    state = state_with(employee('e1', 'An'))
    state['audit'] = [{'at': '2026-01-02T18:04:05+00:00', 'business_date': '2026-01-03', 'actor': 'admin', 'action': 'example', 'detail': {}}]
    before = deepcopy(state)
    content, _ = live._excel_bytes(state, 'history', NOW)
    sheet = load_workbook(BytesIO(content)).active
    assert sheet['A2'].value == '03/01/2026 01:04:05'
    assert sheet['B2'].value == '03/01/2026'
    assert state == before

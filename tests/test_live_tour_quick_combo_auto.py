"""Automatic combo redemption and live leave/check-in validation."""
from copy import deepcopy
from datetime import timedelta

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_combo_booking import setup, booking
from test_live_tour_quick_booking import scenario
from test_live_tour_server_only import SettingsDatabase, app_client


def automatic_payload(customer, purchase):
    return {'customer_id': customer['id'], 'combo_purchase_id': purchase['id'],
            'payment_method': 'COMBO', 'tip': 50000,
            'quick_booking': {'employee_id': 'e1', 'room': '1.1', 'booked_at': live._iso(NOW)}}


def test_auto_component_services_debit_once_each_without_service_input():
    state, skin, body, customer, purchase = setup()
    payload = automatic_payload(customer, purchase)
    invoice = live._apply_action(state, 'quick_checkout', payload, 'admin', NOW)['invoice']
    assert invoice['total'] == 50000
    assert {row['service_id'] for row in invoice['entries'][0]['service_items']} == {skin['id'], body['id']}
    saved = state['customers'][0]['combo_purchases'][0]
    assert saved['remaining'] == 1
    assert [part['remaining'] for part in saved['component_balances']] == [0, 1]
    assert state['employees'][0]['service'] == ''


def test_auto_services_exclude_tickets_reserved_by_other_booking():
    state, skin, body, customer, purchase = setup()
    live._apply_action(state, 'booking', booking(customer, purchase, skin, 'e2'), 'admin', NOW)
    invoice = live._apply_action(state, 'quick_checkout', automatic_payload(customer, purchase), 'admin', NOW)['invoice']
    assert [row['service_id'] for row in invoice['entries'][0]['service_items']] == [body['id']]
    assert live._available_combo(state, customer['id'], state['customers'][0]['combo_purchases'][0])['component_balances'][0]['remaining'] == 0


@pytest.mark.parametrize('problem', ['wrong_customer', 'expired', 'empty'])
def test_auto_combo_invalid_is_atomic(problem):
    state, _, _, customer, purchase = setup()
    payload = automatic_payload(customer, purchase)
    if problem == 'wrong_customer': payload['customer_id'] = 'someone-else'
    elif problem == 'expired': purchase.update(unlimited=False, expires_on='2020-01-01')
    else: purchase['remaining'] = 0
    before = deepcopy(state)
    with pytest.raises(HTTPException): live._apply_action(state, 'quick_checkout', payload, 'admin', NOW)
    assert state == before


def test_generic_combo_uses_one_ticket_without_guessing_catalog_service():
    state, _, _, customer, purchase = setup()
    purchase.pop('component_balances')
    purchase['combo_name'] = 'Body & Chăm sóc'
    invoice = live._apply_action(state, 'quick_checkout', automatic_payload(customer, purchase), 'admin', NOW)['invoice']
    assert invoice['entries'][0]['service'] == 'Vé combo · Body & Chăm sóc'
    assert invoice['entries'][0]['service_items'] == []
    assert invoice['total'] == 50000
    assert state['customers'][0]['combo_purchases'][0]['remaining'] == 2


@pytest.mark.parametrize('value', [None, '', '2026-09-05'])
def test_date_always_required_even_for_steam(value):
    state, payload = scenario()
    state['services'][0]['name'] = 'Xông hơi'
    payload['quick_booking']['service_items'][0]['service_id'] = state['services'][0]['id']
    if value is None: payload['quick_booking'].pop('booked_at')
    else: payload['quick_booking']['booked_at'] = value
    before = deepcopy(state)
    with pytest.raises(HTTPException): live._apply_action(state, 'quick_checkout', payload, 'admin', NOW)
    assert state == before


@pytest.mark.parametrize('mode', ['booking', 'quick_checkout'])
@pytest.mark.parametrize('change', [
    {'shift': ''}, {'work_status': 'Nghỉ phép'},
    {'shift_checkin_date': NOW.date().isoformat(), 'assigned_shift': ''},
    {'shift_checkin_date': (NOW - timedelta(days=1)).date().isoformat(), 'assigned_shift': 'Ca 1'},
])
def test_not_checked_in_cannot_book_on_server(mode, change):
    state, payload = scenario()
    state['employees'][0].update(change)
    if mode == 'booking': payload = payload['quick_booking']
    before = deepcopy(state)
    with pytest.raises(HTTPException): live._apply_action(state, mode, payload, 'admin', NOW)
    assert state == before


def test_daily_leave_changes_project_without_button_and_remove_old_reason():
    worker = employee('e1', 'An')
    worker['appointment'] = 'Khách 15h'
    db = SettingsDatabase(state_with(worker))
    _, client = app_client(db)
    initial = client.get('/v2/live-tour').json()
    db.leaves = [{'employee_name': 'An', 'leave_reason': 'Nghỉ CÓ phép'}]
    absent = client.get('/v2/live-tour').json()
    assert absent['revision'] > initial['revision']
    assert db.stored['employees'][0]['work_status'] == 'Nghỉ phép'
    assert db.stored['employees'][0]['appointment'] == 'Khách 15h · Nghỉ CÓ phép'
    assert client.get('/v2/live-tour').json()['revision'] == absent['revision']
    db.leaves[0]['leave_reason'] = 'Đi trễ CÓ phép'
    client.get('/v2/live-tour')
    assert db.stored['employees'][0]['work_status'] == 'Đi làm'
    assert db.stored['employees'][0]['appointment'] == 'Khách 15h · Đi trễ CÓ phép'
    db.leaves = []
    client.get('/v2/live-tour')
    assert db.stored['employees'][0]['appointment'] == 'Khách 15h'
    assert db.stored['employees'][0]['shift'] == ''  # A leave edit cannot fabricate check-in.

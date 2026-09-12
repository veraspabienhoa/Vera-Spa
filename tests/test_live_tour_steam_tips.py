from copy import deepcopy

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, state_with, employee


def steam_state():
    state = state_with(employee('e1', 'An'))
    service = live._apply_action(state, 'service_upsert', {'name': 'Xông hơi', 'duration': 30, 'price': 100000}, 'admin', NOW)['service']
    return state, service


def test_steam_only_needs_service_and_keeps_tours_untouched():
    state, service = steam_state()
    workers = deepcopy(state['employees'])
    result = live._apply_action(state, 'quick_checkout', {'quick_booking': {'booked_at': live._iso(NOW), 'service_items': [{'service_id': service['id'], 'quantity': 1}]}}, 'admin', NOW)
    invoice = result['invoice']
    assert invoice['total'] == 100000
    assert invoice['entries'][0]['employee_id'] == ''
    assert invoice['entries'][0]['room'] == ''
    assert state['employees'] == workers


def test_duplicate_tip_cards_are_preserved_and_summed():
    state, service = steam_state()
    state['payment_settings']['tip_cards'] = [{'id': '200k', 'name': '200.000 đ', 'amount': 200000}]
    result = live._apply_action(state, 'quick_checkout', {'tip_card_ids': ['200k', '200k'], 'quick_booking': {'booked_at': live._iso(NOW), 'service_items': [{'service_id': service['id'], 'quantity': 1}]}}, 'admin', NOW)
    assert result['invoice']['tip'] == 400000
    assert result['invoice']['total'] == 500000
    assert len(result['invoice']['tip_cards']) == 2


def test_staffed_service_still_requires_employee_and_room():
    state, service = steam_state()
    service['name'] = 'Body'
    with pytest.raises(HTTPException):
        live._apply_action(state, 'quick_checkout', {'quick_booking': {'booked_at': live._iso(NOW), 'service_items': [{'service_id': service['id'], 'quantity': 1}]}}, 'admin', NOW)


def test_steam_can_use_existing_customer_combo():
    state, service = steam_state()
    combo = live._apply_action(state, 'combo_upsert', {'name': 'Combo xông hơi', 'price': 1000000, 'components': [{'service_id': service['id'], 'quantity': 10}]}, 'admin', NOW)['combo']
    bought = live._apply_action(state, 'combo_purchase', {'customer_name': 'Khách cũ', 'combo_id': combo['id'], 'quantity': 1}, 'admin', NOW)
    invoice = live._apply_action(state, 'quick_checkout', {'customer_id': bought['customer']['id'], 'combo_purchase_id': bought['purchase']['id'], 'payment_method': 'COMBO', 'quick_booking': {'booked_at': live._iso(NOW), 'service_items': [{'service_id': service['id'], 'quantity': 1}]}}, 'admin', NOW)['invoice']
    assert invoice['total'] == 0
    assert bought['purchase']['remaining'] == 9

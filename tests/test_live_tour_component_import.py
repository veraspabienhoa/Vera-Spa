from copy import deepcopy

import pytest
from fastapi import HTTPException

from test_service_catalog import action, catalog, complete, pay
from test_live_tour_backend import employee, state_with


def test_import_single_component_eight_remaining_and_checkout():
    state = state_with(employee('e1', 'An'))
    single, _, combo = catalog(state)
    combo['components'] = [{'service_id': single['id'], 'quantity': 13}]
    combo['tickets'] = 13
    action(state, 'combo_import', {'purchases': [{'customer_name': 'Khách nhập', 'combo_id': combo['id'], 'total': 8, 'used': 0}]})
    customer = state['customers'][0]
    owned = customer['combo_purchases'][0]
    assert owned['remaining'] == 8
    assert owned['component_balances'][0]['remaining'] == 8
    assert not state['invoices'] and not state['reports']
    complete(state, single, customer)
    pay(state, customer, owned)
    assert owned['remaining'] == 7
    assert owned['component_balances'][0]['remaining'] == 7


def test_import_multiple_components_preserves_each_balance():
    state = state_with(employee('e1', 'An'))
    single, other, combo = catalog(state)
    action(state, 'combo_import', {'purchases': [{'customer_name': 'Khách nhập', 'combo_id': combo['id'], 'total': 8, 'used': 0,
        'component_remaining': {single['id']: 3, other['id']: 5}}]})
    customer = state['customers'][0]
    owned = customer['combo_purchases'][0]
    complete(state, single, customer, extra=other)
    pay(state, customer, owned)
    assert [part['remaining'] for part in owned['component_balances']] == [2, 4]
    assert owned['remaining'] == 6


def test_missing_component_counts_rejected_atomically():
    state = state_with()
    _, _, combo = catalog(state)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, 'combo_import', {'purchases': [{'customer_name': 'Khách nhập', 'combo_id': combo['id'], 'total': 8}]})
    assert state == before

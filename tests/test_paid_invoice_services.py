"""Paid service corrections keep the original financial and work evidence."""
from copy import deepcopy

import pytest
from fastapi import HTTPException
from test_live_tour_invoice_permissions import paid_state, combo_pending, scoped_client, post
from test_service_catalog import action


def test_replace_paid_services_reprices_reports_and_audits_original():
    state, paid = paid_state()
    service = next(row for row in state['services'] if row['name'] != paid['entries'][0]['service'] and row.get('active', True))
    before = deepcopy(state)
    changed = action(state, 'paid_invoice_update', {'invoice_id': paid['id'], 'reason': 'Chọn đúng dịch vụ',
        'entries': [{'index': 0, 'service_items': [{'service_id': service['id'], 'quantity': 2}]}]})['invoice']
    assert changed['entries'][0]['service_items'][0]['quantity'] == 2
    assert changed['subtotal'] == service['price'] * 2
    assert changed['total'] == changed['subtotal'] + paid['tip']
    assert state['reports'][0]['service'] == changed['entries'][0]['service']
    assert state['reports'][0]['total'] == changed['total']
    for key in ('id', 'bill_no', 'customer_id', 'created_at', 'business_date'):
        assert changed[key] == paid[key]
    for key in ('employee_id', 'employee_name', 'room', 'completed_at', 'completion_delta_minutes', 'note'):
        assert changed['entries'][0].get(key) == paid['entries'][0].get(key)
    assert state['employees'] == before['employees']
    assert state['customers'] == before['customers']
    assert state['invoice_changes'][-1]['before'] == paid
    assert state['invoice_changes'][-1]['reports_before'] == before['reports']


@pytest.mark.parametrize('items', [[], None, [{'service_id': 'missing', 'quantity': 1}],
    [{'service_id': 'missing', 'quantity': True}], [{'service_id': 'missing', 'quantity': 31}]])
def test_invalid_service_selection_leaves_entire_state_unchanged(items):
    state, paid = paid_state()
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, 'paid_invoice_update', {'invoice_id': paid['id'], 'reason': 'x', 'entries': [{'index': 0, 'service_items': items}]})
    assert state == before


def test_inactive_service_cannot_replace_paid_service():
    state, paid = paid_state()
    service = state['services'][0]
    service['active'] = False
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, 'paid_invoice_update', {'invoice_id': paid['id'], 'reason': 'x',
            'entries': [{'index': 0, 'service_items': [{'service_id': service['id'], 'quantity': 1}]}]})
    assert state == before


def test_combo_service_change_cannot_silently_change_ticket_ledger():
    state, skin, body, customer, owned, pending = combo_pending()
    paid = action(state, 'checkout', {'pending_id': pending['id'], 'combo_purchase_id': owned['id'], 'payment_method': 'COMBO'})['invoice']
    for target in (paid, state['invoices'][0]):
        before = deepcopy(state)
        with pytest.raises(HTTPException, match='đối soát vé'):
            action(state, 'paid_invoice_update', {'invoice_id': target['id'], 'reason': 'x',
                'entries': [{'index': 0, 'service_items': [{'service_id': body['id'], 'quantity': 1}]}]})
        assert state == before


def test_paid_service_edit_keeps_http_permissions_and_revision(monkeypatch):
    state, paid = paid_state()
    service = state['services'][0]
    payload = {'invoice_id': paid['id'], 'reason': 'Đổi dịch vụ',
        'entries': [{'index': 0, 'service_items': [{'service_id': service['id'], 'quantity': 1}]}]}
    client, shared = scoped_client(monkeypatch, state, {'live_tour_paid_invoice_view'})
    assert post(client, shared, 'paid_invoice_update', payload).status_code == 403
    assert shared['state'] == state
    client, shared = scoped_client(monkeypatch, state, {'live_tour_paid_invoice_view', 'live_tour_paid_invoice_edit'})
    assert post(client, shared, 'paid_invoice_update', payload, expected_revision=0).status_code == 409
    assert shared['state'] == state
    assert post(client, shared, 'paid_invoice_update', payload).status_code == 200


def test_report_editor_receives_catalog_but_read_only_does_not(monkeypatch):
    state, _ = paid_state()
    client, _ = scoped_client(monkeypatch, state, {'live_tour_reports_view', 'live_tour_reports_edit', 'live_tour_paid_invoice_view'})
    response = client.get('/v2/live-tour/reports?tab=revenue')
    assert response.status_code == 200
    assert {row['id'] for row in response.json()['services']} == {row['id'] for row in state['services']}
    client, _ = scoped_client(monkeypatch, state, {'live_tour_reports_view'})
    assert client.get('/v2/live-tour/reports?tab=revenue').json()['services'] == []

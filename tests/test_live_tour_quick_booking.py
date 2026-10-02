"""Direct quick invoices are atomic, canonical priced, and isolated from live tours."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteEngine, RouteIdentity, employee, state_with
from test_live_tour_safety import api_client
from test_live_tour_combo_booking import setup as combo_setup, booking


def scenario():
    state = state_with(employee("e1", "An"))
    service = next(item for item in state["services"] if item["name"] == "Body 90")
    service["price"] = 250_000
    payload = {"payment_method": "TIỀN MẶT", "tip": 50_000, "quick_booking": {
        "employee_id": "e1", "room": "1.1", "service_items": [{"service_id": service["id"], "quantity": 1}],
        "booked_at": live._iso(NOW - timedelta(hours=2)), "correction_reason": "Nhập bổ sung",
    }}
    return state, payload


def test_direct_quick_invoice_preserves_current_assignment_and_uses_catalog_price():
    state, payload = scenario()
    state["employees"][0].update(service="Đang phục vụ khách khác", status="Đang thực hiện", room="2.1", appointment="18:00")
    original_staff = deepcopy(state["employees"])
    payload.update(total=1, subtotal=1, customer_name="Khách A", customer_phone="0901234567")
    invoice = live._apply_action(state, "quick_checkout", payload, "letan", NOW)["invoice"]
    assert (invoice["subtotal"], invoice["tip"], invoice["total"]) == (250_000, 50_000, 300_000)
    assert invoice["effective_at"] == payload["quick_booking"]["booked_at"]
    assert invoice["recorded_at"] == live._iso(NOW)
    assert invoice["source"] == "quick_booking"
    assert invoice["entries"][0]["employee_name"] == "An"
    assert invoice["entries"][0]["room"] == "1.1"
    assert state["reports"][0]["effective_at"] == invoice["effective_at"]
    assert state["employees"] == original_staff


@pytest.mark.parametrize("change", [
    {"booked_at": "not-a-date"}, {"booked_at": "2026-09-05"},
    {"booked_at": live._iso(NOW + timedelta(minutes=1))},
    {"booked_at": live._iso(NOW - timedelta(days=1)), "correction_reason": ""},
    {"employee_id": "missing"}, {"room": "missing"},
    {"price": 1}, {"service_items": [{"service_id": "missing", "quantity": 1}]},
    {"service_items": [{"service_id": "missing", "quantity": True}]},
])
def test_invalid_quick_input_does_not_change_any_state(change):
    state, payload = scenario()
    payload["quick_booking"].update(change)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, "quick_checkout", payload, "admin", NOW)
    assert state == before


@pytest.mark.parametrize("source", [{"employee_id": "e1"}, {"employee_ids": ["e1"]}, {"pending_id": "p1"}])
def test_manual_booking_cannot_be_mixed_with_existing_payable_source(source):
    state, payload = scenario()
    state["pending"] = [{"id": "p1", "entries": []}]
    payload.update(source)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, "quick_checkout", payload, "admin", NOW)
    assert state == before


def test_direct_input_is_rejected_by_normal_checkout():
    state, payload = scenario()
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, "checkout", payload, "admin", NOW)
    assert state == before


@pytest.mark.parametrize("denied,past,expected", [
    ("live_tour_booking", False, ["live_tour_payment", "live_tour_booking"]),
    ("live_tour_quick_checkout_backdate", True, ["live_tour_payment", "live_tour_booking", "live_tour_view", "live_tour_quick_checkout_backdate"]),
])
def test_required_permissions_are_checked_before_reading_state(monkeypatch, denied, past, expected):
    state, payload = scenario()
    booked = datetime.now(live.VN_TZ) - timedelta(days=1 if past else 0, minutes=1)
    payload["quick_booking"]["booked_at"] = live._iso(booked)
    checked, reads = [], []
    def require(_conn, _identity, feature):
        checked.append(feature)
        if feature == denied:
            raise HTTPException(403, "Không có quyền")
    monkeypatch.setattr(live, "_read_state", lambda *_args, **_kwargs: reads.append(True))
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=require, feature_allowed=lambda *_args: False, identity_type=RouteIdentity)
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/v2/live-tour/action")
    with pytest.raises(HTTPException) as error:
        endpoint(live.LiveTourAction(action="quick_checkout", payload=payload, idempotency_key="quick-permission-1", expected_revision=1), RouteIdentity())
    assert error.value.status_code == 403 and checked == expected and not reads


def test_direct_quick_invoice_replay_charges_once_and_stale_write_fails(monkeypatch):
    state, payload = scenario()
    payload["quick_booking"]["booked_at"] = live._iso(datetime.now(live.VN_TZ) - timedelta(minutes=1))
    client, shared = api_client(monkeypatch, state)
    body = {"action": "quick_checkout", "payload": payload, "idempotency_key": "quick-replay-unique", "expected_revision": 1}
    first = client.post("/v2/live-tour/action", json=body)
    second = client.post("/v2/live-tour/action", json=body)
    assert first.status_code == second.status_code == 200
    assert second.json()["duplicate"] is True
    assert first.json()["result"]["invoice"]["id"] == second.json()["result"]["invoice"]["id"]
    assert len(shared["state"]["invoices"]) == len(shared["state"]["reports"]) == 1
    before = deepcopy(shared)
    body["idempotency_key"] = "quick-stale-unique"
    assert client.post("/v2/live-tour/action", json=body).status_code == 409
    assert shared == before


def test_direct_combo_invoice_cannot_consume_tickets_reserved_by_live_booking():
    state, skin, body, customer, owned = combo_setup()
    live._apply_action(state, "booking", booking(customer, owned, skin), "admin", NOW)
    payload = {"payment_method": "COMBO", "customer_id": customer["id"], "combo_purchase_id": owned["id"],
        "quick_booking": {"employee_id": "e1", "room": "2.1", "booked_at": live._iso(NOW),
                          "service_items": [{"service_id": skin["id"], "quantity": 3}]}}
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, "quick_checkout", payload, "admin", NOW)
    assert state == before
    payload["quick_booking"]["service_items"] = [{"service_id": body["id"], "quantity": 1}]
    invoice = live._apply_action(state, "quick_checkout", payload, "admin", NOW)["invoice"]
    assert invoice["total"] == 0
    assert state["employees"] == before["employees"]
    assert len(state["combo_usage"]) == 1


def test_pending_invoice_retains_booking_and_execution_times():
    state, payload = scenario()
    worker = state["employees"][0]
    worker.update(service="Body 90", room="1.1", status="CHO THANH TOÁN", service_price=250_000,
                  booked_at=live._iso(NOW - timedelta(hours=2)), started_at=live._iso(NOW - timedelta(hours=1)), completed_at=live._iso(NOW))
    expected = {key: worker[key] for key in ("booked_at", "started_at", "completed_at")}
    pending = live._apply_action(state, "move_pending", {"employee_id": "e1"}, "admin", NOW)["pending"]
    assert {key: pending["entries"][0][key] for key in expected} == expected


def test_quick_invoice_accepts_more_than_thirty_extra_services_and_keeps_live_assignment():
    state, payload = scenario()
    service = next(row for row in state['services'] if row['name'] == 'Mua thêm 30')
    service.update(price=10_000, ticket_units=0)
    payload['quick_booking']['extra_service_items'] = [{'service_id': service['id'], 'quantity': 40}]
    before = deepcopy(state['employees'])
    invoice = live._apply_action(state, 'quick_checkout', payload, 'letan', NOW)['invoice']
    assert invoice['subtotal'] == 650_000
    assert invoice['total'] == 700_000
    assert invoice['entries'][0]['service_items'][-1]['quantity'] == 40
    assert state['employees'] == before


def test_component_combo_charges_extra_catalog_services_without_extra_combo_debit():
    state, skin, body, customer, owned = combo_setup()
    extra = next(row for row in state['services'] if row['name'] == 'Mua thêm 30')
    extra.update(price=30_000, ticket_units=0)
    payload = {'payment_method': 'COMBO', 'customer_id': customer['id'], 'combo_purchase_id': owned['id'],
               'quick_booking': {'employee_id': 'e1', 'room': '1.1', 'booked_at': live._iso(NOW),
                                 'service_items': [{'service_id': body['id'], 'quantity': 1}],
                                 'extra_service_items': [{'service_id': extra['id'], 'quantity': 35}]}}
    invoice = live._apply_action(state, 'quick_checkout', payload, 'letan', NOW)['invoice']
    assert invoice['subtotal'] == invoice['total'] == 1_050_000
    assert invoice['combo_units'] == 1
    assert owned['remaining'] == 2


def test_generic_combo_ticket_charges_extra_services_and_debits_only_base_ticket():
    state, payload = scenario()
    extra = next(row for row in state['services'] if row['name'] == 'Mua thêm 30')
    extra.update(price=30_000, ticket_units=0)
    state['customers'] = [{'id': 'customer', 'name': 'Khách', 'combo_purchases': [{'id': 'purchase', 'combo_name': 'Combo', 'remaining': 4, 'total': 4, 'used': 0}]}]
    payload.update(payment_method='COMBO', customer_id='customer', combo_purchase_id='purchase')
    payload['quick_booking'].update(service_items=[], extra_service_items=[{'service_id': extra['id'], 'quantity': 2}])
    invoice = live._apply_action(state, 'quick_checkout', payload, 'letan', NOW)['invoice']
    assert invoice['subtotal'] == 60_000 and invoice['total'] == 110_000
    assert invoice['combo_units'] == 1
    assert state['customers'][0]['combo_purchases'][0]['remaining'] == 3
    assert state['reports'][-1]['combo_units'] == 1


def test_quick_extra_invalid_quantity_rolls_back_invoice_and_combo():
    state, payload = scenario()
    payload['quick_booking']['extra_service_items'] = [{'service_id': state['services'][0]['id'], 'quantity': 1.5}]
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, 'quick_checkout', payload, 'letan', NOW)
    assert state == before


def test_quick_backdate_grant_cannot_enter_two_days_ago(monkeypatch):
    state, payload = scenario()
    payload['quick_booking']['booked_at'] = live._iso(datetime.now(live.VN_TZ) - timedelta(days=2))
    identity = RouteIdentity(role='letan')
    checked, reads = [], []
    app = FastAPI()
    monkeypatch.setattr(live, '_read_state', lambda *_args, **_kwargs: reads.append(True))
    live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=lambda: identity,
        require_feature=lambda _conn, _ident, feature: checked.append(feature), feature_allowed=lambda *_args: True, identity_type=RouteIdentity)
    endpoint = next(route.endpoint for route in app.routes if getattr(route, 'path', '') == '/v2/live-tour/action')
    with pytest.raises(HTTPException) as error:
        endpoint(live.LiveTourAction(action='quick_checkout', payload=payload, idempotency_key='quick-too-old-date'), identity)
    assert error.value.status_code == 403
    assert 'live_tour_quick_checkout_backdate' in checked and not reads


def test_granted_quick_yesterday_booking_keeps_its_invoice_date(monkeypatch):
    state, payload = scenario()
    booked = (datetime.now(live.VN_TZ) - timedelta(days=1)).replace(hour=15, minute=0, second=0)
    payload['quick_booking'].update(booked_at=live._iso(booked), correction_reason='Nhập bổ sung hôm qua')
    client, shared = api_client(monkeypatch, state)
    response = client.post('/v2/live-tour/action', json={'action':'quick_checkout', 'payload':payload, 'idempotency_key':'quick-yesterday-granted', 'expected_revision':1})
    assert response.status_code == 200
    assert shared['state']['invoices'][-1]['effective_at'] == live._iso(booked)
    assert shared['state']['invoices'][-1]['correction_reason'] == 'Nhập bổ sung hôm qua'


def test_quick_accepts_more_than_thirty_distinct_extra_services():
    state, payload = scenario()
    extras = [{'id':f'extra-{i}', 'name':f'Dịch vụ thêm {i}', 'price':1000, 'duration':60, 'ticket_units':0, 'active':True} for i in range(31)]
    state['services'].extend(extras)
    payload['quick_booking']['extra_service_items'] = [{'service_id':row['id'], 'quantity':1} for row in extras]
    invoice = live._apply_action(state, 'quick_checkout', payload, 'letan', NOW)['invoice']
    assert len(invoice['entries'][0]['service_items']) == 32
    assert invoice['subtotal'] == 281_000


def test_report_metrics_projection_exposes_invoice_totals_without_customer_details():
    state, payload = scenario()
    payload['discount'] = 10_000
    invoice = live._apply_action(state, 'quick_checkout', payload, 'letan', NOW)['invoice']
    reports = live._report_rows_with_combo_kind(state)
    assert reports[-1]['invoice_total'] == invoice['total']
    assert reports[-1]['invoice_discount'] == 10_000
    assert 'entries' not in reports[-1]

"""Purchased tickets are reserved at booking and debited exactly once at checkout."""
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteEngine, RouteIdentity, employee, state_with
from test_live_tour_safety import api_client
from test_live_tour_server_only import SettingsDatabase, app_client
from test_service_catalog import action, catalog, purchase


def setup():
    state = state_with(employee("e1", "An"), employee("e2", "Bình"))
    skin, body, combo = catalog(state)
    customer, owned = purchase(state, combo)
    return state, skin, body, customer, owned


def booking(customer, owned, service, worker="e1", quantity=1):
    return {"employee_id": worker, "room": "1.1" if worker == "e1" else "2.1",
            "customer_id": customer["id"], "combo_purchase_id": owned["id"],
            "service_items": [{"service_id": service["id"], "quantity": quantity}]}


def available(state, customer, owned):
    return live._available_combo(state, customer["id"], owned)


def test_booking_reserves_component_and_total_but_does_not_charge():
    state, skin, body, customer, owned = setup()
    before = deepcopy(owned), deepcopy(state["invoices"])
    action(state, "booking", booking(customer, owned, skin))
    assert owned == before[0] and state["invoices"] == before[1]
    assert available(state, customer, owned)["remaining"] == 2
    assert [part["remaining"] for part in available(state, customer, owned)["component_balances"]] == [0, 2]
    snapshot = deepcopy(state)
    with pytest.raises(HTTPException, match="chỉ còn 0 lượt"):
        action(state, "booking", booking(customer, owned, skin, "e2"))
    assert state == snapshot
    action(state, "booking", booking(customer, owned, body, "e2"))
    assert available(state, customer, owned)["remaining"] == 1


@pytest.mark.parametrize("problem", ["zero", "over_quantity", "wrong_service", "wrong_customer", "expired", "future"])
def test_invalid_combo_booking_is_rejected_without_assigning_employee(problem):
    state, skin, _, customer, owned = setup()
    payload = booking(customer, owned, skin)
    if problem == "zero":
        owned["remaining"] = 0
    elif problem == "over_quantity":
        payload["service_items"][0]["quantity"] = 2
    elif problem == "wrong_service":
        payload["service_items"][0]["service_id"] = next(row["id"] for row in state["services"] if row["name"] == "Body 70")
    elif problem == "wrong_customer":
        state["customers"].append({"id": "other", "name": "Other", "combo_purchases": []})
        payload["customer_id"] = "other"
    elif problem == "expired":
        owned["expires_on"] = "2026-09-04"
    else:
        owned["starts_on"] = "2026-09-06"
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "booking", payload)
    assert state == before


def test_edit_uses_own_reservation_and_explicit_cash_releases_it():
    state, skin, body, customer, owned = setup()
    payload = booking(customer, owned, skin)
    action(state, "booking", payload)
    action(state, "update_booking", {**payload, "note": "Giữ nguyên lượt"})
    assert available(state, customer, owned)["remaining"] == 2
    action(state, "update_booking", {**booking(customer, owned, body), "combo_purchase_id": ""})
    assert available(state, customer, owned)["remaining"] == 3
    action(state, "booking", booking(customer, owned, skin, "e2"))


@pytest.mark.parametrize("edit_action", ["replace_service"])
def test_other_service_edit_actions_cannot_bypass_combo_entitlements(edit_action):
    state, skin, _, customer, owned = setup()
    action(state, "booking", booking(customer, owned, skin))
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, edit_action, {"employee_id": "e1", "service": "Body 70"})
    assert state == before


@pytest.mark.parametrize("pending", [False, True])
def test_combo_with_retail_extra_reserves_only_combo_and_charges_extra(pending):
    from vera_web_v2_live_tour_payment import service_subtotal
    state, skin, _, customer, owned = setup()
    extra = next(row for row in state["services"] if row["name"] == "Body 70")
    extra["price"] = 170000
    payload = booking(customer, owned, skin)
    payload["service_items"].append({"service_id": extra["id"], "quantity": 2, "unit_price": 1})
    action(state, "booking", payload)
    assert state["employees"][0]["combo_reserved_units"] == 1
    action(state, "start", {"employee_id": "e1"})
    source = {"employee_id": "e1"}
    if pending:
        source = {"pending_id": action(state, "finish_to_pending", source)["pending"]["id"]}
    else:
        action(state, "complete", source)
    invoice = action(state, "checkout", {**source, "combo_purchase_id": owned["id"], "payment_method": "COMBO", "tip": 50000})["invoice"]
    assert invoice["combo_units"] == 1
    assert invoice["subtotal"] == service_subtotal(invoice) == 340000
    assert invoice["total"] == 390000
    assert invoice["combo_covered_amount"] == skin["price"]
    assert state["customers"][0]["combo_purchases"][0]["remaining"] == 2


@pytest.mark.parametrize("shift,reason,hour,minute,expected", [
    ("Ca 2", "", 12, 59, "YC"), ("Ca 2", "", 13, 0, ""),
    ("Ca 1", "Hỗ trợ Ca 1", 11, 59, "YC"), ("Ca 1", "Hỗ trợ Ca 1", 12, 0, ""),
    ("Ca 1", "Hỗ trợ Ca 2", 13, 59, "YC"), ("Ca 1", "Hỗ trợ Ca 2", 14, 0, ""),
])
def test_booking_auto_yc_before_configured_shift(shift, reason, hour, minute, expected):
    state, skin, _, customer, owned = setup()
    state["employees"][0].update(shift=shift, assigned_shift=shift, shift_checkin_date=NOW.date().isoformat(), synced_leave_reason=reason)
    action(state, "booking", booking(customer, owned, skin), NOW.replace(hour=hour, minute=minute))
    assert state["employees"][0]["request"] == expected


def test_auto_yc_uses_custom_cutoff_and_ignores_yesterday_checkin():
    state, *_ = setup()
    worker = state["employees"][0]
    worker.update(shift="Ca 2", shift_checkin_date=NOW.date().isoformat())
    state["payment_settings"]["shift_ready_times"] = {"shift2": "15:30"}
    assert live._before_shift_ready(state, worker, NOW)
    assert not live._before_shift_ready(state, worker, NOW.replace(hour=15, minute=30))
    worker["shift_checkin_date"] = "2026-09-04"
    assert not live._before_shift_ready(state, worker, NOW)


@pytest.mark.parametrize("pending", [False, True])
def test_reservation_survives_completion_and_checkout_debits_once(pending):
    state, skin, body, customer, owned = setup()
    action(state, "booking", booking(customer, owned, skin))
    action(state, "start", {"employee_id": "e1"})
    source = {"employee_id": "e1"}
    if pending:
        row = action(state, "finish_to_pending", source)["pending"]
        assert row["combo_purchase_id"] == owned["id"]
        assert "combo_purchase_id" not in state["employees"][0]
        source = {"pending_id": row["id"]}
    else:
        action(state, "complete", source)
    assert available(state, customer, owned)["remaining"] == 2
    action(state, "booking", booking(customer, owned, body, "e2"))
    paid = action(state, "checkout", {**source, "combo_purchase_id": owned["id"], "payment_method": "COMBO"})["invoice"]
    assert paid["combo_units"] == 1 and paid["total"] == 0
    customer = state["customers"][0]
    owned = customer["combo_purchases"][0]
    assert owned["remaining"] == 2 and available(state, customer, owned)["remaining"] == 1
    assert len(state["combo_usage"]) == 1


def test_checkout_cannot_consume_tickets_reserved_for_another_booking():
    state, skin, _, customer, owned = setup()
    action(state, "booking", booking(customer, owned, skin))
    action(state, "booking", {**booking(customer, owned, skin, "e2"), "combo_purchase_id": "", "start_now": True})
    action(state, "complete", {"employee_id": "e2"})
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "checkout", {"employee_id": "e2", "combo_purchase_id": owned["id"], "payment_method": "COMBO"})
    assert state == before


def test_service_replacement_releases_previous_component_reservation():
    state, skin, body, customer, owned = setup()
    action(state, "booking", booking(customer, owned, skin))
    action(state, "replace_service", {"employee_id": "e1", "service": body["name"]})
    assert [part["remaining"] for part in available(state, customer, owned)["component_balances"]] == [1, 1]
    action(state, "add_service", {"employee_id": "e1", "service": skin["name"]})
    assert [part["remaining"] for part in available(state, customer, owned)["component_balances"]] == [0, 1]


def test_expired_reserved_combo_cannot_start_service():
    state, skin, _, customer, owned = setup()
    action(state, "booking", booking(customer, owned, skin))
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "start", {"employee_id": "e1"}, now=NOW.replace(month=10, day=1))
    assert state["employees"][0]["status"] == before["employees"][0]["status"]


def test_hidden_retained_assignments_and_restart_keep_reservations():
    state, skin, _, customer, owned = setup()
    action(state, "booking", booking(customer, owned, skin))
    state["employees"][0].update(hidden=True, roster_eligible=False)
    response = live._state_response(state, 1, NOW, can_payment=True)
    assert isinstance(response["available_beds"], list) and "1.1" not in response["available_beds"]
    public_purchase = response["customers"][0]["combo_purchases"][0]
    assert public_purchase["remaining"] == 3 and public_purchase["booking_remaining"] == 2
    assert public_purchase["component_balances"][0]["booking_remaining"] == 0
    assert "booking_remaining" not in owned
    db = SettingsDatabase(state)
    _, reopened = app_client(db)
    assert reopened.get("/v2/live-tour").json()["customers"][0]["combos"][0]["booking_remaining"] == 2
    redacted = live._state_response(state, 1, NOW, can_operate=True)
    assert redacted["customers"] == []
    assert "combo_purchase_id" not in str(redacted)


def test_multi_booking_with_one_remaining_component_rolls_back_all():
    state, skin, _, customer, owned = setup()
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "multi_booking", {"bookings": [booking(customer, owned, skin), booking(customer, owned, skin, "e2")]})
    assert state == before


def test_generic_combo_keeps_legacy_ticket_units():
    state, skin, _, _, _ = setup()
    customer, owned = purchase(state, state["combos"][0])
    action(state, "booking", booking(customer, owned, skin))
    assert state["employees"][0]["combo_reserved_units"] == 5
    assert available(state, customer, owned)["remaining"] == owned["remaining"] - 5


def test_http_stale_booking_and_replayed_checkout_do_not_overspend(monkeypatch):
    state, skin, _, customer, owned = setup()
    owned.update(starts_on="", unlimited=True)
    skin.update(starts_on="", unlimited=True)
    client, shared = api_client(monkeypatch, state)
    def post(name, payload, key, revision=None):
        return client.post("/v2/live-tour/action", json={"action": name, "payload": payload,
            "expected_revision": shared["revision"] if revision is None else revision, "idempotency_key": key})
    initial_revision = shared["revision"]
    first = post("booking", booking(customer, owned, skin), "combo-booking-first")
    assert first.status_code == 200, first.text
    second_payload = booking(customer, owned, skin, "e2")
    assert post("booking", second_payload, "combo-booking-stale", initial_revision).status_code == 409
    assert post("booking", second_payload, "combo-booking-second").status_code == 409
    assert post("start", {"employee_id": "e1"}, "combo-start-first").status_code == 200
    pending = post("finish_to_pending", {"employee_id": "e1"}, "combo-finish-first").json()["result"]["pending"]
    payload = {"pending_id": pending["id"], "combo_purchase_id": owned["id"], "payment_method": "COMBO"}
    paid = post("checkout", payload, "combo-checkout-once")
    assert paid.status_code == 200, paid.text
    replay = post("checkout", payload, "combo-checkout-once")
    assert replay.status_code == 200 and replay.json()["result"]["invoice"]["id"] == paid.json()["result"]["invoice"]["id"]
    assert shared["state"]["customers"][0]["combo_purchases"][0]["remaining"] == 2
    assert len(shared["state"]["combo_usage"]) == 1


@pytest.mark.parametrize("payload", [{"combo_purchase_id": ""}, {"combo_purchase_id": "owned"}, {"bookings": [{"combo_purchase_id": ""}]}])
def test_operate_only_cannot_set_or_clear_customer_combo(payload):
    def require(_conn, _identity, feature):
        if feature == "live_tour_customers_view":
            raise HTTPException(403, "Permission denied")
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=require, feature_allowed=lambda *_args: False, identity_type=RouteIdentity)
    response = TestClient(app).post("/v2/live-tour/action", json={"action": "multi_booking" if "bookings" in payload else "update_booking",
        "payload": payload, "expected_revision": 1, "idempotency_key": "combo-permissions"})
    assert response.status_code == 403


def test_frontend_autofill_and_available_ticket_validation():
    module = (Path(__file__).parents[1] / "web-v2/src/lib/liveTourComboBooking.js").as_uri()
    script = r'''
import assert from 'node:assert/strict';
const {availableBookingPurchase, customerTicketLabel, comboBookingItems, preferredBookingCombo, comboBookingError} = await import(MODULE);
const day = '2026-09-09', services = [{id:'skin',name:'Da',ticket_units:5},{id:'body',name:'Body',ticket_units:1}];
const owned = {id:'p',remaining:13,booking_remaining:12,component_balances:[{service_id:'skin',remaining:1,booking_remaining:0},{service_id:'body',remaining:12,booking_remaining:12}]};
const customer = {combo_purchases:[{id:'empty',remaining:0},owned]};
assert.equal(customerTicketLabel(customer),'Còn 13 vé combo');
assert.equal(customerTicketLabel({combo_purchases:[{remaining:0}]}),'Còn 0 vé combo');
assert.equal(customerTicketLabel({}),'');
assert.equal(preferredBookingCombo(customer,services,day).id,'p');
const available = availableBookingPurchase(owned);
assert.deepEqual(comboBookingItems(available,services,day),[{service_id:'body',quantity:1}]);
assert.deepEqual(comboBookingItems({remaining:13,combo_name:'VIP 90'},services,day),[]);
assert.match(comboBookingError({remaining:0},[],services,day),/0 vé/);
assert.match(comboBookingError({...owned,unlimited:false,expires_on:'2026-09-08'},[],services,day),/hết hạn/);
assert.match(comboBookingError(available,[{service_id:'skin',quantity:1}],services,day),/0 lượt/);
assert.equal(comboBookingError(available,[{service_id:'body',quantity:1}],services,day),'');
assert.match(comboBookingError({remaining:4},[{service_id:'skin',quantity:1}],services,day),/không đủ/);
assert.match(comboBookingError(available,[{service_id:'body',quantity:0.5}],services,day),/nguyên dương/);
const own = {combo_purchase_id:'p',combo_reserved_units:1,combo_reserved_components:[{service_id:'skin',units:1}]};
const editing = availableBookingPurchase(owned,[own]);
assert.equal(editing.remaining,13);
assert.equal(editing.component_balances[0].remaining,1);
assert.equal(comboBookingError(editing,[{service_id:'skin',quantity:1}],services,day),'');
assert.equal(owned.component_balances[0].booking_remaining,0);
assert.equal(availableBookingPurchase(owned,[{...own,combo_purchase_id:'another'}]).remaining,12);
assert.equal(preferredBookingCombo({combo_purchases:[{...owned,id:'expired',unlimited:false,expires_on:'2026-09-08'},owned]},services,day).id,'p');
assert.equal(preferredBookingCombo({combo_purchases:[]},services,day),undefined);
assert.deepEqual(comboBookingItems(undefined,services,day),[]);
'''.replace("MODULE", repr(module))
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

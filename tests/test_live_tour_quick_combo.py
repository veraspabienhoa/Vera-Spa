"""Quick checkout resolves combo entitlements and requires an explicit booking date."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_combo_booking import setup, booking
from test_live_tour_safety import api_client


def payload(customer, purchase):
    return {"customer_id": customer["id"], "combo_purchase_id": purchase["id"], "payment_method": "COMBO",
            "quick_booking": {"employee_id": "e1", "room": "1.1", "booked_at": live._iso(NOW), "correction_reason": "Nhập bổ sung"}}


def test_automatic_components_use_one_each_not_full_balance_and_only_collect_tip():
    state, skin, body, customer, owned = setup()
    before = deepcopy(state["employees"])
    data = payload(customer, owned)
    data["tip_card_ids"] = ["tip-200000", "tip-200000"]
    result = live._apply_action(state, "quick_checkout", data, "admin", NOW)["invoice"]
    assert result["total"] == result["tip"] == 400000
    assert result["subtotal"] == skin["price"] + body["price"]
    assert result["combo_units"] == 2
    assert [part["remaining"] for part in owned["component_balances"]] == [0, 1]
    assert owned["remaining"] == 1
    assert [part["quantity"] for part in result["entries"][0]["service_items"]] == [1, 1]
    assert result["entries"][0]["employee_id"] == "e1"
    assert state["employees"] == before
    assert len(state["combo_usage"]) == 1


def test_generic_legacy_tickets_debit_one_without_inventing_a_catalog_service():
    state = state_with(employee("e1", "An"))
    owned = {"id": "legacy", "combo_name": "Combo 13", "remaining": 7, "total": 13, "used": 6}
    customer = {"id": "customer", "name": "Khách cũ", "combo_purchases": [owned]}
    state["customers"] = [customer]
    invoice = live._apply_action(state, "quick_checkout", payload(customer, owned), "admin", NOW)["invoice"]
    assert invoice["total"] == invoice["subtotal"] == 0
    assert invoice["combo_units"] == 1 and owned["remaining"] == 6 and owned["used"] == 7
    assert invoice["entries"][0]["price_source"] == "combo_ticket"
    assert not invoice["entries"][0]["service_items"]
    assert invoice["entries"][0]["service"] == "Sử dụng combo: Combo 13"


def test_auto_combo_does_not_steal_open_booking_or_pending_reservations():
    state, skin, body, customer, owned = setup()
    live._apply_action(state, "booking", booking(customer, owned, skin), "admin", NOW)
    data = payload(customer, owned)
    invoice = live._apply_action(state, "quick_checkout", data, "admin", NOW)["invoice"]
    assert invoice["combo_units"] == 1
    assert invoice["entries"][0]["service_items"][0]["service_id"] == body["id"]
    assert owned["component_balances"][0]["remaining"] == 1
    # Reserve all remaining body uses in a pending receipt as well.
    state["pending"].append({"id": "pending", "customer_id": customer["id"], "entries": [
        {"combo_purchase_id": owned["id"], "combo_reserved_units": 1,
         "combo_reserved_components": [{"service_id": body["id"], "units": 1}]}]})
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, "quick_checkout", data, "admin", NOW)
    assert state == before


@pytest.mark.parametrize("problem", ["other_customer", "missing_customer", "expired", "future", "deleted", "empty", "unavailable_services", "cash", "bad_service_items"])
def test_invalid_auto_combo_is_atomic(problem):
    state, skin, body, customer, owned = setup()
    data = payload(customer, owned)
    if problem == "other_customer":
        state["customers"].append({"id": "other", "name": "Other", "combo_purchases": []})
        data["customer_id"] = "other"
    elif problem == "missing_customer":
        data.pop("customer_id")
    elif problem == "expired":
        owned["expires_on"] = "2026-09-04"
    elif problem == "future":
        owned["starts_on"] = "2026-09-06"
    elif problem == "deleted":
        owned["deleted_at"] = live._iso(NOW)
    elif problem == "empty":
        owned["remaining"] = 0
    elif problem == "unavailable_services":
        skin["active"] = body["active"] = False
    elif problem == "cash":
        data["payment_method"] = "TIỀN MẶT"
    else:
        data["quick_booking"]["service_items"] = ""
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, "quick_checkout", data, "admin", NOW)
    assert state == before


@pytest.mark.parametrize("booked", [None, "", "2026-09-05", "2026-02-30T12:00:00+07:00", "2026-09-05T15:01:00+07:00"])
@pytest.mark.parametrize("mode", ["combo", "steam", "cash"])
def test_date_required_valid_and_not_future_in_all_quick_flows(booked, mode):
    state, skin, body, customer, owned = setup()
    data = payload(customer, owned)
    if mode != "combo":
        data.pop("combo_purchase_id")
        data["payment_method"] = "TIỀN MẶT"
        service = next(row for row in state["services"] if row["name"] == "Xông hơi") if mode == "steam" else body
        service["price"] = 100000
        data["quick_booking"]["service_items"] = [{"service_id": service["id"], "quantity": 1}]
    if booked is None:
        data["quick_booking"].pop("booked_at")
    else:
        data["quick_booking"]["booked_at"] = booked
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, "quick_checkout", data, "admin", NOW)
    assert state == before


def test_combo_steam_still_no_employee_or_room_and_keeps_selected_date():
    state = state_with(employee("e1", "An"))
    service = next(row for row in state["services"] if row["name"] == "Xông hơi")
    service["price"] = 100000
    owned = {"id": "steam", "remaining": 3, "used": 0, "total": 3, "component_balances": [
        {"service_id": service["id"], "service_name": service["name"], "remaining": 3, "used": 0, "total": 3}]}
    customer = {"id": "c", "name": "Khách cũ", "combo_purchases": [owned]}
    state["customers"] = [customer]
    data = payload(customer, owned)
    data["quick_booking"] = {"booked_at": live._iso(NOW - timedelta(days=1)), "correction_reason": "Nhập hôm qua"}
    invoice = live._apply_action(state, "quick_checkout", data, "admin", NOW)["invoice"]
    assert invoice["effective_at"] == data["quick_booking"]["booked_at"]
    assert invoice["business_date"] == "2026-09-04"
    assert invoice["entries"][0]["employee_id"] == invoice["entries"][0]["room"] == ""
    assert invoice["total"] == 0 and owned["remaining"] == 2


def test_combo_quick_checkout_http_retry_debits_once_and_rejects_stale_revision(monkeypatch):
    state, _, _, customer, owned = setup()
    data = payload(customer, owned)
    # Use today's timestamp; purchase validity remains server-derived.
    data["quick_booking"]["booked_at"] = live._iso(datetime.now(live.VN_TZ) - timedelta(minutes=1))
    owned.update(unlimited=True, starts_on="")
    client, shared = api_client(monkeypatch, state)
    command = {"action": "quick_checkout", "payload": data, "idempotency_key": "auto-combo-unique-1", "expected_revision": 1}
    first = client.post("/v2/live-tour/action", json=command)
    retry = client.post("/v2/live-tour/action", json=command)
    assert first.status_code == retry.status_code == 200, first.text
    assert retry.json()["duplicate"]
    assert first.json()["result"]["invoice"]["id"] == retry.json()["result"]["invoice"]["id"]
    assert shared["state"]["customers"][0]["combo_purchases"][0]["remaining"] == 1
    assert len(shared["state"]["combo_usage"]) == 1
    before = deepcopy(shared)
    command["idempotency_key"] = "auto-combo-stale-2"
    assert client.post("/v2/live-tour/action", json=command).status_code == 409
    assert shared == before

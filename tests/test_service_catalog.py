"""Service creation, package entitlements and compatibility with existing tours."""
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
import subprocess

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from vera_web_v2_service_catalog import component_debits, require_available
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_server_only import SettingsDatabase, app_client


def action(state, name, payload, now=NOW):
    return live._apply_action(state, name, payload, "admin", now)


def catalog(state):
    single = action(state, "service_upsert", {
        "name": "Chăm sóc da", "duration": 60, "price": 200000, "sessions": 3,
        "group": "Chăm sóc", "starts_on": "2026-09-01", "unlimited": True,
        "loyalty_points": 20, "description": "Liệu trình da cơ bản", "ticket_units": 5,
        "steps": [{"name": "Làm sạch", "duration": 10}, {"name": "Massage", "duration": 50}],
    })["service"]
    other = next(row for row in state["services"] if row["name"] == "Body 90")
    combo = action(state, "combo_upsert", {
        "name": "Chăm sóc toàn diện", "price": 500000, "tickets": 999,
        "starts_on": "2026-09-01", "unlimited": False, "expires_on": "2026-09-30",
        "group": "Chăm sóc", "loyalty_points": 50, "description": "Da và body",
        "components": [{"service_id": single["id"], "service_name": "Spoof", "quantity": 1}, {"service_id": other["id"], "quantity": 2}],
    })["combo"]
    return single, other, combo


def purchase(state, combo, quantity=1):
    result = action(state, "combo_purchase", {"combo_id": combo["id"], "customer_name": "Khách mới", "phone": "0901234567", "quantity": quantity, "amount": 1, "tickets": 999})
    return state["customers"][0], result["purchase"]


def complete(state, service, customer, extra=None):
    action(state, "booking", {"employee_id": "e1", "service": service["name"], "room": "1.1", "customer_id": customer["id"]})
    if extra:
        action(state, "add_service", {"employee_id": "e1", "service": extra["name"]})
    action(state, "start", {"employee_id": "e1"})
    action(state, "complete", {"employee_id": "e1"})


def pay(state, customer, owned, **extras):
    return action(state, "checkout", {"employee_id": "e1", "customer_id": customer["id"], "combo_purchase_id": owned["id"], "payment_method": "COMBO", **extras})


def test_catalog_and_purchase_terms_persist_across_server_restarts():
    state = state_with()
    single, other, combo = catalog(state)
    assert single["service_type"] == "single" and single["sessions"] == 3
    assert combo["tickets"] == 3
    assert combo["components"][0]["service_name"] == single["name"]
    customer, owned = purchase(state, combo, 2)
    assert owned["price"] == 1000000 and owned["total"] == 6
    assert [row["remaining"] for row in owned["component_balances"]] == [2, 4]
    database = SettingsDatabase(state)
    _, client = app_client(database)
    settings = client.get("/v2/live-tour/settings").json()
    assert next(row for row in settings["services"] if row["id"] == single["id"]) == single
    assert next(row for row in settings["combos"] if row["id"] == combo["id"]) == combo
    _, reopened = app_client(database)
    history = reopened.get(f"/v2/live-tour/customers/{customer['id']}/history").json()
    assert history["combo_purchases"][0] == owned


@pytest.mark.parametrize("bad", [
    {"sessions": 0}, {"sessions": True}, {"sessions": 1.5}, {"loyalty_points": -1},
    {"starts_on": "2026-02-30"}, {"starts_on": "09/09/2026"}, {"unlimited": "true"},
    {"unlimited": False}, {"unlimited": False, "starts_on": "2026-09-09", "expires_on": "2026-09-08"},
    {"steps": [{"name": "", "duration": 10}]}, {"steps": [{"name": "Bước", "duration": -1}]},
    {"steps": [{"name": "Bước", "duration": 800}] * 2}, {"description": "x" * 5001},
])
def test_invalid_service_update_is_atomic(bad):
    state = state_with()
    single, _, _ = catalog(state)
    before = deepcopy(state)
    with pytest.raises(HTTPException) as error:
        action(state, "service_upsert", {**single, **bad})
    assert error.value.status_code == 400
    assert state == before


@pytest.mark.parametrize("components", [[], "wrong", [{"service_id": "missing", "quantity": 1}], [{"quantity": 1}]])
def test_invalid_combo_components_never_persist(components):
    state = state_with()
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "combo_upsert", {"name": "Bad combo", "price": 1000, "components": components})
    assert state == before


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5, 100001])
def test_combo_quantity_and_duplicates_are_rejected(quantity):
    state = state_with()
    single, _, combo = catalog(state)
    for components in [[{"service_id": single["id"], "quantity": quantity}], [combo["components"][0]] * 2]:
        before = deepcopy(state)
        with pytest.raises(HTTPException):
            action(state, "combo_upsert", {**combo, "components": components})
        assert state == before


def test_old_editor_preserves_metadata_and_old_purchases_keep_their_terms():
    state = state_with()
    single, _, combo = catalog(state)
    _, owned = purchase(state, combo)
    before = deepcopy(owned)
    action(state, "service_upsert", {"id": single["id"], "name": single["name"], "price": 250000, "duration": 60})
    assert single["steps"][0]["name"] == "Làm sạch" and single["loyalty_points"] == 20
    action(state, "combo_upsert", {"id": combo["id"], "name": combo["name"], "tickets": 99, "price": 600000})
    assert combo["tickets"] == 3 and combo["expires_on"] == "2026-09-30"
    action(state, "combo_upsert", {**combo, "components": [{"service_id": single["id"], "quantity": 20}], "expires_on": "2026-10-31"})
    assert owned == before


def test_composed_combo_debits_each_service_once_and_keeps_financial_records():
    state = state_with(employee("e1", "An"))
    single, other, combo = catalog(state)
    customer, owned = purchase(state, combo)
    complete(state, single, customer, extra=other)
    result = pay(state, customer, owned, tip=50000)
    assert result["invoice"]["combo_units"] == 2  # Single has legacy ticket_units=5.
    assert result["invoice"]["total"] == 50000
    assert result["invoice"]["combo_covered_amount"] == 200000
    assert result["invoice"]["combo_units_source"] == "server_purchase_components"
    assert sum(row["combo_units"] for row in state["reports"] if row.get("invoice_id") == result["invoice"]["id"]) == 2
    assert owned["remaining"] == 1 and owned["used"] == 2
    assert [row["remaining"] for row in owned["component_balances"]] == [0, 1]
    assert sum(row["units"] for row in state["combo_usage"][-1]["component_debits"]) == 2
    complete(state, single, customer)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        pay(state, customer, owned)
    assert state == before  # Body still has one use; skin must not borrow it.


def test_wrong_service_and_expired_purchase_cannot_be_used():
    state = state_with(employee("e1", "An"))
    single, _, combo = catalog(state)
    customer, owned = purchase(state, combo)
    other = next(row for row in state["services"] if row["name"] == "Body 70")
    complete(state, other, customer)
    before = deepcopy(state)
    with pytest.raises(HTTPException) as error:
        pay(state, customer, owned)
    assert error.value.status_code == 409 and state == before
    with pytest.raises(HTTPException):
        component_debits(owned, [{"service": single["name"]}], state["services"], date(2026, 10, 1))
    assert component_debits(owned, [{"service": single["name"]}], state["services"], date(2026, 9, 30))[0]["units"] == 1


def test_name_with_ampersand_and_rename_match_stable_service_entitlements():
    state = state_with()
    single, _, combo = catalog(state)
    _, owned = purchase(state, combo)
    action(state, "service_upsert", {**single, "name": "Da & Body"})
    plan = component_debits(owned, [{"service": "da & body"}], state["services"], NOW.date())
    assert plan[0]["service_id"] == single["id"] and plan[0]["units"] == 1
    with pytest.raises(HTTPException):
        action(state, "service_delete", {"id": single["id"]})
    action(state, "combo_delete", {"id": combo["id"]})
    with pytest.raises(HTTPException):
        action(state, "service_delete", {"id": single["id"]})


def test_catalog_dates_use_vietnam_calendar_and_block_booking_and_sale():
    state = state_with(employee("e1", "An"))
    single, _, combo = catalog(state)
    single["starts_on"] = "2026-09-06"
    with pytest.raises(HTTPException):
        action(state, "booking", {"employee_id": "e1", "service": single["name"], "room": "1.1"})
    with pytest.raises(HTTPException):
        purchase(state, combo)
    action(state, "booking", {"employee_id": "e1", "service": single["name"], "room": "1.1"}, datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc))
    single["active"] = False
    with pytest.raises(HTTPException):
        action(state, "replace_service", {"employee_id": "e1", "service": single["name"]})
    require_available({"starts_on": "2026-09-05", "unlimited": False, "expires_on": "2026-09-05"}, NOW.date(), "Dịch vụ")


def test_legacy_ticket_combo_usage_and_import_are_unchanged():
    state = state_with(employee("e1", "An"))
    single, _, composed = catalog(state)
    combo = state["combos"][0]
    customer, owned = purchase(state, combo)
    assert "component_balances" not in owned
    complete(state, single, customer)
    invoice = pay(state, customer, owned)["invoice"]
    assert invoice["combo_units"] == 5
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "combo_import", {"customer_id": customer["id"], "combo_id": composed["id"], "remaining": 2})
    assert state == before


def test_http_create_edit_replay_conflict_and_payment_survive_reopen(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(live, "datetime", FixedDateTime)
    state = state_with(employee("e1", "An"))
    single, _, combo = catalog(state)
    customer, owned = purchase(state, combo)
    complete(state, single, customer)
    db = SettingsDatabase(state)
    _, client = app_client(db)
    body = {"action": "checkout", "expected_revision": 7, "idempotency_key": "composed-payment-once", "payload": {"employee_id": "e1", "customer_id": customer["id"], "combo_purchase_id": owned["id"], "payment_method": "COMBO"}}
    first = client.post("/v2/live-tour/action", json=body)
    assert first.status_code == 200, first.text
    stored = deepcopy(db.stored)
    retry = client.post("/v2/live-tour/action", json=body)
    assert retry.status_code == 200 and db.stored == stored
    create = {"action": "combo_upsert", "expected_revision": db.revision, "idempotency_key": "catalog-create-once", "payload": {"name": "Combo mới", "price": 100000, "components": [{"service_id": single["id"], "quantity": 2}], "create_only": True}}
    saved = client.post("/v2/live-tour/action", json=create)
    assert saved.status_code == 200, saved.text
    assert client.post("/v2/live-tour/action", json={**create, "idempotency_key": "stale-other-request"}).status_code == 409
    _, reopened = app_client(db)
    combos = reopened.get("/v2/live-tour/settings").json()["combos"]
    assert next(row for row in combos if row["name"] == "Combo mới")["tickets"] == 2
    assert db.stored["customers"][0]["combo_purchases"][0]["remaining"] == 2


def test_frontend_payloads_and_combo_preview_follow_server_terms():
    module = (Path(__file__).parents[1] / "web-v2/src/lib/serviceCatalog.js").as_uri()
    script = """
import assert from 'node:assert/strict';
const {newCatalogForm, catalogPayload, comboUsagePreview, vietnamDate, catalogTransactionDate} = await import(MODULE);
assert.equal(vietnamDate('2026-09-05T17:00:00Z'), '2026-09-06');
assert.equal(catalogTransactionDate('2026-09-05T17:00:00Z', true), '2026-09-04');
assert.equal(catalogTransactionDate('2026-09-06T05:00:00Z', true), '2026-09-05');
const single = newCatalogForm('service');
assert.equal(single.sessions, '1'); assert.equal(single.unlimited, true);
const form = newCatalogForm('combo'); form.components = [{service_id:'s1', quantity:'2'}];
assert.deepEqual(catalogPayload('combo', form, false).components, [{service_id:'s1', quantity:2}]);
const legacy = newCatalogForm('combo', {id:'old', tickets:13});
assert.equal(catalogPayload('combo', legacy, true).tickets, 13);
assert.equal('components' in catalogPayload('combo', legacy, true), false);
const owned = {remaining:3, component_balances:[{service_id:'s1',remaining:1},{service_id:'s2',remaining:2}]};
const services = [{id:'s1',name:'Da & Body',ticket_units:5}, {id:'s2',name:'Massage'}];
assert.deepEqual(comboUsagePreview(owned,[{service:'Da & Body'}],services),{eligible:true,units:1});
assert.equal(comboUsagePreview(owned,[{service:'Massage'},{service:'Massage'},{service:'Massage'}],services).eligible,false);
assert.equal(comboUsagePreview({...owned,unlimited:false,expires_on:'2026-09-05'},[{service:'Massage'}],services,'2026-09-06').eligible,false);
assert.equal(comboUsagePreview({remaining:10},[{service:'Unknown legacy'}],services).eligible,true);
""".replace("MODULE", repr(module))
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

"""Customer/settings menus share transactional server data with Live Tour."""
from copy import deepcopy

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteIdentity, employee, state_with
from test_live_tour_server_only import SettingsDatabase, app_client


def action(state, name, payload):
    return live._apply_action(state, name, payload, "admin", NOW)


def area(state, name="Sen", kind="room", beds=None):
    return action(state, "service_area_upsert", {
        "name": name, "kind": kind, "beds": beds if beds is not None else [{"name": "Giường 1"}, {"name": "Giường 2"}],
    })["service_area"]


def test_existing_rooms_are_grouped_without_mutating_bookings_or_ids():
    state = state_with()
    before = deepcopy(state)
    areas = live._service_areas(state)
    vip19 = next(row for row in areas if row["name"] == "19")
    assert [row["booking_name"] for row in vip19["beds"]] == ["19.1", "19.2", "19.3"]
    assert state == before
    saved = action(state, "service_area_upsert", vip19)["service_area"]
    assert saved == vip19


@pytest.mark.parametrize("kind", ["room", "bed", "table"])
def test_all_area_types_are_bookable_and_projected_to_the_board(kind):
    state = state_with(employee("e1", "An"))
    saved = area(state, "Sen.1", kind)
    places = [row for row in state["rooms"] if row.get("area_id") == saved["id"]]
    assert len(places) == (2 if kind == "room" else 1)
    action(state, "booking", {"employee_id": "e1", "room": places[0]["name"], "service": "Body 90"})
    dto = live._state_response(state, 1, NOW)
    assert dto["room_groups"][places[0]["name"]] == "Sen.1"
    assert "Sen.1" in dto["rooms"]["all"]
    assert "Sen.1" in dto["rooms"]["occupied"]
    assert places[0]["name"] not in dto["available_beds"]


def test_private_service_locks_sibling_beds_but_not_other_areas():
    state = state_with(employee("e1", "An"), employee("e2", "Bình"))
    saved = area(state)
    separate = area(state, "Sen.2", "table")
    first, second = [bed["booking_name"] for bed in saved["beds"]]
    action(state, "booking", {"employee_id": "e1", "room": first, "service": "P.Riêng"})
    assert not live._room_available(state, second)
    with pytest.raises(HTTPException) as exc:
        action(state, "booking", {"employee_id": "e2", "room": second, "service": "Body 90"})
    assert exc.value.status_code == 409
    action(state, "booking", {"employee_id": "e2", "room": separate["beds"][0]["booking_name"], "service": "Body 90"})


def test_standard_service_allows_other_beds_in_same_room():
    state = state_with(employee("e1", "An"), employee("e2", "Bình"))
    saved = area(state)
    for identifier, bed in zip(["e1", "e2"], saved["beds"]):
        action(state, "booking", {"employee_id": identifier, "room": bed["booking_name"], "service": "Body 90"})
    assert len({row["room"] for row in state["employees"]}) == 2


@pytest.mark.parametrize("bad", [
    {"name": ""}, {"kind": "unknown"}, {"beds": []}, {"beds": "invalid"},
    {"beds": [{"name": "A"}, {"name": "a"}]}, {"beds": [{"name": "A", "id": "foreign"}]},
    {"beds": [{"name": "A"}] * 101},
])
def test_invalid_area_update_never_partially_changes_places(bad):
    state = state_with()
    saved = area(state)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "service_area_upsert", {**saved, **bad})
    assert state == before


def test_deleting_last_area_and_service_stays_empty_after_reopen():
    state = state_with()
    state["rooms"] = []
    saved = area(state, kind="table")
    action(state, "service_area_delete", {"id": saved["id"]})
    for service in list(state["services"]):
        action(state, "service_delete", {"id": service["id"]})
    reopened = live._normalize_state(state, NOW)
    assert reopened["rooms"] == reopened["services"] == []
    assert live._state_response(reopened, 1, NOW)["rooms"]["all"] == []


def test_area_guards_cover_open_and_pending_work_and_legacy_room_editor():
    state = state_with(employee("e1", "An"))
    saved = area(state)
    bed = saved["beds"][0]
    action(state, "booking", {"employee_id": "e1", "room": bed["booking_name"], "service": "Body 90"})
    for pending in [False, True]:
        if pending:
            action(state, "start", {"employee_id": "e1"})
            action(state, "complete", {"employee_id": "e1"})
            action(state, "move_pending", {"employee_id": "e1"})
        for operation, payload in [
            ("service_area_delete", {"id": saved["id"]}),
            ("service_area_upsert", {**saved, "name": "Tên mới"}),
            ("room_upsert", {"id": bed["id"], "name": "Đổi tên"}),
            ("room_delete", {"id": bed["id"]}),
        ]:
            before = deepcopy(state)
            with pytest.raises(HTTPException) as exc:
                action(state, operation, payload)
            assert exc.value.status_code == 409
            assert state == before


def test_customer_edit_keeps_stable_history_and_updates_only_open_transactions():
    state = state_with(employee("e1", "An"))
    service = next(row for row in state["services"] if row["name"] == "Body 90")
    action(state, "service_upsert", {**service, "price": 100})
    customer = action(state, "customer_upsert", {"customer_name": "Khách cũ", "customer_phone": "0901234567"})["customer"]
    customer_id = customer["id"]
    state["customers"][0]["combo_purchases"] = [{"id": "purchase1", "total": 13, "used": 2, "remaining": 11}]
    state["invoices"] = [{"id": "bill1", "customer_id": customer_id, "reason": "Đối chiếu hồ sơ", "customer_name": "Khách cũ", "total": 100, "entries": []}]
    invoices = deepcopy(state["invoices"])
    action(state, "booking", {"employee_id": "e1", "room": "1.1", "service": "Body 90", "customer_id": customer_id})
    action(state, "start", {"employee_id": "e1"})
    action(state, "complete", {"employee_id": "e1"})
    action(state, "move_pending", {"employee_id": "e1"})
    result = action(state, "customer_upsert", {"customer_id": customer_id, "reason": "Đối chiếu hồ sơ", "customer_name": "Tên mới", "customer_phone": "0907654321", "combo_purchases": [], "remaining": 0})["customer"]
    assert result["id"] == customer_id
    assert result["combo_purchases"][0]["remaining"] == 11
    assert state["invoices"] == invoices
    assert state["pending"][0]["customer_name"] == "Tên mới"
    assert state["pending"][0]["customer_phone"] == "0907654321"
    assert live._customer_history(state, customer_id)["summary"]["invoice_count"] == 1
    assert "Tên mới" not in str(state["audit"])
    assert "0907654321" not in str(state["audit"])
    action(state, "checkout", {"pending_id": state["pending"][0]["id"], "payment_method": "TIỀN MẶT"})
    assert state["invoices"][-1]["customer_name"] == "Tên mới"
    assert state["invoices"][-1]["customer_phone"] == "0907654321"


def test_duplicate_customer_phone_is_rejected_without_merging_records():
    state = state_with()
    first = action(state, "customer_upsert", {"customer_name": "An", "customer_phone": "0901234567"})["customer"]
    second = action(state, "customer_upsert", {"customer_name": "Bình", "customer_phone": "0900000000"})["customer"]
    for customer_id in ["", second["id"]]:
        before = deepcopy(state)
        with pytest.raises(HTTPException) as exc:
            action(state, "customer_upsert", {"customer_id": customer_id, "reason": "Đối chiếu hồ sơ", "customer_name": "Bình", "customer_phone": "090 123 4567"})
        assert exc.value.status_code == 409
        assert state == before
    assert first["id"] != second["id"]


def test_adding_a_duplicate_service_cannot_overwrite_its_price():
    state = state_with()
    service = next(row for row in state["services"] if row["name"] == "Body 90")
    action(state, "service_upsert", {**service, "price": 300000})
    before = deepcopy(state)
    with pytest.raises(HTTPException) as exc:
        action(state, "service_upsert", {"name": "Body 90", "price": 0, "duration": 90, "create_only": True})
    assert exc.value.status_code == 409
    assert state == before


def test_new_menus_persist_on_server_with_revision_and_idempotency():
    database = SettingsDatabase()
    _, client = app_client(database)
    settings = client.get("/v2/live-tour/settings").json()
    body = {"action": "service_area_upsert", "payload": {"name": "Bàn 1", "kind": "table"}, "expected_revision": settings["revision"], "idempotency_key": "area-retry-key"}
    response = client.post("/v2/live-tour/action", json=body)
    assert response.status_code == 200, response.text
    assert client.post("/v2/live-tour/action", json=body).json()["duplicate"] is True
    stale = client.post("/v2/live-tour/action", json={**body, "idempotency_key": "another-action-key"})
    assert stale.status_code == 409
    _, reopened = app_client(database)
    saved = reopened.get("/v2/live-tour/settings").json()
    assert len([row for row in saved["service_areas"] if row["name"] == "Bàn 1"]) == 1
    customer_body = {"action": "customer_upsert", "payload": {"customer_name": "Khách trên server"}, "expected_revision": saved["revision"], "idempotency_key": "customer-retry-key"}
    assert reopened.post("/v2/live-tour/action", json=customer_body).status_code == 200
    assert reopened.post("/v2/live-tour/action", json=customer_body).json()["duplicate"] is True
    _, third = app_client(database)
    assert [row["name"] for row in third.get("/v2/live-tour/customers").json()["customers"]] == ["Khách trên server"]


@pytest.mark.parametrize("permission,path,operation,payload", [
    ("live_tour_customers_view", "/v2/live-tour/customers", "customer_upsert", {"customer_name": "An"}),
    ("live_tour_admin", "/v2/live-tour/settings", "service_area_upsert", {"name": "Bàn 1", "kind": "table"}),
])
def test_menu_permissions_apply_to_reads_and_writes(permission, path, operation, payload):
    database = SettingsDatabase()
    grants = set()
    def require(_conn, _ident, feature):
        if feature not in grants:
            raise HTTPException(403, "Forbidden")
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda: database,
        current_identity=lambda: RouteIdentity(), require_feature=require,
        feature_allowed=lambda _conn, _ident, feature: feature in grants, identity_type=RouteIdentity)
    client = TestClient(app)
    assert client.get(path).status_code == 403
    body = {"action": operation, "payload": payload, "expected_revision": 1, "idempotency_key": "permission-key"}
    assert client.post("/v2/live-tour/action", json=body).status_code == 403
    assert database.stored is None
    grants.add(permission)
    response = client.get(path)
    assert response.status_code == 200
    assert "invoices" not in response.json()
    if permission == "live_tour_admin":
        assert "customers" not in response.json()
    else:
        assert client.post("/v2/live-tour/action", json=body).status_code == 403
        grants.add("live_tour_payment")
    assert client.post("/v2/live-tour/action", json=body).status_code == 200

"""Invoice corrections, ticket integrity and independent API read/write grants."""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from vera_web_v2_live_tour_permissions import CAPABILITY_FEATURES, EXPORT_FEATURES, LEGACY_FEATURE_INHERITANCE
from test_live_tour_backend import NOW, RouteEngine, RouteIdentity
from test_live_tour_safety import api_client, payable_state
from test_live_tour_combo_booking import setup, booking
from test_service_catalog import action


ALL = set(CAPABILITY_FEATURES.values()) | {"live_tour_view", "live_tour_operate", "live_tour_payment", "live_tour_admin", "live_tour_export"}


def pending_state():
    state = payable_state()
    pending = action(state, "move_pending", {"employee_id": "e1"})["pending"]
    return state, pending


def paid_state():
    state = payable_state()
    paid = action(state, "checkout", {"employee_id": "e1", "payment_method": "TIỀN MẶT", "tip": 20})["invoice"]
    return state, paid


def scoped_client(monkeypatch, state, grants):
    _, shared = api_client(monkeypatch, state)
    def require(_conn, _ident, feature):
        if feature not in grants:
            raise HTTPException(403, feature)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
                                 require_feature=require, feature_allowed=lambda _c, _i, feature: feature in grants,
                                 identity_type=RouteIdentity)
    return TestClient(app), shared


def post(client, shared, name, payload, **overrides):
    return client.post("/v2/live-tour/action", json={"action": name, "payload": payload,
                       "expected_revision": shared["revision"], "idempotency_key": str(uuid4()), **overrides})


def test_pending_price_note_and_snapshot_do_not_reprice_or_touch_completed_work():
    state, pending = pending_state()
    old = deepcopy(state)
    for service in state["services"]:
        service["price"] = 99999
    result = action(state, "pending_update", {"pending_id": pending["id"], "note": "Ghi chú", "reason": "Sửa ghi chú"})
    assert result["pending"]["entries"][0]["price"] == 100
    result = action(state, "pending_update", {"pending_id": pending["id"], "entries": [{"index": 0, "price": 150}], "reason": "Đối soát giá"})
    assert result["pending"]["entries"][0]["price"] == 150
    assert state["employees"] == old["employees"]
    assert state["invoices"] == old["invoices"] and state["reports"] == old["reports"]
    assert state["pending_changes"][0]["before"] == pending
    assert len(state["pending_changes"]) == 2


@pytest.mark.parametrize("payload", [
    {"reason": ""}, {"reason": "x", "customer_id": "other"},
    {"reason": "x", "entries": [{"index": 0, "price": -1}]},
    {"reason": "x", "entries": [{"index": 0, "price": 1}, {"index": 0, "price": 2}]},
    {"reason": "x", "entries": [{"index": True, "price": 1}]},
    {"reason": "x", "entries": [{"index": 0, "service_items": []}]},
])
def test_invalid_pending_update_is_atomic(payload):
    state, pending = pending_state()
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "pending_update", {"pending_id": pending["id"], **payload})
    assert state == before


def combo_pending():
    state, skin, body, customer, owned = setup()
    action(state, "booking", booking(customer, owned, skin))
    action(state, "start", {"employee_id": "e1"})
    pending = action(state, "finish_to_pending", {"employee_id": "e1"})["pending"]
    return state, skin, body, customer, owned, pending


def test_pending_service_edit_recalculates_only_its_reservations_and_delete_releases():
    state, skin, body, customer, owned, pending = combo_pending()
    old_ledger = deepcopy(state["customers"])
    result = action(state, "pending_update", {"pending_id": pending["id"], "reason": "Đổi đúng dịch vụ",
                    "entries": [{"index": 0, "service_items": [{"service_id": body["id"], "quantity": 2}]}]})
    assert result["pending"]["entries"][0]["combo_reserved_units"] == 2
    assert state["customers"] == old_ledger
    current = state["customers"][0]["combo_purchases"][0]
    assert live._available_combo(state, customer["id"], current)["remaining"] == 1
    action(state, "pending_delete", {"pending_id": pending["id"], "reason": "Hủy phiếu nhầm"})
    assert state["pending"] == [] and state["customers"] == old_ledger
    assert live._available_combo(state, customer["id"], current)["remaining"] == 3
    assert state["pending_changes"][-1]["before"]["entries"][0]["combo_reserved_units"] == 2
    assert state["pending_changes"][-1]["after"] is None


def test_pending_edit_does_not_take_another_bookings_tickets():
    state, _, body, customer, owned, pending = combo_pending()
    action(state, "booking", booking(customer, owned, body, worker="e2", quantity=2))
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "pending_update", {"pending_id": pending["id"], "reason": "Không đủ vé",
                     "entries": [{"index": 0, "service_items": [{"service_id": body["id"], "quantity": 1}]}]})
    assert state == before


def test_paid_edit_updates_receipt_and_reports_without_rewriting_identity():
    state, paid = paid_state()
    before = deepcopy(state)
    changed = action(state, "paid_invoice_update", {"invoice_id": paid["id"], "reason": "Đối soát",
                     "entries": [{"index": 0, "price": 150}], "discount": 10, "tip": 25,
                     "payment_method": "CHUYỂN KHOẢN", "note": "Đã đối soát"})["invoice"]
    assert changed["subtotal"] == 150 and changed["total"] == 165
    assert sum(row["total"] for row in state["reports"]) == 165
    assert sum(row["tip"] for row in state["reports"]) == 25
    for key in ("id", "bill_no", "actor", "created_at", "business_date", "customer_id"):
        assert changed[key] == paid[key]
    assert state["employees"] == before["employees"] and state["bill_counters"] == before["bill_counters"]
    assert state["invoice_changes"][0]["before"] == paid
    assert state["invoice_changes"][0]["reports_before"] == before["reports"]


@pytest.mark.parametrize("payload", [
    {"reason": ""}, {"reason": "x", "customer_id": "other"}, {"reason": "x", "business_date": "2025-01-01"},
    {"reason": "x", "entries": [{"index": 0, "price": -1}]},
    {"reason": "x", "entries": [{"index": 0, "service_items": []}]},
    {"reason": "x", "discount": 101}, {"reason": "x", "tip": True},
    {"reason": "x", "payment_method": "COMBO"}, {"reason": "x", "tip": 10_000_000_001},
])
def test_invalid_paid_edit_is_atomic(payload):
    state, paid = paid_state()
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "paid_invoice_update", {"invoice_id": paid["id"], **payload})
    assert state == before


def test_paid_void_removes_active_totals_but_preserves_evidence_and_bill_numbers():
    state, paid = paid_state()
    before = deepcopy(state)
    action(state, "paid_invoice_delete", {"invoice_id": paid["id"], "reason": "Nhập trùng"})
    assert not state["invoices"] and not state["reports"]
    assert state["invoice_changes"][0]["before"] == paid
    assert state["bill_counters"] == before["bill_counters"] and state["employees"] == before["employees"]
    assert live._state_response(state, 2, NOW, can_payment=True)["reports"]["total_revenue"] == 0
    assert live._export_rows(state, "revenue", NOW, bounds=live._parse_export_bounds())[2] == []
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "paid_invoice_delete", {"invoice_id": paid["id"], "reason": "Lặp"})
    assert state == before


def test_combo_redemption_edit_does_not_double_debit_and_void_restores_original_components():
    state, _, _, customer, owned, pending = combo_pending()
    paid = action(state, "checkout", {"pending_id": pending["id"], "combo_purchase_id": owned["id"], "payment_method": "COMBO", "tip": 20})["invoice"]
    ledger = deepcopy(state["customers"])
    changed = action(state, "paid_invoice_update", {"invoice_id": paid["id"], "reason": "Sửa TIP", "tip": 35})["invoice"]
    assert changed["total"] == 35 and state["customers"] == ledger
    # The catalog may have changed: refunds must use the original debit plan.
    for service in state["services"]:
        service.update(ticket_units=99, active=False)
    action(state, "paid_invoice_delete", {"invoice_id": paid["id"], "reason": "Hủy lượt dùng"})
    current = state["customers"][0]["combo_purchases"][0]
    assert current["remaining"] == 3 and current["used"] == 0
    assert [row["remaining"] for row in current["component_balances"]] == [1, 2]
    assert not state["combo_usage"]
    assert len(state["invoices"]) == 1  # original combo-sale invoice survives


def test_combo_sale_cannot_be_voided_with_reservations_but_can_after_pending_void():
    state, _, _, _, _, pending = combo_pending()
    sale_id = state["invoices"][0]["id"]
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "paid_invoice_delete", {"invoice_id": sale_id, "reason": "Hủy bán combo"})
    assert state == before
    action(state, "pending_delete", {"pending_id": pending["id"], "reason": "Hủy giữ chỗ"})
    action(state, "paid_invoice_delete", {"invoice_id": sale_id, "reason": "Hủy bán combo chưa dùng"})
    assert state["customers"][0]["combo_purchases"] == []
    assert not state["invoices"] and not state["reports"]


def test_backup_restore_never_resurrects_voided_invoices_or_drops_corrections():
    state, paid = paid_state()
    backup = action(state, "backup", {})["backup"]
    action(state, "paid_invoice_delete", {"invoice_id": paid["id"], "reason": "Hủy"})
    changes = deepcopy(state["invoice_changes"])
    action(state, "restore", {"backup_id": backup["id"]})
    assert not state["invoices"] and not state["reports"] and state["invoice_changes"] == changes


@pytest.mark.parametrize("name,grant,view", [
    ("pending_update", "live_tour_invoice_edit", "live_tour_invoice_view"),
    ("pending_delete", "live_tour_invoice_delete", "live_tour_invoice_view"),
    ("paid_invoice_update", "live_tour_paid_invoice_edit", "live_tour_paid_invoice_view"),
    ("paid_invoice_delete", "live_tour_paid_invoice_delete", "live_tour_paid_invoice_view"),
])
def test_http_write_permissions_revision_idempotency_and_revocation(monkeypatch, name, grant, view):
    state, target = paid_state() if name.startswith("paid_") else pending_state()
    grants = ALL - {grant}
    client, shared = scoped_client(monkeypatch, state, grants)
    payload = {"invoice_id" if name.startswith("paid_") else "pending_id": target["id"], "reason": "Đối soát"}
    assert post(client, shared, name, payload).status_code == 403
    grants.add(grant)
    grants.remove(view)
    assert post(client, shared, name, payload).status_code == 403
    grants.add(view)
    assert post(client, shared, name, payload, expected_revision=0).status_code == 409
    assert post(client, shared, name, payload, expected_revision=None).status_code == 428
    assert post(client, shared, name, payload, idempotency_key="").status_code == 422
    assert post(client, shared, name, payload, idempotency_key=None).status_code == 400
    result = post(client, shared, name, payload, idempotency_key="invoice-correction-key")
    assert result.status_code == 200, result.text
    before = deepcopy(shared)
    replay = post(client, shared, name, payload, idempotency_key="invoice-correction-key", expected_revision=1)
    assert replay.status_code == 200 and replay.json()["duplicate"] is True
    assert shared == before
    grants.remove(grant)
    assert post(client, shared, name, payload, idempotency_key="invoice-correction-key").status_code == 403
    assert shared == before


@pytest.mark.parametrize("feature", list(CAPABILITY_FEATURES.values()))
def test_read_denials_are_explicit_even_with_legacy_admin_payment(monkeypatch, feature):
    state, paid = paid_state()
    state["pending"] = [{"id": "p1", "entries": [], "customer_name": "Private pending"}]
    state["customers"] = [{"id": "c1", "name": "Private customer", "combo_purchases": []}]
    action(state, "backup", {})
    client, _ = scoped_client(monkeypatch, state, ALL - {feature})
    data = client.get("/v2/live-tour").json()
    capability = next(key for key, value in CAPABILITY_FEATURES.items() if value == feature)
    assert data["capabilities"][capability] is False
    if feature in {"live_tour_pending_view", "live_tour_invoice_view"}:
        assert not data["pending"] and not data["pending_payments"] and not data["state"]["pending"]
    if feature == "live_tour_paid_invoice_view":
        assert not data["state"]["invoices"] and not data["invoice_changes"]
    if feature == "live_tour_customers_view":
        assert not data["customers"] and not data["state"]["customers"] and not data["state"]["combo_usage"]
        assert client.get("/v2/live-tour/customers").status_code == 403
        assert client.get("/v2/live-tour/customers/c1/history").status_code == 403
    if feature == "live_tour_reports_view":
        assert not data["reports"] and not data["report_rows"] and not data["state"]["reports"]
    if feature == "live_tour_history_view":
        assert not data["audit"] and not data["history"] and not data["state"]["audit"] and not data["break_events"]
    if feature == "live_tour_backup":
        assert not data["backups"] and not data["state"]["backups"]


@pytest.mark.parametrize("kind,feature", [(kind, feature) for kind, features in EXPORT_FEATURES.items() for feature in features])
def test_exports_require_every_associated_read_grant(monkeypatch, kind, feature):
    state, _ = paid_state()
    client, _ = scoped_client(monkeypatch, state, ALL - {feature})
    assert client.get("/v2/live-tour/export.xlsx", params={"kind": kind, "customer_id": "c1"}).status_code == 403


def test_new_booking_permission_is_independent_from_operation_and_payment(monkeypatch):
    state = payable_state()
    live._clear_assignment(state["employees"][0], NOW)
    grants = {"live_tour_view", "live_tour_booking"}
    client, shared = scoped_client(monkeypatch, state, grants)
    payload = {"employee_id": "e1", "service": "Body 90", "room": "1.1"}
    assert post(client, shared, "booking", {**payload, "start_now": True}).status_code == 403
    assert post(client, shared, "booking", payload).status_code == 200
    assert post(client, shared, "start", {"employee_id": "e1"}).status_code == 403


def test_destructive_grants_never_implicitly_inherit():
    from vera_web_v2_permissions import DEFAULT_ROLE_FEATURES, FEATURES
    for feature in ("live_tour_invoice_edit", "live_tour_invoice_delete", "live_tour_paid_invoice_edit", "live_tour_paid_invoice_delete"):
        assert feature in FEATURES and feature not in LEGACY_FEATURE_INHERITANCE
        assert all(feature not in features for role, features in DEFAULT_ROLE_FEATURES.items() if role != "admin")


@pytest.mark.parametrize("feature,parent", list(LEGACY_FEATURE_INHERITANCE.items()))
def test_real_permission_resolver_preserves_legacy_denials_and_explicit_new_overrides(feature, parent):
    from types import SimpleNamespace
    from vera_web_v2_api import _feature_allowed
    ident = SimpleNamespace(role="letan", employee_username="reception")
    payload = {"roles": [{"target": "letan", "feature": parent, "allowed": True}], "accounts": []}
    assert _feature_allowed(None, ident, feature, payload) is True
    payload["accounts"].append({"target": "reception", "feature": parent, "allowed": False})
    assert _feature_allowed(None, ident, feature, payload) is False
    payload["roles"].append({"target": "letan", "feature": feature, "allowed": True})
    assert _feature_allowed(None, ident, feature, payload) is True
    payload["accounts"].append({"target": "reception", "feature": feature, "allowed": False})
    assert _feature_allowed(None, ident, feature, payload) is False
    ident.role = "admin"
    assert _feature_allowed(None, ident, feature, payload) is True


def test_voided_manual_bill_number_cannot_be_reused():
    state, paid = paid_state()
    action(state, "paid_invoice_delete", {"invoice_id": paid["id"], "reason": "Hủy"})
    with pytest.raises(HTTPException):
        live._next_bill_no(state, {"bill_no": paid["bill_no"]}, NOW)
    assert live._next_bill_no(state, {}, NOW) != paid["bill_no"]


def test_room_finish_nested_results_do_not_leak_pending_details(monkeypatch):
    from test_live_tour_room_actions import mixed_room
    grants = {"live_tour_view", "live_tour_operate", "live_tour_customers_view"}
    client, shared = scoped_client(monkeypatch, mixed_room(), grants)
    response = post(client, shared, "finish_room", {"room": "1"})
    assert response.status_code == 200, response.text
    for item in response.json()["result"]["items"]:
        assert set(item["pending"]) == {"id"}


def test_checkout_retry_cannot_print_a_voided_invoice(monkeypatch):
    client, shared = api_client(monkeypatch, payable_state())
    payload = {"employee_id": "e1", "payment_method": "TIỀN MẶT"}
    checkout = post(client, shared, "checkout", payload, idempotency_key="checkout-original")
    invoice = checkout.json()["result"]["invoice"]
    assert post(client, shared, "paid_invoice_delete", {"invoice_id": invoice["id"], "reason": "Hủy"}).status_code == 200
    before = deepcopy(shared)
    replay = post(client, shared, "checkout", payload, idempotency_key="checkout-original")
    assert replay.status_code == 200 and replay.json()["duplicate"]
    assert replay.json()["result"]["invoice"] is None and replay.json()["result"]["voided"]
    assert shared == before


def test_customer_history_read_filters_other_independently_denied_ledgers(monkeypatch):
    state, _, _, customer, _, _ = combo_pending()
    grants = {"live_tour_view", "live_tour_customers_view"}
    client, _ = scoped_client(monkeypatch, state, grants)
    value = client.get(f"/v2/live-tour/customers/{customer['id']}/history").json()
    assert value["combo_purchases"]
    assert not value["invoices"] and not value["pending"] and not value["reports"] and not value["services"]


@pytest.mark.parametrize("problem", ["missing_usage", "wrong_units", "insufficient_used", "bad_component", "sale_used"])
def test_corrupted_or_used_combo_cannot_be_refunded_or_removed(problem):
    state, _, _, _, owned, pending = combo_pending()
    invoice = action(state, "checkout", {"pending_id": pending["id"], "combo_purchase_id": owned["id"], "payment_method": "COMBO"})["invoice"]
    current = state["customers"][0]["combo_purchases"][0]
    if problem == "missing_usage":
        state["combo_usage"] = []
    elif problem == "wrong_units":
        state["combo_usage"][0]["units"] = 99
    elif problem == "insufficient_used":
        current["used"] = 0
    elif problem == "bad_component":
        current["component_balances"][0]["used"] = 0
    else:
        invoice = state["invoices"][0]  # can't cancel sale while redemption is active
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        action(state, "paid_invoice_delete", {"invoice_id": invoice["id"], "reason": "Đối soát"})
    assert state == before


def test_legacy_combo_void_returns_tickets_without_guessing_catalog_units():
    state, paid = paid_state()
    state["customers"] = [{"id": "c1", "name": "A", "combo_purchases": [{"id": "p1", "total": 5, "used": 2, "remaining": 3}]}]
    paid.update(customer_id="c1", payment_method="COMBO", combo_purchase_id="p1", combo_units=2)
    state["combo_usage"] = [{"id": "u1", "invoice_id": paid["id"], "customer_id": "c1", "combo_purchase_id": "p1", "units": 2}]
    action(state, "paid_invoice_delete", {"invoice_id": paid["id"], "reason": "Hủy vé cũ"})
    purchase = state["customers"][0]["combo_purchases"][0]
    assert purchase["used"] == 0 and purchase["remaining"] == 5


def test_void_and_audit_survive_reopening_server_state():
    from test_live_tour_server_only import SettingsDatabase, app_client
    state, paid = paid_state()
    database = SettingsDatabase(stored=state)
    _, client = app_client(database)
    revision = client.get("/v2/live-tour").json()["revision"]
    body = {"action": "paid_invoice_delete", "payload": {"invoice_id": paid["id"], "reason": "Hủy lưu server"},
            "expected_revision": revision, "idempotency_key": "persistent-void-key"}
    response = client.post("/v2/live-tour/action", json=body)
    assert response.status_code == 200, response.text
    _, reopened = app_client(database)
    value = reopened.get("/v2/live-tour").json()
    assert not value["state"]["invoices"] and value["reports"]["total_revenue"] == 0
    assert value["invoice_changes"][0]["before"]["id"] == paid["id"]
    assert reopened.post("/v2/live-tour/action", json=body).json()["duplicate"] is True
    assert len(database.stored["invoice_changes"]) == 1


def test_payment_permission_does_not_create_customers_through_checkout_when_denied(monkeypatch):
    client, shared = scoped_client(monkeypatch, payable_state(), ALL - {"live_tour_customers_view"})
    before = deepcopy(shared)
    response = post(client, shared, "checkout", {"employee_id": "e1", "payment_method": "TIỀN MẶT", "customer_name": "New customer"})
    assert response.status_code == 403 and shared == before
    assert post(client, shared, "checkout", {"employee_id": "e1", "payment_method": "TIỀN MẶT"}).status_code == 200


def test_paid_read_denial_also_hides_checkout_result_and_financial_audit(monkeypatch):
    grants = ALL - {"live_tour_paid_invoice_view"}
    client, shared = scoped_client(monkeypatch, payable_state(), grants)
    response = post(client, shared, "checkout", {"employee_id": "e1", "payment_method": "TIỀN MẶT"})
    assert response.status_code == 200
    value = response.json()
    assert "invoice" not in value["result"] and not value["state"]["invoices"]
    assert value["audit"][-1]["detail"] == {"summary": "Nội dung cần quyền xem tương ứng."}

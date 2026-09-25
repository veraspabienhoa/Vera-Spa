"""Admin authority is server-owned; corrections retain ledger integrity."""
from copy import deepcopy
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteEngine
from test_live_tour_invoice_permissions import paid_state, pending_state, combo_pending, post
from test_live_tour_safety import api_client
from test_service_catalog import action


def client_for(monkeypatch, state, role="admin"):
    class Identity(BaseModel):
        # A non-admin account named admin must not acquire the override.
        employee_username: str = "admin"
        full_name: str = "Test operator"
        role: str

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(live, "datetime", FixedDateTime)
    _, shared = api_client(monkeypatch, state)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine,
        current_identity=lambda: Identity(role=role), identity_type=Identity,
        require_feature=lambda *args: None, feature_allowed=lambda *args: True)
    return TestClient(app), shared


@pytest.mark.parametrize("name", ["pending_update", "pending_delete", "paid_invoice_update",
                                   "paid_invoice_delete", "report_invoice_update", "report_invoice_delete"])
def test_admin_can_correct_old_invoices_without_reason_and_replay_once(monkeypatch, name):
    pending = name.startswith("pending_")
    state, item = pending_state() if pending else paid_state()
    item["business_date"] = "2020-01-01"
    client, shared = client_for(monkeypatch, state)
    payload = {"pending_id" if pending else "invoice_id": item["id"]}
    if name.endswith("update"):
        payload.update(note="Admin correction", invoice_at="2021-02-03T09:15:00+07:00")
    response = post(client, shared, name, payload, idempotency_key="admin-old-invoice")
    assert response.status_code == 200, response.text
    history = shared["state"]["pending_changes" if pending else "invoice_changes"][-1]
    assert history["admin_override"] is True
    assert history["actor"] == "admin" and history["reason"] == "Admin điều chỉnh hóa đơn"
    assert history["before"]["business_date"] == "2020-01-01"
    if name.endswith("update"):
        assert history["after"]["business_date"] == "2021-02-03"
        if not pending:
            assert all(row["business_date"] == "2021-02-03" for row in shared["state"]["reports"])
    else:
        assert history["after"] is None
    before = deepcopy(shared)
    replay = post(client, shared, name, payload, idempotency_key="admin-old-invoice", expected_revision=1)
    assert replay.status_code == 200 and replay.json()["duplicate"] is True
    assert shared == before


@pytest.mark.parametrize("role", ["letan", "quanly", "nhanvien", ""])
@pytest.mark.parametrize("name", ["pending_update", "pending_delete", "paid_invoice_delete", "report_invoice_delete"])
def test_all_delegated_grants_and_admin_account_name_do_not_bypass_date(monkeypatch, role, name):
    state, item = pending_state() if name.startswith("pending_") else paid_state()
    item["business_date"] = "2020-01-01"
    client, shared = client_for(monkeypatch, state, role)
    before = deepcopy(shared)
    payload = {"pending_id" if name.startswith("pending_") else "invoice_id": item["id"], "reason": "Correction"}
    response = post(client, shared, name, payload)
    assert response.status_code == 403, response.text
    assert shared == before


@pytest.mark.parametrize("flag", ["admin_invoice_override", "_admin_invoice_override", "admin_override", "_actor_role", "role"])
def test_payload_cannot_claim_admin_authority(monkeypatch, flag):
    state, paid = paid_state()
    paid["business_date"] = "2020-01-01"
    client, shared = client_for(monkeypatch, state, "letan")
    before = deepcopy(shared)
    response = post(client, shared, "paid_invoice_delete", {"invoice_id": paid["id"], "reason": "Correction", flag: "admin"})
    assert response.status_code == 400, response.text
    assert shared == before


@pytest.mark.parametrize("role", ["letan", "quanly"])
def test_non_admin_still_needs_reason(monkeypatch, role):
    state, paid = paid_state()
    client, shared = client_for(monkeypatch, state, role)
    assert post(client, shared, "paid_invoice_delete", {"invoice_id": paid["id"]}).status_code == 400


@pytest.mark.parametrize("redeemed", [False, True])
def test_admin_voids_combo_sale_without_orphaning_bookings_or_redemptions(monkeypatch, redeemed):
    state, _, _, _, owned, pending = combo_pending()
    sale = deepcopy(state["invoices"][0])
    if redeemed:
        redemption = action(state, "checkout", {"pending_id": pending["id"], "combo_purchase_id": owned["id"], "payment_method": "COMBO", "tip": 20})["invoice"]
    before = deepcopy(state)
    client, shared = client_for(monkeypatch, state)
    response = post(client, shared, "paid_invoice_delete", {"invoice_id": sale["id"]})
    assert response.status_code == 200, response.text
    after = shared["state"]
    purchase = after["customers"][0]["combo_purchases"][0]
    previous = before["customers"][0]["combo_purchases"][0]
    for key in ("id", "used", "remaining", "total", "component_balances"):
        assert purchase[key] == previous[key]
    assert purchase["price"] == 0 and purchase["sale_invoice_voided_by"] == "admin"
    assert after["pending"] == before["pending"] and after["employees"] == before["employees"]
    assert after["combo_usage"] == before["combo_usage"]
    assert all(row["invoice_id"] != sale["id"] for row in after["reports"])
    assert after["invoice_changes"][-1]["purchase_before"] == previous
    if redeemed:
        response = post(client, shared, "paid_invoice_delete", {"invoice_id": redemption["id"]})
        assert response.status_code == 200, response.text
        refunded = shared["state"]["customers"][0]["combo_purchases"][0]
        assert refunded["used"] == 0 and refunded["remaining"] == refunded["total"]
        assert not shared["state"]["combo_usage"]


def test_admin_malformed_money_is_rejected_atomically(monkeypatch):
    state, paid = paid_state()
    client, shared = client_for(monkeypatch, state)
    before = deepcopy(shared)
    response = post(client, shared, "paid_invoice_update", {"invoice_id": paid["id"], "tip": -1})
    assert response.status_code == 400
    assert shared == before

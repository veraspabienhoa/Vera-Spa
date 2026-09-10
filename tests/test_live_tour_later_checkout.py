"""Lễ tân can settle an existing booking on a later day without date-edit grants."""
from copy import deepcopy

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteEngine, RouteIdentity
from test_live_tour_safety import api_client, payable_state
from test_live_tour_invoice_permissions import post


class ReceptionIdentity(RouteIdentity):
    role: str = "letan"
    employee_username: str = "letan"


def reception_client(monkeypatch, state, grants):
    _, shared = api_client(monkeypatch, state)

    def require(_conn, identity, feature):
        assert identity.role == "letan"
        if feature not in grants:
            raise HTTPException(403, feature)

    app = FastAPI()
    live.install_live_tour_routes(
        app, engine_instance=RouteEngine, current_identity=lambda: ReceptionIdentity(),
        require_feature=require, feature_allowed=lambda _c, _i, feature: feature in grants,
        identity_type=ReceptionIdentity,
    )
    return TestClient(app), shared


def old_pending(method):
    state = payable_state()
    employee = state["employees"][0]
    employee.update(booked_at="2026-08-02T23:30:00+07:00", customer_id="c1", break_count=0)
    service = next(row for row in state["services"] if row["name"] == "Body 90")
    purchase = {
        "id": "p1", "combo_name": "Body", "total": 3, "used": 0, "remaining": 3,
        "active": True, "starts_on": "2026-08-01", "unlimited": False, "expires_on": "2026-08-05",
        "component_balances": [{"service_id": service["id"], "service_name": service["name"],
                                "total": 3, "used": 0, "remaining": 3}],
    }
    state["customers"] = [{"id": "c1", "name": "Khách cũ", "phone": "0901234567", "combo_purchases": [purchase]}]
    if method == "COMBO":
        employee["combo_purchase_id"] = "p1"
    pending = live._apply_action(state, "move_pending", {"employee_id": "e1"}, "letan", NOW)["pending"]
    # A new assignment on the same employee must survive settlement of the old bill.
    employee.update(service="Body 90", room="2", status="Đang chờ", booked_at=NOW.isoformat())
    return state, pending


GRANTS = {"live_tour_payment", "live_tour_pending_view", "live_tour_invoice_view"}


@pytest.mark.parametrize("action", ["checkout", "quick_checkout"])
@pytest.mark.parametrize("method", ["TIỀN MẶT", "THẺ", "COMBO"])
def test_reception_settles_old_pending_once_and_keeps_booking_date(monkeypatch, action, method):
    state, pending = old_pending(method)
    employees = deepcopy(state["employees"])
    grants = GRANTS | {"live_tour_customers_view"} if method == "COMBO" else GRANTS
    client, shared = reception_client(monkeypatch, state, grants)
    payload = {"pending_id": pending["id"], "payment_method": method, "tip": 20}
    if method == "COMBO":
        payload["combo_purchase_id"] = "p1"
    response = post(client, shared, action, payload, idempotency_key="old-pending-settlement")
    assert response.status_code == 200, response.text
    invoice = shared["state"]["invoices"][0]
    assert invoice["effective_at"] == pending["effective_at"] == "2026-08-02T23:30:00+07:00"
    assert invoice["business_date"] == "2026-08-02"
    assert invoice["recorded_at"] != invoice["effective_at"]
    assert invoice["actor"] == "letan"
    assert invoice["backdate_one_day"] is False
    assert shared["state"]["reports"][0]["effective_at"] == invoice["effective_at"]
    assert shared["state"]["employees"] == employees
    assert not shared["state"]["pending"]
    if method == "COMBO":
        purchase = shared["state"]["customers"][0]["combo_purchases"][0]
        assert purchase["remaining"] == 2 and purchase["used"] == 1
        assert invoice["total"] == 20
    after = deepcopy(shared)
    replay = post(client, shared, action, payload, idempotency_key="old-pending-settlement", expected_revision=1)
    assert replay.status_code == 200 and replay.json()["duplicate"] is True
    assert shared == after
    assert post(client, shared, action, payload).status_code == 404
    assert shared == after


@pytest.mark.parametrize("missing", sorted(GRANTS))
def test_old_booking_does_not_bypass_required_payment_and_read_permissions(monkeypatch, missing):
    state, pending = old_pending("TIỀN MẶT")
    client, shared = reception_client(monkeypatch, state, GRANTS - {missing})
    before = deepcopy(shared)
    response = post(client, shared, "checkout", {"pending_id": pending["id"], "payment_method": "TIỀN MẶT"})
    assert response.status_code == 403 and shared == before


def test_reception_payment_does_not_grant_invoice_date_editing(monkeypatch):
    state, pending = old_pending("TIỀN MẶT")
    client, shared = reception_client(monkeypatch, state, GRANTS | {"live_tour_invoice_edit"})
    before = deepcopy(shared)
    response = post(client, shared, "pending_update", {"pending_id": pending["id"], "invoice_at": NOW.isoformat(), "reason": "Đổi ngày"})
    assert response.status_code == 403 and shared == before

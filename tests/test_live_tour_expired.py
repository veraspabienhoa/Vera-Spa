from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_safety import api_client


def expired_state(now=NOW):
    state = state_with(employee("e1", "An"), employee("e2", "Bình"))
    for index, worker in enumerate(state["employees"]):
        worker.update(service="Body 90", duration=90, room=f"1.{index + 1}", status="DANG THUC HIEN",
                      started_at=live._iso(now - timedelta(minutes=105 - index)))
    return state


def test_preview_is_read_only_and_uses_exact_threshold():
    state = expired_state()
    before = deepcopy(state)
    preview = live._expired_preview(state, {}, NOW)
    assert state == before
    assert preview["count"] == 1
    assert preview["employees"][0]["employee_id"] == "e1"
    assert live._expired_preview(state, {"grace_minutes": 14}, NOW)["count"] == 2


@pytest.mark.parametrize("grace", [-1, 1441, 1.5, "nan", "", None])
def test_invalid_threshold_is_rejected(grace):
    with pytest.raises(HTTPException) as error:
        live._expired_preview(expired_state(), {"grace_minutes": grace}, NOW)
    assert error.value.status_code == 400


def test_newly_expired_employee_requires_another_preview():
    state = expired_state()
    preview = live._expired_preview(state, {}, NOW)
    before = deepcopy(state)
    with pytest.raises(HTTPException) as error:
        live._apply_action(state, "clear_expired", {"confirm_token": preview["preview_token"]}, "admin", NOW + timedelta(minutes=1))
    assert error.value.status_code == 409
    assert state == before


@pytest.mark.parametrize("payload", [{}, {"confirm_token": "forged"}, {"grace_minutes": 0}])
def test_cleanup_requires_matching_confirmation_before_any_write(payload):
    state = expired_state()
    before = deepcopy(state)
    with pytest.raises(HTTPException) as error:
        live._apply_action(state, "clear_expired", payload, "admin", NOW)
    assert error.value.status_code == 409
    assert state == before


def test_confirm_preserves_payable_assignment_and_financial_ledgers():
    state = expired_state()
    preview = live._expired_preview(state, {}, NOW)
    result = live._apply_action(state, "clear_expired", {"confirm_token": preview["preview_token"]}, "admin", NOW)
    assert result["marked_for_payment"] == 1
    assert state["employees"][0]["payment_status"] == "CHO THANH TOÁN"
    assert state["employees"][0]["service"] == "Body 90"
    assert state["employees"][1]["status"] == "DANG THUC HIEN"
    assert state["invoices"] == state["reports"] == []


def test_http_preview_confirm_revision_and_idempotent_replay(monkeypatch):
    client, shared = api_client(monkeypatch, expired_state(datetime.now(live.VN_TZ) - timedelta(minutes=10)))
    before = deepcopy(shared)
    preview = client.post("/v2/live-tour/action", json={"action": "clear_expired_preview", "expected_revision": 1, "payload": {}})
    assert preview.status_code == 200
    assert preview.json()["count"] == 2
    assert shared == before
    body = {"action": "clear_expired", "expected_revision": 1, "idempotency_key": "clear-expired-test", "payload": {"confirm_token": preview.json()["preview_token"]}}
    assert client.post("/v2/live-tour/action", json={**body, "expected_revision": 0}).status_code == 409
    assert client.post("/v2/live-tour/action", json=body).status_code == 200
    assert shared["revision"] == 2
    assert client.post("/v2/live-tour/action", json=body).status_code == 200
    assert shared["revision"] == 2
    assert live._required_action_feature("clear_expired_preview") == "live_tour_admin"

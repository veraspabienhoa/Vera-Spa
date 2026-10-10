"""Booking notes belong to one service; invoice notes are independent edits."""
from copy import deepcopy

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_quick_booking import scenario as quick_scenario
from test_live_tour_safety import api_client


def act(state, action, payload):
    return live._apply_action(state, action, payload, "operator", NOW)


def booked(*notes, start=True):
    state = state_with(*(employee(f"e{i}", f"Employee {i}") for i in range(1, len(notes) + 1)))
    service = next(row for row in state["services"] if row["name"] == "Body 90")
    service["price"] = 100
    for i, note in enumerate(notes, 1):
        act(state, "booking", {"employee_id": f"e{i}", "room": f"1.{i}",
            "service_items": [{"service_id": service["id"], "quantity": 1}],
            "note": note, "start_now": start, "customer_name": "Shared customer", "customer_phone": "0901234567"})
    return state


def source_notes(item):
    return {entry["employee_id"]: entry["note"] for entry in item["entries"]}


def test_new_booking_does_not_inherit_idle_employee_note():
    state = state_with(employee("e1", "An"))
    state["employees"][0]["note"] = "Private note from an old assignment"
    act(state, "booking", {"employee_id": "e1", "room": "1.1", "service": "Body 90"})
    assert state["employees"][0]["note"] == ""


@pytest.mark.parametrize("payload,expected", [({}, "Original"), ({"note": "Revised"}, "Revised"), ({"note": ""}, "")])
@pytest.mark.parametrize("start", [False, True])
def test_booking_edit_preserves_omitted_note_and_accepts_explicit_clear(payload, expected, start):
    state = booked("Original", start=start)
    entry = state["employees"][0]
    act(state, "update_booking", {"employee_id": "e1", "room": "1.1", "service_items": entry["service_items"], **payload})
    assert state["employees"][0]["note"] == expected
    reloaded = live._normalize_state(deepcopy(state), NOW)
    assert reloaded["employees"][0]["note"] == expected
    assert live._state_response(reloaded, 1, NOW)["records"][0]["Ghi chú"] == expected


@pytest.mark.parametrize("with_services", [False, True])
@pytest.mark.parametrize("note_payload,expected", [({}, "Original"), ({"note": "Updated at Finish"}, "Updated at Finish"), ({"note": ""}, "")])
def test_finish_snapshots_note_before_releasing_employee(with_services, note_payload, expected):
    state = booked("Original")
    payload = {"employee_id": "e1", **note_payload}
    if with_services:
        payload["service_items"] = state["employees"][0]["service_items"]
    pending = act(state, "finish_to_pending", payload)["pending"]
    assert pending["note"] == expected
    assert source_notes(pending) == {"e1": expected}
    assert state["employees"][0]["note"] == ""
    assert state["employees"][0]["service"] == ""
    assert live._employee_record(state["employees"][0], NOW)["Ghi chú"] == ""


@pytest.mark.parametrize("action,payload", [("finish_to_pending", {"employee_ids": ["e1", "e2"]}), ("finish_room", {"room": "1"})])
def test_batch_and_room_finish_keep_each_booking_note(action, payload):
    state = booked("First guest note", "Second guest note")
    result = act(state, action, payload)
    assert result["count"] == 2
    assert {row["entries"][0]["employee_id"]: row["note"] for row in state["pending"]} == {
        "e1": "First guest note", "e2": "Second guest note"}
    assert all(row["entries"][0]["note"] == row["note"] for row in state["pending"])
    assert all(row["note"] == "" for row in state["employees"])


@pytest.mark.parametrize("invoice_note", [None, "", "Cashier note"])
def test_group_pending_keeps_distinct_sources_and_separate_invoice_note(invoice_note):
    state = booked("First guest note", "Second guest note", "First guest note", "  ")
    ids = [row["id"] for row in state["employees"]]
    act(state, "complete", {"employee_ids": ids})
    payload = {"employee_ids": ids}
    if invoice_note is not None:
        payload["note"] = invoice_note
    pending = act(state, "move_pending", payload)["pending"]
    assert pending["note"] == ("First guest note\nSecond guest note" if invoice_note is None else invoice_note)
    assert source_notes(pending) == dict(zip(ids, ["First guest note", "Second guest note", "First guest note", "  "]))
    assert all(row["note"] == "" for row in state["employees"])


@pytest.mark.parametrize("quick", [False, True])
@pytest.mark.parametrize("via_pending", [False, True])
@pytest.mark.parametrize("note_payload,expected", [({}, "One\nTwo"), ({"note": ""}, ""), ({"note": "Payment note"}, "Payment note")])
def test_group_checkout_keeps_source_notes_when_invoice_note_is_omitted_or_changed(quick, via_pending, note_payload, expected):
    state = booked("One", "Two")
    act(state, "complete", {"employee_ids": ["e1", "e2"]})
    source = {"employee_ids": ["e1", "e2"]}
    if via_pending:
        pending = act(state, "move_pending", source)["pending"]
        source = {"pending_id": pending["id"]}
        # A new assignment must never be used as the old pending invoice's source.
        act(state, "booking", {"employee_id": "e1", "room": "2.1", "service": "Body 90", "note": "Next guest"})
    invoice = act(state, "quick_checkout" if quick else "checkout", {**source, "payment_method": "TIỀN MẶT", **note_payload})["invoice"]
    assert invoice["note"] == expected
    assert source_notes(invoice) == {"e1": "One", "e2": "Two"}
    assert (invoice["subtotal"], invoice["discount"], invoice["tip"], invoice["total"]) == (200, 0, 0, 200)
    assert {row["employee_id"]: row["booking_note"] for row in state["reports"]} == {"e1": "One", "e2": "Two"}
    assert all(row["note"] == expected for row in state["reports"])
    history = live._customer_history(state, invoice["customer_id"])
    assert source_notes(history["invoices"][0]) == {"e1": "One", "e2": "Two"}
    assert {row["employee_id"]: row["note"] for row in history["services"]} == {"e1": "One", "e2": "Two"}
    assert all(row["invoice_note"] == expected for row in history["services"])
    if via_pending:
        assert state["employees"][0]["note"] == "Next guest"
    else:
        assert all(row["note"] == "" for row in state["employees"])


@pytest.mark.parametrize("saved_note,expected", [(None, "Original"), ("", ""), ("Edited pending note", "Edited pending note")])
def test_checkout_prefers_saved_pending_note_including_empty(saved_note, expected):
    state = booked("Original")
    pending = act(state, "finish_to_pending", {"employee_id": "e1"})["pending"]
    if saved_note is None:
        del pending["note"]  # A legacy record with source snapshots, no invoice-level note.
    else:
        before = deepcopy(pending)
        act(state, "pending_update", {"pending_id": pending["id"], "note": saved_note, "reason": "Review invoice"})
        assert state["pending_changes"][0]["before"] == before
        assert state["pending_changes"][0]["after"]["entries"] == before["entries"]
    invoice = act(state, "checkout", {"pending_id": pending["id"], "payment_method": "TIỀN MẶT"})["invoice"]
    assert invoice["note"] == expected
    assert source_notes(invoice) == {"e1": "Original"}


def test_pending_and_paid_corrections_cannot_rewrite_booking_snapshot():
    state = booked("Immutable booking note")
    pending = act(state, "finish_to_pending", {"employee_id": "e1"})["pending"]
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, "pending_update", {"pending_id": pending["id"], "entries": [{"index": 0, "note": "Overwrite"}], "reason": "Correction"})
    assert state == before
    invoice = act(state, "checkout", {"pending_id": pending["id"], "payment_method": "TIỀN MẶT"})["invoice"]
    act(state, "paid_invoice_update", {"invoice_id": invoice["id"], "note": "", "reason": "Clear invoice note"})
    assert state["invoices"][0]["note"] == ""
    assert state["invoices"][0]["entries"][0]["note"] == "Immutable booking note"
    assert state["reports"][0]["booking_note"] == "Immutable booking note"
    assert state["invoice_changes"][0]["before"]["note"] == "Immutable booking note"


@pytest.mark.parametrize("note_payload,expected", [({}, ""), ({"note": ""}, ""), ({"note": "Manual invoice"}, "Manual invoice")])
def test_manual_quick_checkout_never_copies_live_assignment_note(note_payload, expected):
    state, payload = quick_scenario()
    state["employees"][0].update(service="Other service", status="Đang thực hiện", note="Other guest private note")
    original = deepcopy(state["employees"])
    invoice = act(state, "quick_checkout", {**payload, **note_payload})["invoice"]
    assert invoice["note"] == expected
    assert not invoice["entries"][0].get("note")
    assert state["reports"][0]["booking_note"] == ""
    assert state["employees"] == original


def test_failed_finish_and_checkout_preserve_notes_and_history():
    state = booked("One", "Two")
    state["employees"][1]["status"] = "Đang chờ"
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, "finish_to_pending", {"employee_ids": ["e1", "e2"], "note": "Attempted edit"})
    assert state == before
    act(state, "finish_to_pending", {"employee_id": "e1"})
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, "checkout", {"pending_id": state["pending"][0]["id"], "payment_method": "COMBO", "note": "Attempted invoice edit"})
    assert state == before


def test_finish_and_payment_retries_keep_original_sources_after_new_booking(monkeypatch):
    state = booked("Original")
    client, shared = api_client(monkeypatch, state)
    finish = {"action": "finish_to_pending", "payload": {"employee_id": "e1"},
              "expected_revision": 1, "idempotency_key": "finish-booking-note-once"}
    first = client.post("/v2/live-tour/action", json=finish)
    assert first.status_code == 200, first.text
    pending = first.json()["result"]["pending"]
    assert pending["note"] == pending["entries"][0]["note"] == "Original"
    act(shared["state"], "booking", {"employee_id": "e1", "room": "1.1", "service": "Body 90", "note": "New guest"})
    shared["revision"] += 1
    before = deepcopy(shared)
    repeated = client.post("/v2/live-tour/action", json=finish)
    assert repeated.status_code == 200 and repeated.json()["duplicate"]
    assert repeated.json()["result"]["pending"] == pending
    assert shared == before
    checkout = {"action": "checkout", "payload": {"pending_id": pending["id"], "payment_method": "TIỀN MẶT", "note": ""},
                "expected_revision": shared["revision"], "idempotency_key": "pay-booking-note-once"}
    paid = client.post("/v2/live-tour/action", json=checkout)
    assert paid.status_code == 200, paid.text
    invoice = paid.json()["result"]["invoice"]
    assert invoice["note"] == "" and invoice["entries"][0]["note"] == "Original"
    before = deepcopy(shared)
    repeated = client.post("/v2/live-tour/action", json=checkout)
    assert repeated.status_code == 200 and repeated.json()["duplicate"]
    assert repeated.json()["result"]["invoice"] == invoice
    assert shared == before and shared["state"]["employees"][0]["note"] == "New guest"
    assert client.post("/v2/live-tour/action", json={**checkout, "idempotency_key": "stale-booking-note-pay"}).status_code == 409
    assert shared == before


def test_legacy_paid_records_are_not_backfilled_or_modified_on_normalization():
    state = state_with(employee("e1", "An"))
    state["invoices"] = [{"id": "legacy-paid", "note": "Original paid invoice", "entries": [{"employee_id": "e1"}]}]
    state["reports"] = [{"id": "legacy-report", "invoice_id": "legacy-paid", "note": "Original paid invoice"}]
    original = deepcopy(state)
    normalized = live._normalize_state(state, NOW)
    assert normalized["invoices"] == original["invoices"]
    assert normalized["reports"] == original["reports"]


def test_performance_note_projection_follows_live_pending_and_paid_sources():
    state = booked("First booking", "Second booking")
    act(state, "complete", {"employee_ids": ["e1", "e2"]})
    for stage in ("live", "pending", "invoice"):
        if stage == "pending":
            pending = act(state, "move_pending", {"employee_ids": ["e1", "e2"], "note": "Different invoice note"})["pending"]
        elif stage == "invoice":
            act(state, "checkout", {"pending_id": pending["id"], "payment_method": "TIỀN MẶT", "note": ""})
        before = deepcopy(state)
        rows = live._service_performance_rows(state)
        assert {row["employee_id"]: row["booking_note"] for row in rows} == {
            "e1": "First booking", "e2": "Second booking"}
        assert {row["source"] for row in rows} == {stage}
        assert state == before


def combo_note_state():
    from test_live_tour_combo_booking import setup, booking
    state, _, body, customer, owned = setup()
    for identifier, note in (("e1", "First booking"), ("e2", "Second booking")):
        act(state, "booking", {**booking(customer, owned, body, identifier), "note": note, "start_now": True})
    act(state, "complete", {"employee_ids": ["e1", "e2"]})
    invoice = act(state, "checkout", {"employee_ids": ["e1", "e2"], "payment_method": "COMBO",
        "combo_purchase_id": owned["id"], "customer_id": customer["id"], "note": ""})["invoice"]
    return state, invoice


def test_combo_history_projects_snapshot_notes_without_changing_aggregated_debit_rows():
    state, invoice = combo_note_state()
    before = deepcopy(state)
    usage = state["combo_usage"][0]
    assert len(usage["entries"]) == 1  # Two employees consumed the same component.
    result = live._customer_history(state, invoice["customer_id"])
    projected = result["combo_usage"][0]
    assert projected["entries"] == usage["entries"]
    assert projected["units"] == usage["units"] == invoice["combo_units"] == 2
    assert projected["remaining_after"] == usage["remaining_after"] == 1
    assert projected["invoice_note"] == ""
    assert {row["employee_id"]: (row["employee_name"], row["room"], row["note"]) for row in projected["booking_entries"]} == {
        "e1": ("An", "1.1", "First booking"), "e2": ("Bình", "2.1", "Second booking")}
    projected["booking_entries"][0]["note"] = "Do not write through"
    assert state == before
    assert "booking_entries" not in usage and "invoice_note" not in usage
    # The unrestricted raw usage alias must remain the original debit ledger.
    public = live._state_response(state, 1, NOW, can_customers_view=True)
    assert public["state"]["combo_usage"] == before["combo_usage"]


@pytest.mark.parametrize("source", ["missing", "other_customer"])
def test_combo_history_does_not_guess_notes_from_unmatched_invoice(source):
    state, invoice = combo_note_state()
    usage = state["combo_usage"][0]
    if source == "missing":
        usage["invoice_id"] = "missing-invoice"
    else:
        invoice["customer_id"] = "other-customer"
    before = deepcopy(state)
    result = live._customer_history(state, usage["customer_id"])
    assert result["combo_usage"][0] == usage
    assert state == before


@pytest.mark.parametrize("paid_view", [False, True])
def test_combo_history_note_projection_respects_paid_invoice_permission(monkeypatch, paid_view):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from test_live_tour_backend import RouteEngine, RouteIdentity
    state, invoice = combo_note_state()
    invoice["note"] = "Restricted invoice note"
    before = deepcopy(state)
    monkeypatch.setattr(live, "_read_state", lambda *_args, **_kwargs: (deepcopy(state), 1))
    grants = {"live_tour_view", "live_tour_customers_view"}
    if paid_view:
        grants.update({"live_tour_paid_invoice_view", "live_tour_invoices_date_all"})
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=lambda *_args: None, feature_allowed=lambda _conn, _identity, feature: feature in grants,
        identity_type=RouteIdentity)
    response = TestClient(app).get(f"/v2/live-tour/customers/{invoice['customer_id']}/history")
    assert response.status_code == 200, response.text
    result = response.json()
    usage = result["combo_usage"][0]
    assert usage["entries"] == state["combo_usage"][0]["entries"]
    if paid_view:
        assert usage["invoice_note"] == "Restricted invoice note"
        assert [row["note"] for row in usage["booking_entries"]] == ["First booking", "Second booking"]
    else:
        assert not result["invoices"]
        assert "booking_entries" not in usage and "invoice_note" not in usage
        assert "First booking" not in response.text and "Second booking" not in response.text
        assert "Restricted invoice note" not in response.text
    assert state == before

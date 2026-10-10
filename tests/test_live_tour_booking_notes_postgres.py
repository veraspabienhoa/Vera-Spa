"""Note snapshots commit with the invoice, report and durable replay receipt."""
from copy import deepcopy

import pytest
from fastapi import HTTPException

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW
from test_live_tour_payment_scope_postgres import payments, saved
from test_live_tour_resource_postgres import database


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("clear_invoice_note", [False, True])
def test_note_handoff_rollback_retry_and_old_ledger_integrity(database, payments, monkeypatch, pending, clear_invoice_note):
    client, body, seeded = payments
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        prepared = deepcopy(before)
        for index, worker in enumerate(prepared["employees"], 1):
            worker.update(note=f"Booking note {index}", service_price_source="catalog", booked_at=live._iso(NOW))
            if pending:
                worker.update(status="Đang thực hiện", started_at=live._iso(NOW), duration=90)
        revision = store.write(conn, before, prepared, "fixture")
    if pending:
        finish_body = {"action": "finish_to_pending", "payload": {"employee_ids": ["e1", "e2"]},
                       "expected_revision": revision, "response_view": "receipt", "idempotency_key": "finish-notes-once"}
        finished = client.post("/v2/live-tour/action", json=finish_body)
        assert finished.status_code == 200, finished.text
        persisted, revision = saved(database)
        assert len(persisted["pending"]) == 2
        assert all(row["note"] == "" for row in persisted["employees"])
        assert {row["entries"][0]["employee_id"]: row["entries"][0]["note"] for row in persisted["pending"]} == {
            "e1": "Booking note 1", "e2": "Booking note 2"}
        selected = next(row for row in persisted["pending"] if row["entries"][0]["employee_id"] == "e1")
        body["payload"] = {"pending_id": selected["id"], "payment_method": "TIỀN MẶT", "tip": 11}
        expected_notes = {"e1": "Booking note 1"}
        expected_default = "Booking note 1"
        # An already finished employee can immediately take another guest. A
        # retry and payment of the earlier pending record must not touch it.
        with database.begin() as conn:
            store.lock(conn)
            before, _, _ = store.read(conn)
            prepared = deepcopy(before)
            live._apply_action(prepared, "booking", {"employee_id": "e1", "service": "Body 90", "room": "1.1", "note": "Next guest"}, "operator", NOW)
            revision = store.write(conn, before, prepared, "operator")
        before_retry = saved(database)
        retry = client.post("/v2/live-tour/action", json=finish_body)
        assert retry.status_code == 200 and retry.json()["duplicate"]
        assert saved(database) == before_retry
    else:
        body["payload"] = {"employee_ids": ["e1", "e2"], "payment_method": "TIỀN MẶT", "tip": 11}
        expected_notes = {"e1": "Booking note 1", "e2": "Booking note 2"}
        expected_default = "Booking note 1\nBooking note 2"
    body["expected_revision"] = revision
    if clear_invoice_note:
        body["payload"]["note"] = ""
    baseline = saved(database)
    original_write = store.write

    def abort_after_write(*args):
        original_write(*args)
        raise HTTPException(503, "Injected transaction rollback")

    monkeypatch.setattr(store, "write", abort_after_write)
    failed = client.post("/v2/live-tour/action", json=body)
    assert failed.status_code == 503, failed.text
    assert saved(database) == baseline
    monkeypatch.setattr(store, "write", original_write)
    paid = client.post("/v2/live-tour/action", json=body)
    assert paid.status_code == 200, paid.text
    invoice = paid.json()["result"]["invoice"]
    assert invoice["note"] == ("" if clear_invoice_note else expected_default)
    assert {row["employee_id"]: row["note"] for row in invoice["entries"]} == expected_notes
    assert invoice["total"] == 100 * len(expected_notes) + 11
    current, paid_revision = saved(database)
    assert current["invoices"][:-1] == seeded["invoices"]
    assert current["reports"][:len(seeded["reports"])] == seeded["reports"]
    assert current["invoice_changes"] == seeded["invoice_changes"]
    assert all(current["idempotency"][key] == value for key, value in seeded["idempotency"].items())
    reports = [row for row in current["reports"] if row.get("invoice_id") == invoice["id"]]
    assert {row["employee_id"]: row["booking_note"] for row in reports} == expected_notes
    assert all(row["note"] == invoice["note"] for row in reports)
    assert current["idempotency"][body["idempotency_key"]]["result"]["invoice"] == invoice
    assert current["employees"][0]["note"] == ("Next guest" if pending else "")
    replay = client.post("/v2/live-tour/action", json=body)
    assert replay.status_code == 200 and replay.json()["duplicate"]
    assert replay.json()["result"]["invoice"] == invoice
    assert saved(database) == (current, paid_revision)
    changed = {**body, "payload": {**body["payload"], "note": "Different retry note"}}
    assert client.post("/v2/live-tour/action", json=changed).status_code == 409
    assert saved(database) == (current, paid_revision)

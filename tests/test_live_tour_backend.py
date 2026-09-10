from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from openpyxl import load_workbook
from pydantic import BaseModel

import vera_web_v2_live_tour as live

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 5, 15, 0, tzinfo=live.VN_TZ)


def employee(identifier: str, name: str, *, shift: str = "Ca 1", vip: bool = False):
    return {
        "id": identifier, "stt": identifier.removeprefix("e"), "name": name,
        "appointment": "", "service": "", "request": "", "room": "", "status": "",
        "duration": None, "started_at": "", "completed_at": "", "payment_status": "",
        "tour_count": 0, "request_count": 0, "work_status": "Đi làm", "shift": shift,
        "break_started_at": "", "clock_out": "", "clock_in": "", "note": "",
        "hidden": False, "vip": vip, "sort_index": int(identifier.removeprefix("e") or 0),
    }


def state_with(*employees):
    state = live._empty_state(NOW)
    state["employees"] = list(employees)
    return state


def payable_employee(identifier: str, name: str, *, customer_id: str = "c1", room: str = "1.1", service: str = "Body 90"):
    item = employee(identifier, name)
    item.update({
        "service": service, "service_price": 100, "room": room,
        "status": "CHO THANH TOÁN", "payment_status": "CHO THANH TOÁN",
        "customer_id": customer_id, "customer_name": f"Khách {customer_id}",
        "customer_phone": f"090{customer_id.removeprefix('c')}",
    })
    return item


class RouteIdentity(BaseModel):
    employee_username: str = "tester"
    full_name: str = "Test Operator"


class RouteConnection:
    def execution_options(self, **_kwargs):
        return self

    def execute(self, *_args, **_kwargs):
        class Result:
            rowcount = 1

            @staticmethod
            def scalar():
                return True

        return Result()

    def close(self):
        return None


class RouteEngine:
    @contextmanager
    def begin(self):
        yield RouteConnection()

    def connect(self):
        return RouteConnection()


def test_business_date_changes_exactly_at_1110_vietnam_time():
    before = datetime(2026, 9, 5, 11, 9, 59, tzinfo=live.VN_TZ)
    cutoff = datetime(2026, 9, 5, 11, 10, 0, tzinfo=live.VN_TZ)
    assert live._business_date(before).isoformat() == "2026-09-04"
    assert live._business_date(cutoff).isoformat() == "2026-09-05"


def test_private_service_locks_the_whole_room_group():
    first = employee("e1", "An")
    second = employee("e2", "Bình")
    state = state_with(first, second)
    live._booking(state, {"employee_id": "e1", "room": "19.1", "service": "Body 90"}, NOW)

    with pytest.raises(HTTPException) as error:
        live._booking(state, {"employee_id": "e2", "room": "19.2", "service": "VIP 90 PR"}, NOW)

    assert error.value.status_code == 409
    assert "PR" in str(error.value.detail)


def test_booking_then_start_increments_only_request_counter():
    ktv = employee("e1", "An")
    state = state_with(ktv)
    live._booking(state, {
        "employee_id": "e1", "room": "19.1", "service": "VIP 90 PR", "request": "YC",
    }, NOW)
    assert ktv["status"] == "Đang chờ"

    live._start_employee(state, ktv, NOW)

    assert ktv["status"] == "Đang thực hiện"
    assert ktv["booked_at"] == NOW.isoformat()
    assert ktv["wait_minutes"] == 0
    assert ktv["request_count"] == 1
    assert ktv["tour_count"] == 0
    with pytest.raises(HTTPException):
        live._start_employee(state, ktv, NOW)
    assert ktv["request_count"] == 1


def test_multi_booking_allocates_distinct_beds_in_requested_room_group():
    first = employee("e1", "An")
    second = employee("e2", "Bình")
    state = state_with(first, second)

    result = live._apply_action(state, "multi_booking", {
        "employee_ids": ["e1", "e2"], "room": "19.1", "service": "VIP 90",
    }, "admin", NOW)

    assert result["employees"][0]["room"] == "19.1"
    assert result["employees"][1]["room"] == "19.2"


def test_complete_releases_room_but_preserves_unpaid_row_and_vip():
    ktv = employee("e1", "An", vip=True)
    state = state_with(ktv)
    live._booking(state, {"employee_id": "e1", "room": "16.1", "service": "VIP 90"}, NOW)
    live._start_employee(state, ktv, NOW)

    live._apply_action(state, "complete", {"employee_id": "e1"}, "admin", NOW)

    assert ktv["status"] == "CHO THANH TOÁN"
    assert ktv["payment_status"] == "CHO THANH TOÁN"
    assert ktv["completion_delta_minutes"] == -90
    assert ktv["room"] == "16.1"
    assert not live._active_booking(ktv)
    assert live._room_available(state, "16.1")
    assert ktv["vip"] is True


def test_completion_result_survives_pending_checkout_report_and_customer_history():
    ktv = employee("e1", "An")
    ktv.update({
        "service": "Body 90", "service_price": 100, "service_price_source": "catalog",
        "room": "1.1", "status": "Đang thực hiện", "started_at": (NOW - timedelta(minutes=60)).isoformat(),
        "duration": 90,
    })
    state = state_with(ktv)
    next(item for item in state["services"] if item["name"] == "Body 90")["price"] = 100

    live._apply_action(state, "complete", {"employee_id": "e1"}, "admin", NOW)
    assert ktv["completion_delta_minutes"] == -30
    assert ktv["completion_note"] == "Sớm 30 phút"
    pending = live._apply_action(
        state, "move_pending", {"employee_id": "e1"}, "admin", NOW,
    )["pending"]
    assert pending["entries"][0]["completion_note"] == "Sớm 30 phút"

    invoice = live._apply_action(state, "checkout", {
        "pending_id": pending["id"], "customer_name": "Khách A", "customer_phone": "0901",
        "payment_method": "TIỀN MẶT",
    }, "admin", NOW)["invoice"]
    customer_id = invoice["customer_id"]

    assert invoice["entries"][0]["completion_delta_minutes"] == -30
    assert state["reports"][-1]["completion_note"] == "Sớm 30 phút"
    assert live._customer_history(state, customer_id)["services"][0]["completion_note"] == "Sớm 30 phút"
    assert ktv["completion_note"] == ""


def test_vip_room_inference_is_limited_to_groups_16_through_21():
    state = state_with()
    room_16 = live._apply_action(state, "room_upsert", {"name": "16.9"}, "admin", NOW)["room"]
    room_21 = live._apply_action(state, "room_upsert", {"name": "21.9"}, "admin", NOW)["room"]
    room_22 = live._apply_action(state, "room_upsert", {"name": "22.1"}, "admin", NOW)["room"]

    assert room_16["type"] == "vip"
    assert room_21["type"] == "vip"
    assert room_22["type"] == "standard"


def test_checkout_is_atomic_for_invoice_report_combo_and_preserves_vip():
    first = employee("e1", "An", vip=True)
    second = employee("e2", "Bình")
    first.update({"service": "Body 90", "service_price": 100, "room": "1.1", "status": "CHO THANH TOÁN"})
    second.update({"service": "Body 70", "service_price": 200, "room": "1.2", "status": "CHO THANH TOÁN"})
    state = state_with(first, second)
    customer = {
        "id": "c1", "name": "Khách A", "phone": "0901", "combo_purchases": [{
            "id": "cp1", "combo_id": "combo", "combo_name": "Combo 13",
            "total": 3, "used": 0, "remaining": 3,
        }],
    }
    state["customers"].append(customer)

    invoice = live._checkout(state, {
        "employee_ids": ["e1", "e2"], "customer_id": "c1",
        "discount": 50, "tip": 30, "payment_method": "COMBO",
        "combo_purchase_id": "cp1", "combo_units": 999,
    }, "admin", NOW, False)

    assert invoice["total"] == 280  # 100 + 200 - 50 + 30 tip
    assert invoice["bill_no"] == "LIVE-20260905-0001"
    assert invoice["combo_units"] == 2
    assert invoice["payment_method"] == "COMBO"
    assert invoice["combo_units_source"] == "server_service_catalog"
    assert customer["combo_purchases"][0]["remaining"] == 1
    assert state["combo_usage"][-1]["invoice_id"] == invoice["id"]
    assert state["combo_usage"][-1]["units"] == 2
    assert sum(item["total"] for item in state["reports"]) == invoice["total"]
    assert sum(item["tip"] for item in state["reports"]) == invoice["tip"]
    assert sum(item["combo_units"] for item in state["reports"]) == invoice["combo_units"]
    assert first["service"] == "" and second["service"] == ""
    assert first["service_price"] is None and first["wait_minutes"] is None
    assert first["completion_delta_minutes"] is None
    assert first["vip"] is True

    third = employee("e3", "Chi")
    third.update({"service": "Body 70", "service_price": 200, "room": "2.1", "status": "CHO THANH TOÁN"})
    state["employees"].append(third)
    second_invoice = live._checkout(state, {"employee_id": "e3", "payment_method": "TIỀN MẶT"}, "admin", NOW, False)
    assert second_invoice["bill_no"] == "LIVE-20260905-0002"

    fourth = employee("e4", "Dung")
    fourth.update({"service": "Body 70", "service_price": 200, "room": "2.2", "status": "CHO THANH TOÁN"})
    state["employees"].append(fourth)
    with pytest.raises(HTTPException) as duplicate_bill:
        live._checkout(state, {"employee_id": "e4", "bill_no": invoice["bill_no"], "payment_method": "TIỀN MẶT"}, "admin", NOW, False)
    assert duplicate_bill.value.status_code == 409


def test_multi_select_action_rolls_back_all_items_when_one_is_invalid():
    first = employee("e1", "An")
    second = employee("e2", "Bình")
    first.update({"service": "Body 90", "room": "1.1", "status": "Đang chờ", "duration": 90})
    second.update({"service": "Body 70", "room": "1.2", "status": "", "duration": 70})
    state = state_with(first, second)
    original = deepcopy(state)

    with pytest.raises(HTTPException):
        live._apply_action(state, "start", {"employee_ids": ["e1", "e2"]}, "admin", NOW)

    assert state == original


def test_catalog_backup_and_restore_round_trip():
    state = state_with(employee("e1", "An"))
    live._apply_action(state, "backup", {"label": "Trước khi sửa"}, "admin", NOW)
    backup_id = state["backups"][0]["id"]
    live._apply_action(state, "service_upsert", {
        "name": "Dịch vụ mới", "duration": 45, "price": 123_000,
    }, "admin", NOW)
    state["invoices"].append({"id": "immutable-invoice", "total": 10})
    state["customers"].append({"id": "immutable-customer", "combo_purchases": [{"remaining": 2}]})
    state["combo_usage"].append({"id": "immutable-combo-usage", "units": 2})
    assert any(item["name"] == "Dịch vụ mới" for item in state["services"])

    live._apply_action(state, "restore", {"backup_id": backup_id}, "admin", NOW)

    assert not any(item["name"] == "Dịch vụ mới" for item in state["services"])
    assert state["backups"][0]["id"] == backup_id
    assert state["invoices"][0]["id"] == "immutable-invoice"
    assert state["customers"][0]["id"] == "immutable-customer"
    assert state["combo_usage"][0]["id"] == "immutable-combo-usage"
    assert state["audit"][-1]["action"] == "restore"


def test_break_end_records_ninety_minute_outcome():
    ktv = employee("e1", "An")
    state = state_with(ktv)
    start = datetime(2026, 9, 5, 13, 0, tzinfo=live.VN_TZ)
    end = datetime(2026, 9, 5, 14, 31, tzinfo=live.VN_TZ)
    live._apply_action(state, "start_break", {"employee_id": "e1"}, "admin", start)
    live._apply_action(state, "end_break", {"employee_id": "e1"}, "admin", end)
    assert ktv["last_break_minutes"] == 91
    assert ktv["last_break_outcome"] == "Quá 90 phút"


def test_view_only_response_does_not_expose_customer_pii_in_raw_employee_state():
    ktv = employee("e1", "An")
    ktv.update({"customer_id": "c1", "customer_name": "Khách A", "customer_phone": "0901"})
    response = live._state_response(state_with(ktv), 1, NOW, can_payment=False)
    raw_employee = response["state"]["employees"][0]
    assert "customer_name" not in raw_employee
    assert "customer_phone" not in raw_employee


def test_zero_ticket_combo_purchase_is_rejected():
    state = state_with()
    state["combos"][0]["tickets"] = 0
    with pytest.raises(HTTPException) as error:
        live._apply_action(state, "combo_purchase", {
            "customer_name": "Khách A", "combo_id": state["combos"][0]["id"], "tickets": 99,
        }, "admin", NOW)
    assert error.value.status_code == 400


def test_combo_purchase_uses_catalog_price_and_creates_financial_ledger():
    state = state_with()
    combo = state["combos"][0]
    result = live._apply_action(state, "combo_purchase", {
        "customer_name": "Khách A", "phone": "0901", "combo_id": combo["id"],
        "quantity": 2, "amount": 1,
    }, "admin", NOW)
    assert result["purchase"]["total"] == combo["tickets"] * 2
    assert result["purchase"]["price"] == combo["price"] * 2
    assert result["invoice"]["total"] == combo["price"] * 2
    assert result["invoice"]["combo_purchase_id"] == ""
    assert result["invoice"]["purchased_combo_id"] == result["purchase"]["id"]
    assert state["reports"][-1]["type"] == "combo_purchase"


@pytest.mark.parametrize(("action", "payload"), [
    ("service_upsert", {"name": "Bad duration", "duration": float("nan"), "price": 1}),
    ("service_upsert", {"name": "Negative duration", "duration": -1, "price": 1}),
    ("service_upsert", {"name": "Infinite price", "duration": 60, "price": float("inf")}),
    ("service_upsert", {"name": "Negative price", "duration": 60, "price": -1}),
    ("combo_upsert", {"name": "Bad tickets", "tickets": float("inf"), "price": 1}),
    ("combo_upsert", {"name": "Negative tickets", "tickets": -1, "price": 1}),
    ("combo_upsert", {"name": "Huge price", "tickets": 13, "price": live.MAX_MONEY + 1}),
])
def test_catalog_financial_values_reject_nonfinite_negative_or_out_of_bounds(action, payload):
    state = state_with()
    original = deepcopy(state)

    with pytest.raises(HTTPException) as error:
        live._apply_action(state, action, payload, "admin", NOW)

    assert error.value.status_code == 400
    assert state == original


@pytest.mark.parametrize("payload", [
    {"employee_id": "e1", "discount": -1},
    {"employee_id": "e1", "discount": float("nan")},
    {"employee_id": "e1", "tip": float("inf")},
    {"employee_id": "e1", "tip": live.MAX_MONEY + 1},
])
def test_checkout_rejects_invalid_discount_and_tip_atomically(payload):
    ktv = payable_employee("e1", "An", customer_id="")
    ktv.update({"customer_name": "", "customer_phone": ""})
    state = state_with(ktv)
    original = deepcopy(state)

    with pytest.raises(HTTPException) as error:
        live._checkout(state, payload, "admin", NOW, False)

    assert error.value.status_code == 400
    assert state == original


@pytest.mark.parametrize("quantity", [float("nan"), float("inf"), -1, 0, 1.5, live.MAX_PURCHASE_QUANTITY + 1])
def test_combo_purchase_rejects_invalid_quantity_without_mutation(quantity):
    state = state_with()
    original = deepcopy(state)

    with pytest.raises(HTTPException) as error:
        live._apply_action(state, "combo_purchase", {
            "customer_name": "Khách A", "combo_id": state["combos"][0]["id"],
            "quantity": quantity,
        }, "admin", NOW)

    assert error.value.status_code == 400
    assert state == original


def test_customer_id_cannot_take_another_customers_phone():
    state = state_with()
    state["customers"] = [
        {"id": "c1", "name": "Một", "phone": "0901", "combo_purchases": []},
        {"id": "c2", "name": "Hai", "phone": "0902", "combo_purchases": []},
    ]
    with pytest.raises(HTTPException) as error:
        live._customer(state, {"customer_id": "c1", "phone": "0902"})
    assert error.value.status_code == 409


@pytest.mark.parametrize(("payload", "status_code"), [
    ({"pending_id": "p1", "employee_id": "e1"}, 400),
    ({"employee_ids": ["e1", "e1"]}, 400),
    ({"pending_id": "missing"}, 404),
])
def test_checkout_rejects_ambiguous_duplicate_or_missing_source_atomically(payload, status_code):
    state = state_with(payable_employee("e1", "An"))
    state["pending"] = [{
        "id": "p1", "customer_id": "c1", "customer_name": "Khách c1",
        "customer_phone": "0901", "entries": [{
            "employee_id": "e9", "employee_name": "Chín", "service": "Body 70",
            "room": "2.1", "price": 100,
        }],
    }]
    original = deepcopy(state)

    with pytest.raises(HTTPException) as error:
        live._checkout(state, payload, "admin", NOW, False)

    assert error.value.status_code == status_code
    assert state == original


def test_checkout_rejects_mixed_customer_rows_and_customer_override_atomically():
    first = payable_employee("e1", "An", customer_id="c1", room="1.1")
    second = payable_employee("e2", "Bình", customer_id="c2", room="1.2")
    state = state_with(first, second)
    state["customers"] = [
        {"id": "c1", "name": "Khách c1", "phone": "0901", "combo_purchases": []},
        {"id": "c2", "name": "Khách c2", "phone": "0902", "combo_purchases": []},
    ]
    original = deepcopy(state)

    with pytest.raises(HTTPException) as mixed_error:
        live._checkout(state, {"employee_ids": ["e1", "e2"], "payment_method": "TIỀN MẶT"}, "admin", NOW, False)
    assert mixed_error.value.status_code == 409
    assert state == original

    with pytest.raises(HTTPException) as override_error:
        live._checkout(state, {"employee_id": "e1", "customer_id": "c2", "payment_method": "TIỀN MẶT"}, "admin", NOW, False)
    assert override_error.value.status_code == 409
    assert state == original


def test_customer_identity_is_not_mutated_by_transaction_payload_and_unknown_id_is_rejected():
    state = state_with()
    state["customers"] = [{
        "id": "c1", "name": "Khách Một", "phone": "0901", "combo_purchases": [],
    }]
    original = deepcopy(state)

    with pytest.raises(HTTPException) as phone_error:
        live._customer(state, {"customer_id": "c1", "customer_name": "Khách Một", "phone": "0999"})
    assert phone_error.value.status_code == 409
    assert state == original

    with pytest.raises(HTTPException) as name_error:
        live._customer(state, {"customer_id": "c1", "customer_name": "Tên Khác", "phone": "0901"})
    assert name_error.value.status_code == 409
    assert state == original

    with pytest.raises(HTTPException) as missing_error:
        live._customer(state, {"customer_id": "missing", "customer_name": "Khách Mới"})
    assert missing_error.value.status_code == 404
    assert state == original


def test_common_customer_identity_uses_the_nonblank_source_row():
    identity = live._common_customer_identity([
        {"customer_id": "c1", "customer_name": "", "customer_phone": ""},
        {"customer_id": "c1", "customer_name": "Khách Một", "customer_phone": "0901"},
    ])
    assert identity == {
        "customer_id": "c1", "customer_name": "Khách Một", "customer_phone": "0901",
    }


@pytest.mark.parametrize("rows", [
    [
        {"customer_id": "c1", "customer_name": "Khách Một", "customer_phone": "0901"},
        {"customer_id": "", "customer_name": "", "customer_phone": ""},
    ],
    [
        {"customer_id": "c1", "customer_name": "", "customer_phone": ""},
        {"customer_id": "", "customer_name": "Khách Một", "customer_phone": "0901"},
    ],
    [
        {"customer_id": "c1", "customer_name": "Khách Một", "customer_phone": "0901"},
        {"customer_id": "c1", "customer_name": "Khách Khác", "customer_phone": "0901"},
    ],
])
def test_common_customer_identity_rejects_anonymous_or_inconsistent_mixes(rows):
    with pytest.raises(HTTPException) as error:
        live._common_customer_identity(rows)
    assert error.value.status_code == 409


def test_audit_recursively_removes_exact_customer_pii_keys():
    state = state_with()
    live._audit(state, "booking", {
        "employee_id": "e1", "customer_id": "c1", "phone": "0901",
        "bookings": [{
            "customer_name": "Khách Một",
            "meta": {"customer_phone": "0901", "safe": "kept"},
        }],
    }, "admin", NOW)

    detail = state["audit"][-1]["detail"]
    encoded = str(detail)
    assert "customer_id" not in encoded
    assert "customer_name" not in encoded
    assert "customer_phone" not in encoded
    assert "'phone'" not in encoded
    assert detail["bookings"][0]["meta"]["safe"] == "kept"


@pytest.mark.parametrize("payload", [
    {"employee_id": "e1", "payment_method": "COMBO"},
    {"employee_id": "e1", "payment_method": "Tiền mặt", "combo_purchase_id": "cp1"},
    {"employee_id": "e1", "payment_method": "Thẻ", "combo_purchase_id": "cp1"},
    {"employee_id": "e1", "combo_purchase_id": "cp1"},
])
def test_checkout_requires_combo_payment_method_iff_combo_is_debited(payload):
    ktv = payable_employee("e1", "An")
    state = state_with(ktv)
    state["customers"] = [{
        "id": "c1", "name": "Khách c1", "phone": "0901", "combo_purchases": [{
            "id": "cp1", "combo_name": "Combo 13", "total": 13,
            "used": 0, "remaining": 13,
        }],
    }]
    original = deepcopy(state)

    with pytest.raises(HTTPException) as error:
        live._checkout(state, payload, "admin", NOW, False)

    assert error.value.status_code == 400
    assert state == original


def test_insufficient_combo_balance_rolls_back_invoice_usage_and_customer_balance():
    first = payable_employee(
        "e1", "An", room="1.1", service="Body 90 & Mua thêm 30",
    )
    second = payable_employee("e2", "Bình", room="1.2", service="Body 70")
    state = state_with(first, second)
    state["customers"] = [{
        "id": "c1", "name": "Khách c1", "phone": "0901", "combo_purchases": [{
            "id": "cp1", "combo_name": "Combo 13", "total": 1, "used": 0, "remaining": 1,
        }],
    }]
    original = deepcopy(state)

    with pytest.raises(HTTPException) as error:
        live._checkout(state, {
            "employee_ids": ["e1", "e2"], "customer_id": "c1",
            "payment_method": "COMBO", "combo_purchase_id": "cp1", "combo_units": 1,
        }, "admin", NOW, False)

    assert error.value.status_code == 409
    assert state == original


def test_idempotency_hash_is_payload_bound_and_replay_rejects_mismatches():
    first_hash = live._canonical_payload_hash(" CHECKOUT ", {
        "employee_id": "e1", "discount": 10,
        "meta": {"phone": "0901", "name": "Khách"},
        "idempotency_key": "nested-key", "_source_records": [{"ignored": 1}],
    })
    same_hash = live._canonical_payload_hash("checkout", {
        "meta": {"name": "Khách", "phone": "0901"},
        "discount": 10, "employee_id": "e1",
    })
    changed_hash = live._canonical_payload_hash("checkout", {
        "employee_id": "e2", "discount": 10,
        "meta": {"name": "Khách", "phone": "0901"},
    })
    assert first_hash == same_hash
    assert changed_hash != first_hash

    state = state_with()
    result = {"invoice": {"id": "invoice-1"}}
    live._remember_idempotency(
        state, "request-key-1", action="checkout", actor="admin",
        payload_hash=first_hash, result=result, now=NOW,
    )
    replay = live._idempotency_replay(
        state, "request-key-1", action="checkout", actor="admin", payload_hash=first_hash,
    )
    assert replay["result"] == result
    assert replay["status"] == "completed"

    with pytest.raises(HTTPException) as mismatch:
        live._idempotency_replay(
            state, "request-key-1", action="checkout", actor="admin", payload_hash=changed_hash,
        )
    assert mismatch.value.status_code == 409

    state["idempotency"]["legacy-key"] = {"action": "checkout", "actor": "admin"}
    with pytest.raises(HTTPException) as legacy:
        live._idempotency_replay(
            state, "legacy-key", action="checkout", actor="admin", payload_hash=first_hash,
        )
    assert legacy.value.status_code == 409


def test_noncompleted_idempotency_is_never_replayed_as_success():
    state = state_with()
    payload_hash = live._canonical_payload_hash("sync_leaves", {"sync_action": "sync_all"})
    state["idempotency"]["sync-in-progress"] = {
        "action": "sync_leaves", "actor": "admin", "payload_hash": payload_hash,
        "status": "recovery_required", "result": {"recovery_required": True},
    }

    with pytest.raises(HTTPException) as error:
        live._idempotency_replay(
            state, "sync-in-progress", action="sync_leaves", actor="admin",
            payload_hash=payload_hash,
        )

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "LIVE_TOUR_SYNC_RECOVERY_REQUIRED"


def test_idempotency_pruning_preserves_financial_and_sync_entries():
    state = state_with()
    state["idempotency"] = {
        "protected-checkout": {
            "action": "checkout", "actor": "admin", "payload_hash": "checkout-hash",
            "status": "completed", "at": "2020-01-01T00:00:00+00:00", "result": {},
        },
        "protected-sync": {
            "action": "sync_leaves", "actor": "admin", "payload_hash": "sync-hash",
            "status": "in_progress", "at": "2020-01-01T00:00:01+00:00", "result": {},
        },
    }
    for index in range(live.MAX_IDEMPOTENCY):
        state["idempotency"][f"ordinary-{index:03d}"] = {
            "action": "booking", "actor": "admin", "payload_hash": str(index),
            "status": "completed", "at": f"2021-01-01T00:{index // 60:02d}:{index % 60:02d}+00:00",
            "result": {},
        }

    live._remember_idempotency(
        state, "ordinary-new", action="booking", actor="admin",
        payload_hash="new-hash", result={}, now=NOW,
    )

    assert "protected-checkout" in state["idempotency"]
    assert "protected-sync" in state["idempotency"]
    assert state["idempotency"]["ordinary-new"]["status"] == "completed"
    assert len(state["idempotency"]) == live.MAX_IDEMPOTENCY


def test_source_employee_maps_vip_break_booking_and_steam_fields_without_overloading_wait_time():
    source = {
        "STT": 7, "Tên nhân viên": "  Ánh * ", "Đi làm": "ĐANG LÀM VIỆC",
        "Vào ca": "10h00", "Break": "Break", "Giờ ra": 13 / 24,
        "Giờ Booking": 14 / 24, "TG Xông Hơi": 12 / 1440,
        "Thời gian": 75, "Dịch vụ": "Xông hơi", "Phòng": "19.1",
    }

    mapped = live._source_employee(source, 0, NOW)

    assert mapped["name"] == "Ánh"
    assert mapped["vip"] is True
    assert mapped["work_status"] == "Đi làm"
    assert mapped["shift"] == "Ca 1"
    assert mapped["booked_at"] == "2026-09-05T14:00:00+07:00"
    assert mapped["break_started_at"] == "2026-09-05T13:00:00+07:00"
    assert mapped["break_remaining_minutes"] == 75
    assert mapped["steam_elapsed_minutes"] == 12
    assert mapped["wait_minutes"] is None


def test_bootstrap_service_prices_are_reconciled_from_catalog_for_combined_rows():
    existing = employee("e1", "An")
    state = state_with(existing)
    next(item for item in state["services"] if item["name"] == "Body 90")["price"] = 450_000
    next(item for item in state["services"] if item["name"] == "Body 70")["price"] = 350_000
    records = [
        {
            "STT": 1, "Tên nhân viên": "An", "Dịch vụ": "Body 90 & Body 70",
            "Phòng": "1.1", "Trạng thái": "CHO THANH TOÁN", "Đi làm": "Di lam",
        },
        {
            "STT": 2, "Tên nhân viên": "Bình", "Dịch vụ": "Body 90",
            "Phòng": "1.2", "Trạng thái": "CHO THANH TOÁN", "Đi làm": "Di lam",
        },
    ]

    # Full assignment import belongs only to initial bootstrap, not an ongoing
    # merge of an old Tour workbook over an already operating Live board.
    state["employees"] = [live._source_employee(record, index, NOW) for index, record in enumerate(records)]
    existing, imported = state["employees"]
    assert existing["service_price"] is None
    assert existing["service_price_source"] == "tour_import"
    assert imported["service_price"] is None

    invoice = live._checkout(
        state, {"employee_ids": [existing["id"], imported["id"]], "payment_method": "TIỀN MẶT"},
        "admin", NOW, False,
    )

    assert invoice["subtotal"] == 1_250_000
    assert [entry["price"] for entry in invoice["entries"]] == [800_000, 450_000]
    zero_catalog = next(item for item in state["services"] if item["name"] == "Xông hơi")
    assert zero_catalog["price"] == 0
    assert live._resolved_service_price(
        state, {"service": "Xông hơi", "service_price": None, "service_price_source": "tour_import"},
    ) == 0


def test_operator_cannot_bypass_service_catalog_with_custom_price_payload():
    state = state_with(employee("e1", "An"))

    with pytest.raises(HTTPException) as error:
        live._booking(state, {
            "employee_id": "e1", "room": "1.1", "service": "Tự nhập",
            "price": 1, "allow_custom_service": True,
        }, NOW)

    assert error.value.status_code == 400
    assert state["employees"][0]["service"] == ""


@pytest.mark.parametrize("value", ["=1+1", " +SUM(A1:A2)", "\t-2+3", "@cmd"])
def test_excel_literal_escapes_every_formula_prefix_after_whitespace(value):
    escaped = live._excel_literal(value)
    assert escaped.startswith("'")
    assert escaped[1:] == value


def test_excel_export_writes_formula_like_customer_values_as_text():
    state = state_with()
    state["invoices"] = [{
        "business_date": "2026-09-05", "created_at": NOW.isoformat(),
        "bill_no": "LIVE-1", "customer_name": " =1+1", "customer_phone": "+2+2",
        "total": 0, "discount": 0, "tip": 0, "payment_method": "Tiền mặt", "actor": "admin",
    }]

    content, _ = live._excel_bytes(state, "revenue", NOW)
    sheet = load_workbook(BytesIO(content), data_only=False).active

    assert sheet["C2"].data_type == "s"
    assert sheet["C2"].value == "' =1+1"
    assert sheet["D2"].data_type == "s"
    assert sheet["D2"].value == "'+2+2"


@pytest.mark.parametrize(("utc_value", "expected"), [
    (datetime(2026, 9, 5, 15, 59, 59, tzinfo=timezone.utc), False),  # 22:59:59 VN
    (datetime(2026, 9, 5, 16, 0, 0, tzinfo=timezone.utc), True),     # 23:00:00 VN
    (datetime(2026, 9, 5, 20, 0, 0, tzinfo=timezone.utc), True),     # 03:00:00 VN
    (datetime(2026, 9, 5, 20, 0, 1, tzinfo=timezone.utc), False),    # 03:00:01 VN
])
def test_auto_yc_ca1_uses_inclusive_vietnam_time_window(utc_value, expected):
    request, automatic = live._auto_yc_ca1(
        utc_value, employee("e1", "An", shift="Ca 1"), "", True,
    )
    assert automatic is expected
    assert request == ("YC" if expected else "")

    disabled_request, disabled = live._auto_yc_ca1(
        utc_value, employee("e1", "An", shift="Ca 1"), "", False,
    )
    ca2_request, ca2 = live._auto_yc_ca1(
        utc_value, employee("e2", "Bình", shift="Ca 2"), "", True,
    )
    assert (disabled_request, disabled) == ("", False)
    assert (ca2_request, ca2) == ("", False)


def test_multi_booking_propagates_outer_auto_yc_flag_only_to_ca1():
    first = employee("e1", "An", shift="Ca 1")
    second = employee("e2", "Bình", shift="Ca 2")
    state = state_with(first, second)
    at_2300_vn = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)

    result = live._apply_action(state, "multi_booking", {
        "auto_yc_ca1": True,
        "bookings": [
            {"employee_id": "e1", "room": "1.1", "service": "Body 90", "request": ""},
            {"employee_id": "e2", "room": "1.2", "service": "Body 90", "request": ""},
        ],
    }, "admin", at_2300_vn)

    assert result["employees"][0]["request"] == "YC"
    assert result["employees"][0]["request_source"] == "auto_yc_ca1"
    assert result["employees"][1]["request"] == ""
    assert result["employees"][1]["request_source"] == "manual"


def test_canonical_work_and_shift_transitions_reject_invalid_sequences():
    assert live._canonical_work_status("đang làm việc") == "Đi làm"
    assert live._canonical_work_status("nghỉ có phép") == "Nghỉ phép"
    assert live._canonical_shift("14h") == "Ca 2"
    with pytest.raises(HTTPException) as invalid_work:
        live._canonical_work_status("không rõ")
    with pytest.raises(HTTPException) as invalid_shift:
        live._canonical_shift("Ca đêm")
    assert invalid_work.value.status_code == 400
    assert invalid_shift.value.status_code == 400

    off_duty = employee("e1", "An")
    off_duty["work_status"] = "Nghỉ phép"
    off_state = state_with(off_duty)
    with pytest.raises(HTTPException) as off_error:
        live._apply_action(off_state, "set_shift", {"employee_id": "e1", "shift": "Ca 2"}, "admin", NOW)
    assert off_error.value.status_code == 409

    on_break = employee("e2", "Bình")
    on_break["break_started_at"] = NOW.isoformat()
    break_state = state_with(on_break)
    with pytest.raises(HTTPException) as break_error:
        live._apply_action(break_state, "set_shift", {"employee_id": "e2", "shift": "Ca 2"}, "admin", NOW)
    assert break_error.value.status_code == 409

    active = employee("e3", "Chi")
    active.update({"service": "Body 90", "room": "1.1", "status": "Đang chờ"})
    active_state = state_with(active)
    with pytest.raises(HTTPException) as active_error:
        live._apply_action(active_state, "set_shift", {"employee_id": "e3", "shift": "Ca 2"}, "admin", NOW)
    assert active_error.value.status_code == 409

    idle = employee("e4", "Dung")
    idle_state = state_with(idle)
    live._apply_action(idle_state, "set_shift", {"employee_id": "e4", "shift": "14h"}, "admin", NOW)
    live._apply_action(idle_state, "set_work_status", {"employee_id": "e4", "status": "nghỉ có phép"}, "admin", NOW)
    assert idle["shift"] == "Ca 2"
    assert idle["work_status"] == "Nghỉ phép"


def test_normalize_state_canonicalizes_unknown_source_values_safely():
    raw = live._empty_state(NOW)
    raw["employees"] = [
        {"id": "e1", "name": "An", "work_status": "ĐANG LÀM VIỆC", "shift": "10h"},
        {"id": "e2", "name": "Bình", "work_status": "không rõ", "shift": "Ca đêm"},
    ]

    normalized = live._normalize_state(raw, NOW)

    assert normalized["employees"][0]["work_status"] == "Đi làm"
    assert normalized["employees"][0]["shift"] == "Ca 1"
    assert normalized["employees"][1]["work_status"] == "Nghỉ"
    assert normalized["employees"][1]["shift"] == ""


def test_operator_capabilities_allow_hidden_employee_recovery_but_view_only_does_not():
    visible = employee("e1", "An")
    hidden = employee("e2", "Bình")
    hidden["hidden"] = True
    state = state_with(visible, hidden)

    operator = live._state_response(
        state, 3, NOW, include_hidden=True, can_operate=True,
    )
    assert {item["employee_id"] for item in operator["records"]} == {"e1", "e2"}
    assert operator["capabilities"]["operate"] is True
    assert "sync" not in operator["capabilities"]
    assert operator["capabilities"]["hide_recovery"] is True

    view_only = live._state_response(state, 3, NOW, include_hidden=True)
    assert [item["employee_id"] for item in view_only["records"]] == ["e1"]
    assert view_only["capabilities"]["hide_recovery"] is False

    live._apply_action(state, "show_employee", {"employee_id": "e2"}, "operator", NOW)
    assert hidden["hidden"] is False


def test_assignment_cleanup_clears_only_tour_fields():
    ktv = employee("e1", "An", vip=True)
    ktv.update({
        "appointment": "2026-09-05T16:00:00+07:00", "service": "Body 90",
        "request": "YC", "request_source": "manual", "room": "1.1",
        "status": "CHO THANH TOÁN", "booked_at": NOW.isoformat(),
        "started_at": NOW.isoformat(), "completed_at": NOW.isoformat(),
        "payment_status": "CHO THANH TOÁN", "customer_id": "c1",
        "customer_name": "Khách", "customer_phone": "0901", "note": "ghi chú",
        "booking_id": "booking-1", "duration": 90, "service_price": 100,
        "service_price_source": "catalog",
        "wait_minutes": 12, "completion_delta_minutes": -3, "steam_elapsed_minutes": 15,
        "break_history": [{"minutes": 90}], "clock_in": "10:00", "clock_out": "23:00",
    })
    preserved = {
        key: deepcopy(ktv[key]) for key in (
            "id", "name", "vip", "tour_count", "request_count", "work_status", "shift",
            "break_history", "clock_in", "clock_out", "sort_index",
        )
    }

    live._clear_assignment(ktv)

    for key in (
        "appointment", "service", "request", "request_source", "room", "status",
        "booked_at", "started_at", "completed_at", "payment_status", "customer_id",
        "customer_name", "customer_phone", "note", "booking_id",
        "service_price_source",
    ):
        assert ktv[key] == ""
    for key in (
        "duration", "service_price", "wait_minutes", "completion_delta_minutes",
        "steam_elapsed_minutes",
    ):
        assert ktv[key] is None
    assert {key: ktv[key] for key in preserved} == preserved


def test_board_export_hides_rows_by_default_and_admin_can_include_them():
    visible = employee("e1", "An")
    hidden = employee("e2", "Bình")
    hidden["hidden"] = True
    state = state_with(visible, hidden)

    _, headers, default_rows = live._export_rows(state, "board", NOW)
    _, _, admin_rows = live._export_rows(state, "board", NOW, include_hidden=True)
    name_index = headers.index("Tên nhân viên")

    assert [row[name_index] for row in default_rows] == ["An"]
    assert [row[name_index] for row in admin_rows] == ["An", "Bình"]


def test_export_bounds_filter_business_date_and_cross_midnight_vietnam_time():
    state = state_with()
    state["invoices"] = [
        {
            "id": "old", "business_date": "2026-09-04", "bill_no": "OLD",
            "created_at": "2026-09-05T02:30:00+07:00",
        },
        {
            "id": "late", "business_date": "2026-09-05", "bill_no": "LATE",
            "created_at": "2026-09-05T23:30:00+07:00",
        },
        {
            "id": "early", "business_date": "2026-09-05", "bill_no": "EARLY",
            "created_at": "2026-09-06T02:30:00+07:00",
        },
        {
            "id": "noon", "business_date": "2026-09-05", "bill_no": "NOON",
            "created_at": "2026-09-05T12:00:00+07:00",
        },
    ]
    bounds = live._parse_export_bounds(
        date_from="2026-09-05", date_to="2026-09-05",
        time_from="23:00", time_to="03:00",
    )

    _, headers, rows = live._export_rows(state, "revenue", NOW, bounds=bounds)
    bill_index = headers.index("Số bill")

    assert [row[bill_index] for row in rows] == ["LATE", "EARLY"]
    with pytest.raises(HTTPException):
        live._parse_export_bounds(date_from="2026-09-06", date_to="2026-09-05")
    with pytest.raises(HTTPException):
        live._parse_export_bounds(time_from="3:00")


@pytest.mark.parametrize(("action", "payload"), [
    ("booking", {
        "employee_id": "e1", "room": "1.1", "service": "Body 90",
        "customer_id": "c1",
    }),
    ("multi_booking", {
        "bookings": [{
            "employee_id": "e1", "room": "1.1", "service": "Body 90",
            "meta": {"customer_phone": "0901"},
        }],
    }),
])
def test_booking_with_customer_pii_requires_customers_permission_before_state_mutation(
    monkeypatch, action, payload,
):
    app = FastAPI()
    checked = []
    state_reads = []

    def require(_conn, _identity, feature):
        checked.append(feature)
        if feature == "live_tour_customers_view":
            raise HTTPException(403, "Không có quyền thanh toán")

    monkeypatch.setattr(
        live, "_read_state", lambda *_args, **_kwargs: state_reads.append(True),
    )
    live.install_live_tour_routes(
        app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=require, feature_allowed=lambda *_args: False,
        identity_type=RouteIdentity,
    )
    endpoint = next(
        route.endpoint for route in app.routes
        if getattr(route, "path", "") == "/v2/live-tour/action"
    )

    with pytest.raises(HTTPException) as error:
        endpoint(
            live.LiveTourAction(
                action=action, idempotency_key=f"{action}-request-1", payload=payload,
            ),
            RouteIdentity(),
        )

    assert error.value.status_code == 403
    assert checked == ["live_tour_booking", "live_tour_view", "live_tour_customers_view"]
    assert state_reads == []


def test_action_response_redacts_pii_without_mutating_internal_idempotency(monkeypatch):
    app = FastAPI()
    ktv = employee("e1", "An")
    ktv.update({
        "customer_id": "c1", "customer_name": "Khách A", "customer_phone": "0901",
    })
    state = state_with(ktv)
    written = {}
    monkeypatch.setattr(live, "_read_state", lambda *_args, **_kwargs: (state, 4))

    def capture_write(_conn, value, revision, _actor):
        written["state"] = deepcopy(value)
        return revision + 1

    monkeypatch.setattr(live, "_write_state", capture_write)
    live.install_live_tour_routes(
        app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=lambda *_args: None,
        feature_allowed=lambda _conn, _identity, feature: feature in {"live_tour_admin", "live_tour_operate"},
        identity_type=RouteIdentity,
    )
    endpoint = next(
        route.endpoint for route in app.routes
        if getattr(route, "path", "") == "/v2/live-tour/action"
    )

    response = endpoint(
        live.LiveTourAction(
                action="set_vip", idempotency_key="set-vip-request-1",
                expected_revision=4,
            payload={"employee_id": "e1", "vip": True},
        ),
        RouteIdentity(),
    )

    public_employee = response["result"]["employee"]
    assert "customer_id" not in public_employee
    assert "customer_name" not in public_employee
    assert "customer_phone" not in public_employee
    internal = written["state"]["idempotency"]["set-vip-request-1"]["result"]["employee"]
    assert internal["customer_id"] == "c1"
    assert internal["customer_name"] == "Khách A"
    assert internal["customer_phone"] == "0901"


@pytest.mark.parametrize("kind", ["revenue", "tip", "customers", "pending", "history"])
def test_sensitive_exports_require_more_than_export_permission(kind):
    app = FastAPI()

    def require(_conn, _identity, feature):
        if feature != "live_tour_export":
            raise HTTPException(403, "Không có quyền")

    live.install_live_tour_routes(
        app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=require,
        feature_allowed=lambda _conn, _identity, feature: feature == "live_tour_export",
        identity_type=RouteIdentity,
    )
    endpoint = next(
        route.endpoint for route in app.routes
        if getattr(route, "path", "") == "/v2/live-tour/export.xlsx"
    )

    with pytest.raises(HTTPException) as error:
        endpoint(
            kind=kind, include_hidden=False, date_from="", date_to="",
            time_from="", time_to="", ident=RouteIdentity(),
        )

    assert error.value.status_code == 403


def test_operator_can_include_hidden_rows_in_board_and_png_exports(monkeypatch):
    app = FastAPI()
    state = state_with(employee("e1", "An"))
    captured = []
    monkeypatch.setattr(live, "_read_state", lambda *_args, **_kwargs: (state, 1))
    monkeypatch.setattr(
        live, "_excel_bytes",
        lambda *_args, include_hidden=False, **_kwargs: (
            captured.append(("xlsx", include_hidden)) or b"xlsx", "board.xlsx",
        ),
    )
    monkeypatch.setattr(
        live, "_png_bytes",
        lambda *_args, include_hidden=False, **_kwargs: captured.append(("png", include_hidden)) or b"png",
    )
    live.install_live_tour_routes(
        app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=lambda *_args: None,
        feature_allowed=lambda _conn, _identity, feature: feature in {"live_tour_export", "live_tour_operate"},
        identity_type=RouteIdentity,
    )
    excel_endpoint = next(
        route.endpoint for route in app.routes
        if getattr(route, "path", "") == "/v2/live-tour/export.xlsx"
    )
    png_endpoint = next(
        route.endpoint for route in app.routes
        if getattr(route, "path", "") == "/v2/live-tour/export.png"
    )

    excel_endpoint(
        kind="board", include_hidden=True, date_from="", date_to="",
        time_from="", time_to="", ident=RouteIdentity(),
    )
    png_endpoint(kind="board", include_hidden=True, ident=RouteIdentity())

    assert captured == [("xlsx", True), ("png", True)]


def test_all_representative_mutation_groups_require_idempotency_keys_at_api_boundary():
    assert {
        "booking", "start", "add_minutes", "checkout", "quick_checkout",
        "set_work_status", "hide_employee", "combo_purchase", "combo_import",
        "backup", "restore", "clear_expired",
    } <= live.IDEMPOTENCY_REQUIRED_ACTIONS
    body = live.LiveTourAction(action="checkout", idempotency_key="request-123", payload={})
    assert body.idempotency_key == "request-123"


def test_optimistic_write_rejects_stale_revision():
    class Result:
        rowcount = 0

    class Connection:
        def execute(self, *_args, **_kwargs):
            return Result()

    with pytest.raises(HTTPException) as error:
        live._write_state(Connection(), live._empty_state(NOW), 8, "admin")
    assert error.value.status_code == 409


def test_live_tour_permissions_and_installer_are_wired_without_replacing_legacy_tour():
    permissions = (ROOT / "vera_web_v2_permissions.py").read_text(encoding="utf-8")
    installer = (ROOT / "vera_web_v2_api_v38.py").read_text(encoding="utf-8")
    source = (ROOT / "vera_web_v2_live_tour.py").read_text(encoding="utf-8")

    for feature in ("live_tour_view", "live_tour_operate", "live_tour_payment", "live_tour_admin", "live_tour_export"):
        assert f'"{feature}"' in permissions
    assert "install_live_tour_routes" in installer
    assert '@app.get("/v2/live-tour")' in source
    assert '@app.post("/v2/live-tour/action")' in source
    assert '@app.get("/v2/live-tour/export.xlsx")' in source
    assert '@app.get("/v2/live-tour/export.png")' in source
    assert '@app.get("/v2/tour")' not in source


@pytest.mark.parametrize("ticket_price", [None, 0, -1, float("nan"), 1_000_000_001])
def test_zero_catalog_cash_checkout_requires_valid_manual_ticket_price(ticket_price):
    ktv = payable_employee("e1", "An")
    ktv.update({
        "service_price": 0, "service_price_source": "catalog",
        "customer_id": "", "customer_name": "", "customer_phone": "",
    })
    state = state_with(ktv)
    payload = {"employee_id": "e1", "payment_method": "TIỀN MẶT"}
    if ticket_price is not None:
        payload["ticket_price"] = ticket_price
    original = deepcopy(state)

    with pytest.raises(HTTPException) as error:
        live._checkout(state, payload, "admin", NOW, False)

    assert error.value.status_code == 400
    assert state == original


def test_zero_catalog_cash_checkout_accepts_bounded_ticket_price_and_catalog_price_cannot_be_spoofed():
    zero = payable_employee("e1", "An")
    zero.update({
        "service_price": 0, "service_price_source": "catalog",
        "customer_id": "", "customer_name": "", "customer_phone": "",
    })
    state = state_with(zero)
    invoice = live._checkout(
        state, {"employee_id": "e1", "payment_method": "TIỀN MẶT", "ticket_price": 450_000},
        "admin", NOW, False,
    )
    assert invoice["subtotal"] == 450_000
    assert invoice["pricing_source"] == "manual"

    priced = payable_employee("e2", "Bình")
    priced.update({
        "service_price": 300_000, "service_price_source": "catalog",
        "customer_id": "", "customer_name": "", "customer_phone": "",
    })
    state = state_with(priced)
    original = deepcopy(state)
    with pytest.raises(HTTPException):
        live._checkout(
            state, {"employee_id": "e2", "payment_method": "TIỀN MẶT", "ticket_price": 1},
            "admin", NOW, False,
        )
    assert state == original


def test_combo_checkout_with_zero_catalog_price_needs_no_manual_ticket_price():
    ktv = payable_employee("e1", "An")
    ktv.update({"service_price": 0, "service_price_source": "catalog"})
    state = state_with(ktv)
    state["customers"] = [{
        "id": "c1", "name": "Khách c1", "phone": "0901", "combo_purchases": [{
            "id": "cp1", "combo_name": "Combo 13", "total": 13, "used": 0, "remaining": 13,
        }],
    }]
    invoice = live._checkout(
        state, {"employee_id": "e1", "payment_method": "COMBO", "combo_purchase_id": "cp1"},
        "admin", NOW, False,
    )
    assert invoice["subtotal"] == 0
    assert invoice["pricing_source"] == "combo_debit"


def test_source_payment_header_promotes_blank_status_to_payable():
    source = live._source_employee({
        "STT": 1, "Tên nhân viên": "An", "Trạng thái": "", "Chờ thanh toán": "Chờ thanh toán",
        "Đi làm": "Di lam", "Vào ca": "Ca 1",
    }, 0, NOW)
    assert source["status"] == "CHO THANH TOÁN"
    assert source["payment_status"] == "CHO THANH TOÁN"


def test_source_column_x_is_wait_time_except_for_steam_service():
    massage = live._source_employee({
        "STT": 1, "Tên nhân viên": "An", "Dịch vụ": "Body 90", "TG Xông Hơi": 12,
    }, 0, NOW)
    steam = live._source_employee({
        "STT": 2, "Tên nhân viên": "Bình", "Dịch vụ": "Xông hơi", "TG Xông Hơi": 18,
    }, 1, NOW)

    assert massage["wait_minutes"] == 12
    assert massage["steam_elapsed_minutes"] is None
    assert steam["wait_minutes"] is None
    assert steam["steam_elapsed_minutes"] == 18


def test_mixed_zero_and_priced_services_cannot_silently_checkout_free():
    priced = payable_employee("e1", "An", customer_id="", service="Body 90")
    zero = payable_employee("e2", "Bình", customer_id="", room="1.2", service="Body 70")
    for item, price in ((priced, 300_000), (zero, 0)):
        item.update({
            "service_price": price, "service_price_source": "catalog",
            "customer_id": "", "customer_name": "", "customer_phone": "",
        })
    state = state_with(priced, zero)
    original = deepcopy(state)

    with pytest.raises(HTTPException) as error:
        live._checkout(
            state, {"employee_ids": ["e1", "e2"], "payment_method": "TIỀN MẶT"},
            "admin", NOW, False,
        )

    assert error.value.status_code == 400
    assert state == original


def test_combo_catalog_rejects_zero_tickets():
    state = state_with()
    original = deepcopy(state)
    with pytest.raises(HTTPException) as error:
        live._apply_action(
            state, "combo_upsert", {"name": "Combo lỗi", "tickets": 0, "price": 1},
            "admin", NOW,
        )
    assert error.value.status_code == 400
    assert state == original

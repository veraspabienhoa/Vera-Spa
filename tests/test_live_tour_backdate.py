from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import vera_web_v2_live_tour as live


def _employee(identifier: str = "e1") -> dict:
    return {
        "id": identifier,
        "stt": "1",
        "name": "An",
        "service": "Body 90",
        "service_price": 450_000,
        "service_price_source": "catalog",
        "room": "1.1",
        "status": "CHO THANH TOÁN",
        "payment_status": "CHO THANH TOÁN",
        "duration": 90,
        "work_status": "Đi làm",
        "shift": "Ca 1",
        "tour_count": 0,
        "request_count": 0,
        "hidden": False,
        "vip": False,
        "sort_index": 0,
    }


def _payable_state(now: datetime) -> dict:
    state = live._empty_state(now)
    state["employees"] = [_employee()]
    service = next(item for item in state["services"] if item["name"] == "Body 90")
    service["price"] = 450_000
    return state


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 4, 22, 0, tzinfo=timezone.utc), "2026-09-03T23:59:00+07:00"),  # 05:00 VN
        (datetime(2026, 9, 5, 11, 9, 59, tzinfo=live.VN_TZ), "2026-09-03T23:59:00+07:00"),
        (datetime(2026, 9, 5, 11, 10, tzinfo=live.VN_TZ), "2026-09-04T23:59:00+07:00"),
        (datetime(2026, 9, 5, 15, 0, tzinfo=live.VN_TZ), "2026-09-04T23:59:00+07:00"),
    ],
)
def test_backdate_uses_previous_vietnam_business_day_at_2359_across_cutoff(now, expected):
    timing = live._financial_timing(
        {"backdate_one_day": True, "correction_reason": "Sửa ngày"}, now,
    )

    assert timing["effective_at"] == expected
    assert timing["business_date"] == expected[:10]
    assert timing["recorded_at"] == live._iso(now)


@pytest.mark.parametrize(
    "payload",
    [
        {"backdate_one_day": True, "correction_reason": "  a "},
        {"backdate_one_day": "true", "correction_reason": "Hợp lệ"},
        {"backdate_one_day": True, "correction_reason": "Hợp lệ", "effective_at": "2020-01-01T00:00:00+07:00"},
        {"backdate_one_day": True, "correction_reason": "Hợp lệ", "business_date": "2020-01-01"},
        {"backdate_one_day": False, "correction_reason": "Không được dùng"},
    ],
)
def test_backdate_rejects_invalid_reason_boolean_and_client_time_override(payload):
    now = datetime(2026, 9, 5, 15, 0, tzinfo=live.VN_TZ)

    with pytest.raises(HTTPException) as error:
        live._financial_timing(payload, now)

    assert error.value.status_code == 400


def test_checkout_uses_booking_timestamp():
    now = datetime(2026, 9, 5, 15, 0, tzinfo=live.VN_TZ)
    state = _payable_state(now)
    state["employees"][0]["booked_at"] = "2026-09-04T09:15:00+07:00"
    invoice = live._apply_action(state, "checkout", {"employee_id": "e1", "payment_method": "TIỀN MẶT"}, "admin", now)["invoice"]
    assert invoice["effective_at"] == "2026-09-04T09:15:00+07:00"
    assert invoice["business_date"] == "2026-09-04"
    assert invoice["bill_no"].startswith("LIVE-20260904-")
    assert invoice["recorded_at"] == live._iso(now)
    assert state["reports"][0]["effective_at"] == invoice["effective_at"]



def test_quick_checkout_uses_booking_timestamp():
    now = datetime(2026, 9, 5, 15, 0, tzinfo=live.VN_TZ)
    state = _payable_state(now)
    state["employees"][0]["booked_at"] = "2026-09-04T09:15:00+07:00"
    invoice = live._apply_action(state, "quick_checkout", {"employee_id": "e1", "payment_method": "TIỀN MẶT"}, "admin", now)["invoice"]
    assert invoice["effective_at"] == "2026-09-04T09:15:00+07:00"
    assert invoice["business_date"] == "2026-09-04"
    assert invoice["bill_no"].startswith("LIVE-20260904-")
    assert invoice["recorded_at"] == live._iso(now)
    assert state["reports"][0]["effective_at"] == invoice["effective_at"]



def test_combo_purchase_backdate_propagates_timing_to_purchase_invoice_and_report():
    now = datetime(2026, 9, 5, 15, 0, tzinfo=live.VN_TZ)
    state = live._empty_state(now)
    combo = state["combos"][0]

    result = live._apply_action(
        state,
        "combo_purchase",
        {
            "combo_id": combo["id"],
            "customer_name": "Khách A",
            "customer_phone": "0901",
            "payment_method": "THẺ",
            "backdate_one_day": True,
            "correction_reason": "Bổ sung giao dịch",
        },
        "admin",
        now,
    )

    for item in (result["purchase"], result["invoice"], state["reports"][-1]):
        assert item["recorded_at"] == "2026-09-05T15:00:00+07:00"
        assert item["effective_at"] == "2026-09-04T23:59:00+07:00"
        assert item["business_date"] == "2026-09-04"
        assert item["correction_reason"] == "Bổ sung giao dịch"
    assert result["purchase"]["purchased_at"] == result["purchase"]["recorded_at"]
    assert result["invoice"]["bill_no"] == "LIVE-20260904-0001"


class _Identity(BaseModel):
    employee_username: str = "operator"
    full_name: str = "Operator"


class _Connection:
    def execute(self, *_args, **_kwargs):
        class _Result:
            rowcount = 1

            @staticmethod
            def scalar():
                return True

        return _Result()


class _Engine:
    @contextmanager
    def begin(self):
        yield _Connection()


def _action_endpoint(app: FastAPI):
    return next(
        route.endpoint for route in app.routes
        if getattr(route, "path", "") == "/v2/live-tour/action"
    )


def test_backdate_route_requires_payment_then_admin_before_read_or_mutation(monkeypatch):
    app = FastAPI()
    checked: list[str] = []
    state_reads: list[bool] = []

    def require(_conn, _identity, feature):
        checked.append(feature)
        if feature == "live_tour_admin":
            raise HTTPException(403, "Không có quyền quản trị")

    monkeypatch.setattr(live, "_read_state", lambda *_args, **_kwargs: state_reads.append(True))
    live.install_live_tour_routes(
        app,
        engine_instance=_Engine,
        current_identity=lambda: _Identity(),
        require_feature=require,
        feature_allowed=lambda *_args: False,
        identity_type=_Identity,
    )

    with pytest.raises(HTTPException) as error:
        _action_endpoint(app)(
            live.LiveTourAction(
                action="checkout",
                idempotency_key="backdate-denied-1",
                payload={
                    "employee_id": "e1",
                    "payment_method": "TIỀN MẶT",
                    "backdate_one_day": True,
                    "correction_reason": "Sửa ngày",
                },
            ),
            _Identity(),
        )

    assert error.value.status_code == 403
    assert checked == ["live_tour_payment", "live_tour_admin"]
    assert state_reads == []


def test_booking_dated_payment_replay_returns_same_result_without_second_invoice(monkeypatch):
    app = FastAPI()
    seed_now = datetime(2026, 9, 5, 15, 0, tzinfo=live.VN_TZ)
    shared = {"state": _payable_state(seed_now), "revision": 0}

    def read_state(_conn, _now, **_kwargs):
        return deepcopy(shared["state"]), shared["revision"]

    def write_state(_conn, state, revision, _actor):
        shared["state"] = deepcopy(state)
        shared["revision"] = revision + 1
        return shared["revision"]

    monkeypatch.setattr(live, "_read_state", read_state)
    monkeypatch.setattr(live, "_write_state", write_state)
    live.install_live_tour_routes(
        app,
        engine_instance=_Engine,
        current_identity=lambda: _Identity(),
        require_feature=lambda *_args: None,
        feature_allowed=lambda *_args: True,
        identity_type=_Identity,
    )
    endpoint = _action_endpoint(app)
    body = live.LiveTourAction(
        action="checkout",
        idempotency_key="backdate-replay-1",
        expected_revision=0,
        payload={
            "employee_id": "e1",
            "payment_method": "TIỀN MẶT",

        },
    )

    first = endpoint(body, _Identity())
    second = endpoint(body, _Identity())

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["result"] == first["result"]
    assert len(shared["state"]["invoices"]) == 1
    assert len(shared["state"]["reports"]) == 1
    assert shared["revision"] == 1

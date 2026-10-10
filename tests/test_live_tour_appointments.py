"""Appointment permissions and retained board values across payment transitions."""
from copy import deepcopy
from datetime import timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteEngine, RouteIdentity, employee, state_with
from test_live_tour_safety import api_client
from vera_web_v2_live_tour_daily import sync_daily


CLEARED = {"Trạng thái", "Phòng", "TG CÒN LẠI", "Yêu cầu", "Dịch vụ"}


def running_state():
    state = state_with(employee("e1", "An An", vip=True), employee("e2", "An Bình"))
    next(row for row in state["services"] if row["name"] == "Body 90")["price"] = 100
    live._booking(state, {"employee_id": "e1", "room": "1.1", "service": "Body 90", "request": "YC",
                          "appointment": "16:30 · khách hẹn", "note": "Giữ ghi chú"}, NOW)
    live._start_employee(state, state["employees"][0], NOW)
    state["employees"][0].update(clock_in="10:00", clock_out="12:00", last_break_remaining_minutes=5)
    return state


@pytest.mark.parametrize("action", ["complete", "finish_to_pending", "move_pending", "checkout", "quick_checkout"])
def test_service_columns_clear_and_booking_note_moves_with_invoice_source(action):
    state = running_state()
    at = NOW + timedelta(minutes=60)
    before = live._employee_record(state["employees"][0], at)
    payload = {"employee_id": "e1", "payment_method": "TIỀN MẶT"}
    if action in {"move_pending", "checkout", "quick_checkout"}:
        live._apply_action(state, "complete", payload, "tester", at)
    result = live._apply_action(state, action, payload, "tester", at)
    after = live._employee_record(state["employees"][0], at)
    assert all(after[column] == "" for column in CLEARED)
    for column in set(live.BOARD_COLUMNS) - CLEARED - {"TT thanh toán", "Kết quả hoàn thành", "Ghi chú"}:
        assert after[column] == before[column], column
    assert after["Ghi chú"] == (before["Ghi chú"] if action == "complete" else "")
    assert after["TT thanh toán"] == ("ĐÃ THANH TOÁN" if action in {"checkout", "quick_checkout"} else "CHO THANH TOÁN")
    assert after["Kết quả hoàn thành"] == "Sớm 30 phút"
    assert after["_countdown_deadline"] == ""
    assert after["_active_booking"] is False
    assert after["_payment_pending"] is (action == "complete")
    assert after["TG bắt đầu thực hiện"] == "" and after["TG bắt đầu thực hiện YC"]
    assert live._room_available(state, "1.1")
    entries = result.get("invoice", result.get("pending", {})).get("entries")
    if entries:
        assert entries[0]["service"] == "Body 90"
        assert entries[0]["room"] == "1.1"
        assert entries[0]["request"] == "YC" and entries[0]["price"] == 100
        assert entries[0]["note"] == before["Ghi chú"]
    if action != "complete":
        assert not live._has_unsettled_work(state["employees"][0])
        with pytest.raises(HTTPException):
            live._apply_action(state, "checkout", payload, "tester", at)


def test_old_pending_checkout_does_not_clear_new_booking_or_appointment():
    state = running_state()
    pending = live._apply_action(state, "finish_to_pending", {"employee_id": "e1"}, "tester", NOW)["pending"]
    live._apply_action(state, "update_appointment", {"employee_id": "e1", "appointment": "18:00"}, "tester", NOW)
    worker = live._booking(state, {"employee_id": "e1", "room": "2.1", "service": "Body 90"}, NOW)
    assert worker["appointment"] == "18:00" and worker["note"] == ""
    assert pending["entries"][0]["note"] == "Giữ ghi chú"
    assert "last_assignment_display" not in worker
    record = live._employee_record(worker, NOW)
    assert record["TG bắt đầu thực hiện YC"] == live._display_datetime(NOW)
    assert record["Kết quả hoàn thành"] == ""
    before = deepcopy(worker)
    live._apply_action(state, "checkout", {"pending_id": pending["id"], "payment_method": "TIỀN MẶT"}, "tester", NOW)
    assert state["employees"][0] == before


def test_pending_payment_updates_its_retained_payment_label_only():
    state = running_state()
    pending = live._apply_action(state, "finish_to_pending", {"employee_id": "e1"}, "tester", NOW)["pending"]
    before = live._employee_record(state["employees"][0], NOW)
    live._apply_action(state, "checkout", {"pending_id": pending["id"], "payment_method": "TIỀN MẶT"}, "tester", NOW)
    after = live._employee_record(state["employees"][0], NOW)
    assert after == {**before, "TT thanh toán": "ĐÃ THANH TOÁN"}


class AppointmentIdentity(RouteIdentity):
    role: str


def appointment_client(monkeypatch, role, view=True):
    state = running_state()
    live._ensure_counter_day(state, live.datetime.now(live.VN_TZ))
    _, shared = api_client(monkeypatch, state)
    def allowed(_conn, _ident, feature):
        return view and feature == "live_tour_view"
    def require(conn, ident, feature):
        if not allowed(conn, ident, feature):
            raise HTTPException(403, feature)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine,
                                 current_identity=lambda: AppointmentIdentity(role=role),
                                 require_feature=require, feature_allowed=allowed, identity_type=AppointmentIdentity)
    return TestClient(app), shared


def request_body(**overrides):
    return {"action": "update_appointment", "expected_revision": 1, "idempotency_key": "appointment-edit-1",
            "payload": {"employee_id": "e1", "employee_ids": ["e1"], "appointment": " 17:00 ngày mai "}, **overrides}


@pytest.mark.parametrize("role", ["letan", "quanly", "admin", "nhanvien", "leader", ""])
def test_appointment_role_permissions_apply_to_http_and_ui_capability(monkeypatch, role):
    client, shared = appointment_client(monkeypatch, role)
    can_edit = role in {"letan", "quanly", "admin"}
    assert client.get("/v2/live-tour").json()["capabilities"]["appointment_edit"] is can_edit
    before = deepcopy(shared["state"]["employees"])
    response = client.post("/v2/live-tour/action", json=request_body())
    assert response.status_code == (200 if can_edit else 403)
    if can_edit:
        before[0]["appointment"] = "17:00 ngày mai"
    assert shared["state"]["employees"] == before


def test_appointment_requires_board_access_even_for_admin(monkeypatch):
    client, shared = appointment_client(monkeypatch, "admin", view=False)
    assert client.post("/v2/live-tour/action", json=request_body()).status_code == 403
    assert shared["revision"] == 1


def test_appointment_revision_retry_and_explicit_clearing(monkeypatch):
    client, shared = appointment_client(monkeypatch, "letan")
    body = request_body()
    assert client.post("/v2/live-tour/action", json=body).status_code == 200
    assert client.post("/v2/live-tour/action", json=body).json()["duplicate"] is True
    assert shared["revision"] == 2
    body["idempotency_key"] = "appointment-edit-2"
    body["payload"]["appointment"] = ""
    assert client.post("/v2/live-tour/action", json=body).status_code == 409
    assert shared["state"]["employees"][0]["appointment"] == "17:00 ngày mai"
    body["expected_revision"] = 2
    assert client.post("/v2/live-tour/action", json=body).status_code == 200
    assert shared["state"]["employees"][0]["appointment"] == ""


def test_website_booking_appointment_writes_only_for_working_staff_today(monkeypatch):
    class FrozenDateTime(live.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(live, "datetime", FrozenDateTime)
    client, shared = appointment_client(monkeypatch, "letan")
    writer = client.app.state.website_booking_appointment_writer
    result = writer("An An", NOW.date(), "19:30")
    assert result["applied"] is True
    worker = shared["state"]["employees"][0]
    assert worker["appointment"] == "16:30 · khách hẹn · YC 19:30"

    worker["work_status"] = "Nghỉ"
    rejected = writer("An An", NOW.date(), "20:00")
    assert rejected == {"applied": False, "reason": "staff_no_longer_working"}
    assert worker["appointment"].endswith("YC 19:30")


def test_website_booking_appointment_is_not_written_for_another_day(monkeypatch):
    class FrozenDateTime(live.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(live, "datetime", FrozenDateTime)
    client, shared = appointment_client(monkeypatch, "letan")
    writer = client.app.state.website_booking_appointment_writer
    result = writer("An An", NOW.date() + timedelta(days=1), "19:30")
    assert result == {"applied": False, "reason": "not_today"}
    assert shared["state"]["employees"][0]["appointment"] == "16:30 · khách hẹn"


def test_website_booking_suffix_is_removed_at_day_rollover():
    worker = employee("e1", "An An")
    worker.update(appointment="Lịch riêng · YC 19:30", roster_eligible=True,
                  _website_booking_appointment_day="2026-09-05",
                  _website_booking_appointment_values=["YC 19:30"])
    state = state_with(worker)
    sync_daily(state, [{"username":"An An"}], [], automatic=True, today="2026-09-06")
    assert worker["appointment"] == "Lịch riêng"
    assert "_website_booking_appointment_day" not in worker
    assert "_website_booking_appointment_values" not in worker


@pytest.mark.parametrize("overrides", [
    {"idempotency_key": None}, {"expected_revision": None},
    {"payload": {"employee_id": "e1", "appointment": 123}},
    {"payload": {"employee_id": "e1", "appointment": "x" * 201}},
    {"payload": {"employee_id": "e1", "appointment": "17:00\n18:00"}},
    {"payload": {"employee_id": "missing", "appointment": "17:00"}},
    {"payload": {"employee_ids": ["e1", "e2"], "appointment": "17:00"}},
    {"payload": {"employee_id": "e1", "employee_ids": ["e2"], "appointment": "17:00"}},
])
def test_invalid_appointment_never_mutates_state(monkeypatch, overrides):
    client, shared = appointment_client(monkeypatch, "letan")
    before = deepcopy(shared)
    assert client.post("/v2/live-tour/action", json=request_body(**overrides)).status_code in {400, 404, 428}
    assert shared == before


def test_online_booking_edit_delete_reconciles_only_owned_tokens():
    a = employee('e1', 'An An')
    a.update(username='AN AN', work_status='Đi làm', roster_eligible=True, appointment='Khách riêng · YC 19:30 · YC 19:30', _website_booking_appointment_day='2026-10-01', _website_booking_appointment_values=['YC 19:30'])
    b = employee('e2', 'B')
    b.update(username='B', work_status='Đi làm', roster_eligible=True, appointment='')
    state = state_with(a, b)
    live._sync_online_booking_requests(state, [{'requested_staff':'B','appointment_time':'20:00'},{'requested_staff':'B','appointment_time':'20:00'}], '2026-10-01')
    assert a['appointment'] == 'Khách riêng · YC 19:30'
    assert b['appointment'] == 'YC 20:00'
    assert live._sync_online_booking_requests(state, [{'requested_staff':'B','appointment_time':'20:00'}], '2026-10-01') == 0
    live._sync_online_booking_requests(state, [], '2026-10-01')
    assert b['appointment'] == ''
    assert a['appointment'] == 'Khách riêng · YC 19:30'


def test_online_booking_projection_excludes_leave_and_keeps_other_booking_time():
    a = employee('e1', 'A')
    a.update(username='A', work_status='Nghỉ phép', roster_eligible=False, appointment='Khách riêng')
    state = state_with(a)
    live._sync_online_booking_requests(state, [{'requested_staff':'A','appointment_time':'19:30'}], '2026-10-01')
    assert a['appointment'] == 'Khách riêng'

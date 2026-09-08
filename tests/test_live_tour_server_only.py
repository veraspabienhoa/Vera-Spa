"""Live Tour is database-only, including first boot and stale-client requests."""
import ast
import json
import re
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteIdentity, employee, state_with


class SettingsDatabase:
    """SQL contract fixture; state survives creation of a second app instance."""
    def __init__(self, stored=None):
        self.stored = deepcopy(stored)
        self.revision = 7 if stored else 0
        self.employee_reads = 0
        self.fail_employee_read = False

    @contextmanager
    def begin(self):
        before = deepcopy(self.stored), self.revision
        try:
            yield self
        except Exception:
            self.stored, self.revision = before
            raise

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        rows = []
        count = 1
        if "FROM employees" in sql:
            self.employee_reads += 1
            if self.fail_employee_read:
                raise RuntimeError("database unavailable")
            rows = [{"username": "server-ktv", "full_name": "Nhân viên máy chủ", "role": "nhanvien", "payload": {"Đi làm": "Đi làm", "Vào ca": "Ca 2"}}]
        elif "SELECT value_json" in sql:
            rows = [{"value_json": deepcopy(self.stored), "revision": self.revision}] if self.stored else []
        elif "INSERT INTO vera_app_setting" in sql:
            self.stored, self.revision = json.loads(params["value"]), 1
        elif "UPDATE vera_app_setting" in sql:
            if params["revision"] != self.revision:
                count = 0
            else:
                self.stored, self.revision = json.loads(params["value"]), self.revision + 1
        else:
            assert "pg_advisory_xact_lock" in sql, sql

        class Result:
            rowcount = count
            def mappings(self): return self
            def all(self): return rows
            def first(self): return rows[0] if rows else None
        return Result()


def app_client(database):
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda: database,
        current_identity=lambda: RouteIdentity(), require_feature=lambda *_args: None,
        feature_allowed=lambda *_args: True, identity_type=RouteIdentity)
    return app, TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def forbid_external_requests(monkeypatch):
    import requests.sessions
    import socket
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Live Tour must not access external sources")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def test_first_boot_uses_database_and_starts_employees_off_duty():
    database = SettingsDatabase()
    app, client = app_client(database)
    response = client.get("/v2/live-tour").json()
    assert response["storage_mode"] == "server"
    worker = response["state"]["employees"][0]
    assert worker["username"] == "server-ktv"
    assert worker["work_status"] == "Nghỉ" and worker["shift"] == ""
    assert worker["service"] == "" and worker["room"] == ""
    assert database.stored["bootstrap_source"] == "employees"
    assert "sync" not in response["capabilities"]
    assert not hasattr(app.state, "live_tour_leave_sync_service")
    client.get("/v2/live-tour?refresh=true")
    assert database.employee_reads == 1


def test_first_boot_database_error_does_not_save_an_empty_board():
    database = SettingsDatabase()
    database.fail_employee_read = True
    _, client = app_client(database)
    assert client.get("/v2/live-tour").status_code == 500
    assert database.stored is None
    database.fail_employee_read = False
    assert client.get("/v2/live-tour").status_code == 200
    assert len(database.stored["employees"]) == 1


def test_booking_is_persisted_and_read_by_a_new_app_instance():
    database = SettingsDatabase()
    _, first = app_client(database)
    data = first.get("/v2/live-tour").json()
    worker_id = data["state"]["employees"][0]["id"]
    for number, (action, payload) in enumerate([
        ("set_work_status", {"status": "Đi làm"}), ("set_shift", {"shift": "Ca 1"}),
        ("booking", {"service": "Body 90", "room": "1.1"}), ("start", {}),
    ]):
        result = first.post("/v2/live-tour/action", json={"action": action,
            "expected_revision": data["revision"], "idempotency_key": f"server-operation-{number}",
            "payload": {"employee_id": worker_id, **payload}})
        assert result.status_code == 200, result.text
        data = result.json()
    _, second = app_client(database)
    loaded = second.get("/v2/live-tour").json()
    assert loaded["state"]["employees"] == data["state"]["employees"]
    assert loaded["revision"] == data["revision"]
    assert loaded["state"]["employees"][0]["service"] == "Body 90"
    assert database.employee_reads == 1


@pytest.mark.parametrize("action", ["sync_leaves", "merge_current_tour", "merge_current_tour_preview", " SYNC_LEAVES "])
def test_retired_external_actions_reject_before_database_access_or_replay(action):
    database = SettingsDatabase()
    _, client = app_client(database)
    response = client.post("/v2/live-tour/action", json={"action": action, "payload": {"url": "https://example.com/source.xlsm"}})
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "LIVE_TOUR_SERVER_ONLY"
    assert database.stored is None and database.employee_reads == 0
    state = state_with(employee("e1", "An"))
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        live._apply_action(state, action, {"_source_records": []}, "admin", NOW)
    assert state == before


def test_existing_financial_and_operating_state_survives_without_external_recovery():
    state = state_with(employee("e1", "An"))
    state["employees"][0].update(service="Body 90", room="1.1", payment_status="CHO THANH TOÁN")
    state["invoices"] = [{"bill_no": "old-bill", "total": 450000}]
    state["customers"] = [{"id": "customer-1", "name": "Khách mẫu", "combo_purchases": []}]
    state["sync_status"] = {"status": "recovery_required", "idempotency_key": "old-sync"}
    state["idempotency"] = {"old-sync": {"action": "sync_leaves", "status": "recovery_required", "prepared": {"source": "legacy"}}}
    database = SettingsDatabase(state)
    _, client = app_client(database)
    data = client.get("/v2/live-tour").json()
    assert database.stored == state
    assert database.employee_reads == 0
    assert data["state"]["invoices"] == state["invoices"]
    assert all(data["state"]["customers"][0][key] == value for key, value in state["customers"][0].items())
    assert "sync_status" not in data["state"]


def test_live_tour_ui_and_api_have_no_external_source_connections():
    root = Path(__file__).resolve().parents[1]
    frontend = (root / "web-v2/src/pages/LiveTourPage.jsx").read_text()
    calls = re.findall(r"veraApi\.(\w+)\(", frontend)
    assert set(calls) <= {"liveTour", "liveTourAction", "liveTourCustomerHistory", "exportLiveTourExcel", "exportLiveTourPng"}
    for token in ("syncLeaves", "TourVera", "Google Drive", "openPurchaseReport", "merge_current_tour"):
        assert token not in frontend
    backend = (root / "vera_web_v2_live_tour.py").read_text()
    imports = [n.module for n in ast.walk(ast.parse(backend)) if isinstance(n, ast.ImportFrom)]
    assert not any(name and name.startswith('vera_web_v2_tour') for name in imports)
    assert "live_tour_leave_sync_service" not in (root / "vera_web_v2_tour_leave_sync.py").read_text()

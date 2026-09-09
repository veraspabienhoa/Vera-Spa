"""Exercise the real edit endpoint with the installed V3.9 validation wrapper."""
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

import vera_web_v2_policy_v39 as policy


@pytest.fixture
def edit_app(monkeypatch):
    shared, api = policy._shared, policy._shared._api
    old = {
        "record_uid": "leave-123", "source_sheet_id": "", "source_row": 0,
        "leave_date": date(2026, 9, 8), "employee_name": "Nhân viên A",
        "leave_reason": "Nghỉ CÓ phép", "detail": "Giữ ghi chú", "calculated_days": 1,
    }
    state = {"old": old, "active": True, "prepared": [], "saved": [], "committed": False,
             "rolled_back": False, "closed": False, "validation_error": None,
             "effective_start": date(2026, 9, 1), "used_days": 0}
    ident = SimpleNamespace(role="admin", employee_username="Nhân viên A")

    class Connection:
        is_active = True

        def connect(self):
            return self

        def begin(self):
            return self

        def execute(self, query, params=None):
            sql = str(query)
            if "FOR UPDATE" in sql:
                row = old.copy()
            elif "FROM employees" in sql:
                row = {"employment_start_date": state["effective_start"], "payload": {}}
            else:
                row = None
            return SimpleNamespace(mappings=lambda: SimpleNamespace(
                first=lambda: row,
                all=lambda: [{"leave_reason": "Nghỉ CÓ phép", "calculated_days": state["used_days"]}],
            ))

        def commit(self):
            state["committed"] = True
            self.is_active = False

        def rollback(self):
            state["rolled_back"] = True
            self.is_active = False

        def close(self):
            state["closed"] = True

    conn = Connection()

    # The base validator is a boundary stub with the canonical keyword contract;
    # neither the edit endpoint nor the installed wrapper is mocked.
    def prepare(conn, body, actor, *, exclude_record_uid="", skip_registration_timing=False,
                record_uid="", existing_ordinal=None, allow_inactive_employee=False):
        state["prepared"].append({
            "exclude_record_uid": exclude_record_uid, "record_uid": record_uid,
            "skip_registration_timing": skip_registration_timing,
            "existing_ordinal": existing_ordinal, "allow_inactive_employee": allow_inactive_employee,
        })
        if state["validation_error"]:
            raise state["validation_error"]
        if not state["active"] and not allow_inactive_employee:
            raise HTTPException(400, "Không tìm thấy nhân viên đang hoạt động.")
        return {**old, "record_uid": record_uid, "leave_reason": body.leave_reason,
                "detail": body.detail, "calculated_days": 0.5, "penalty": 0}, ["Cảnh báo giữ nguyên"]

    monkeypatch.setattr(shared, "_validate_and_prepare", prepare)
    # Restore both aliases after each installer invocation.
    monkeypatch.setattr(api, "_validate_and_prepare", prepare)
    monkeypatch.setattr(shared, "_policy_group", lambda conn, reason: "co_phep")
    monkeypatch.setattr(api, "_engine_instance", lambda: conn)
    monkeypatch.setattr(api, "_validate_edit_permission", lambda conn, row, reason, actor: (
        {"name": reason, "requires_manual_penalty": False}, True,
    ))
    monkeypatch.setattr(api, "_progressive_key", lambda reason: "")
    monkeypatch.setattr(api, "_rebalance_progressive_rows", lambda *args: [])
    monkeypatch.setattr(api, "_update_record", lambda conn, record, *args: state["saved"].append(record))

    app = FastAPI()

    @app.patch("/v2/staff/{username}")
    def staff_placeholder(username: str):
        raise AssertionError("Leave edits must not call staff writes")

    policy.install_policy_v39(app, engine_instance=lambda: conn, current_identity=api.current_identity,
                              require_feature=lambda *args: None, vn_tz=api.VN_TZ)
    app.add_api_route("/v2/leave/records/{record_uid}", api.update_leave, methods=["PATCH"])
    app.dependency_overrides[api.current_identity] = lambda: ident
    return TestClient(app), state, ident, conn


def edit(client):
    return client.patch("/v2/leave/records/leave-123", json={"leave_reason": "Về sớm CÓ phép"})


@pytest.mark.parametrize("role", ["admin", "letan", "quanly", "leader", "nhanvien", "locker", "tapvu"])
def test_authorized_edits_forward_options_and_commit_same_record(edit_app, role):
    client, state, ident, _ = edit_app
    ident.role = role
    response = edit(client)
    assert response.status_code == 200, response.text
    assert response.json()["record_uid"] == "leave-123"
    assert response.json()["warnings"] == ["Cảnh báo giữ nguyên"]
    assert state["prepared"] == [{"exclude_record_uid": "leave-123", "record_uid": "leave-123",
        "skip_registration_timing": True, "existing_ordinal": None, "allow_inactive_employee": role == "admin"}]
    assert len(state["saved"]) == 1
    assert state["saved"][0]["leave_reason"] == "Về sớm CÓ phép"
    assert state["saved"][0]["detail"] == "Giữ ghi chú"
    assert state["saved"][0]["calculated_days"] == 0.5
    assert state["committed"] and state["closed"] and not state["rolled_back"]


@pytest.mark.parametrize("role,expected", [("admin", 200), ("letan", 400), ("nhanvien", 400)])
def test_inactive_employee_exception_is_only_forwarded_for_admin(edit_app, role, expected):
    client, state, ident, _ = edit_app
    ident.role, state["active"] = role, False
    response = edit(client)
    assert response.status_code == expected, response.text
    assert state["committed"] == (expected == 200)
    assert state["rolled_back"] == (expected != 200)


def test_permission_rejection_still_prevents_validation_and_writes(edit_app, monkeypatch):
    client, state, _, _ = edit_app

    def reject(*args):
        raise HTTPException(403, "Không có quyền sửa lịch nghỉ.")

    monkeypatch.setattr(policy._shared._api, "_validate_edit_permission", reject)
    assert edit(client).status_code == 403
    assert state["prepared"] == state["saved"] == []
    assert state["rolled_back"] and not state["committed"]


def test_base_validation_errors_are_not_swallowed(edit_app):
    client, state, _, _ = edit_app
    state["validation_error"] = HTTPException(409, "Lịch nghỉ bị trùng.")
    response = edit(client)
    assert response.status_code == 409
    assert response.json()["detail"] == "Lịch nghỉ bị trùng."
    assert not state["saved"] and state["rolled_back"]


@pytest.mark.parametrize("role,expected", [("admin", 200), ("nhanvien", 400)])
def test_late_month_cap_still_applies_except_for_admin(edit_app, role, expected):
    client, state, ident, _ = edit_app
    ident.role = role
    state.update(effective_start=date(2026, 9, 16), used_days=3)
    state["old"]["leave_date"] = date(2026, 9, 20)
    response = edit(client)
    assert response.status_code == expected, response.text
    if expected == 400:
        assert "tối đa 3 ngày" in response.json()["detail"]
        assert state["rolled_back"] and not state["saved"]


def test_create_without_edit_options_keeps_inactive_default_false(edit_app):
    _, state, ident, conn = edit_app
    body = policy._shared._api.LeaveCreate(leave_date=date(2026, 9, 8), employee_name="Nhân viên A",
                                           leave_reason="Nghỉ CÓ phép", detail="")
    policy._shared._validate_and_prepare(conn, body, ident)
    assert state["prepared"][0]["allow_inactive_employee"] is False

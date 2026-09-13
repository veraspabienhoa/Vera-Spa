"""Bound catalog reads without caching policies across requests or changing access."""
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
import pytest

import vera_web_v2_api as api
import vera_web_v2_api_shared as shared
import vera_web_v2_letan_leave_guard as guard
from vera_web_v2_leave_violation_split import install_leave_violation_split_routes


class PolicyConnection:
    def __init__(self):
        self.reads = 0
        self.rows = [
            {"Lý do nghỉ": f"Lý do {i}", "Loại nghỉ": "Có phép", "Số ngày tính phép": 0.5,
             "Phạt vi phạm": "50.000", "User có quyền được nhập": "nhanvien",
             "Chỉ nhập được cuối tuần": "Cuối tuần"}
            for i in range(60)
        ]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_args, **_kwargs):
        self.reads += 1
        return SimpleNamespace(scalar_one_or_none=lambda: {"rows": self.rows})


@pytest.fixture
def catalog(monkeypatch):
    conn = PolicyConnection()
    engine = SimpleNamespace(connect=lambda: conn)
    monkeypatch.setattr(api, "_engine_instance", lambda: engine)
    monkeypatch.setattr(api, "_require_feature", lambda *_: None)
    monkeypatch.setattr(api, "_feature_allowed", lambda _conn, ident, _: ident.role == "admin")
    monkeypatch.setattr(api, "_reason_item", shared._reason_item)
    monkeypatch.setattr(api, "load_employee_self_service_policy", lambda _: {"enabled": True})
    monkeypatch.setattr(api, "load_letan_leave_policy", lambda _: {"enabled": True})
    monkeypatch.setattr(guard, "load_letan_leave_policy", lambda _: {"enabled": True})
    app = FastAPI()
    app.add_api_route("/v2/leave/reasons", api.reasons, methods=["GET"])
    guard._install_admin_reason_catalog(app, api)
    install_leave_violation_split_routes(
        app, engine_instance=api._engine_instance, current_identity=lambda: None,
        require_feature=api._require_feature, feature_allowed=api._feature_allowed,
        policy_rows=api._policy_rows, field=api._field, reason_item=api._reason_item,
        role_tokens=api._role_tokens, day_allowed=api._day_allowed, norm=api._norm,
    )
    routes = {r.path: r.dependant.call for r in app.routes if hasattr(r, "dependant")}
    return conn, routes


@pytest.mark.parametrize("path", ["reasons", "reason-groups", "reason-types"])
def test_catalog_reads_policy_once_and_next_request_sees_policy_edit(catalog, path):
    conn, routes = catalog
    call = routes[f"/v2/leave/{path}"]
    kwargs = {"ident": SimpleNamespace(role="nhanvien")}
    if path != "reason-types":
        kwargs["date_value"] = date(2026, 9, 13)
    key = {"reasons": "reasons", "reason-groups": "leave_reasons", "reason-types": "items"}[path]
    first = call(**kwargs)[key]
    assert len(first) == 60
    assert conn.reads == 1
    if path != "reason-types":
        assert first[0]["penalty"] is None
        assert first[0]["days"] == 0.5
    conn.rows[0] = {**conn.rows[0], "Lý do nghỉ": "Đã sửa Nội quy"}
    second = call(**kwargs)[key]
    assert second[0]["name"] == "Đã sửa Nội quy"
    assert conn.reads == 2


def test_admin_keeps_all_reasons_on_weekdays_and_other_roles_keep_restrictions(catalog):
    conn, routes = catalog
    call = routes["/v2/leave/reasons"]
    monday = date(2026, 9, 14)
    admin = call(date_value=monday, ident=SimpleNamespace(role="admin"))["reasons"]
    assert len(admin) == 60
    assert admin[0]["penalty"] == 50000
    assert conn.reads == 1
    assert call(date_value=monday, ident=SimpleNamespace(role="nhanvien"))["reasons"] == []
    assert call(date_value=date(2026, 9, 13), ident=SimpleNamespace(role="letan"))["reasons"] == []
    assert conn.reads == 3


def test_write_reason_lookup_remains_fresh_and_empty_snapshot_fails_closed(catalog):
    conn, _ = catalog
    assert api._reason_item(conn, "Lý do 0")["days"] == 0.5
    conn.rows[0] = {**conn.rows[0], "Số ngày tính phép": 1}
    assert api._reason_item(conn, "Lý do 0")["days"] == 1
    assert conn.reads == 2
    with pytest.raises(HTTPException) as error:
        api._reason_item(conn, "Lý do 0", policy_rows=[])
    assert error.value.status_code == 400
    assert conn.reads == 2

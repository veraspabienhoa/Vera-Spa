from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import ValidationError

from vera_revenue_entry_window import effective_days, save_window, require_entry_date
from vera_web_v2_permissions import PermissionUpdate


TODAY = date(2026, 3, 1)


class Connection:
    def __init__(self, payload):
        self.payload = payload

    def execute(self, *args):
        return SimpleNamespace(scalar_one_or_none=lambda: self.payload)


def identity(role="letan", username="cashier"):
    return SimpleNamespace(role=role, employee_username=username)


@pytest.mark.parametrize("days", [1, 3, 5, 7, 11, 36500])
def test_inclusive_window_rejects_previous_day_and_future(days):
    conn = Connection({"revenue_entry_windows": {"roles": {"letan": days}}})
    first = TODAY - timedelta(days=days - 1)
    assert require_entry_date(conn, identity(), first, TODAY)["min_date"] == first.isoformat()
    assert require_entry_date(conn, identity(), TODAY, TODAY)["max_date"] == TODAY.isoformat()
    for day in (first - timedelta(days=1), TODAY + timedelta(days=1)):
        with pytest.raises(HTTPException) as error:
            require_entry_date(conn, identity(), day, TODAY)
        assert error.value.status_code == 403


def test_account_override_all_days_role_fallback_admin_and_legacy():
    payload = {"revenue_entry_windows": {"roles": {"LETAN": 3}, "accounts": {"Cashier": None}}}
    assert effective_days(payload, "letan", "cashier") is None
    assert effective_days(payload, "letan", "other") == 3
    payload["revenue_entry_windows"]["accounts"]["Cashier"] = 5
    assert effective_days(payload, "letan", "cashier") == 5
    assert effective_days(payload, "admin", "cashier") is None
    assert effective_days({}, "letan", "cashier") is None


def test_older_and_other_page_saves_preserve_scope_inherit_removes_it():
    payload = {}
    save_window(payload, "role", "letan", inherit=False, supplied=True, days=3)
    save_window(payload, "account", "Cashier", inherit=False, supplied=True, days=7,
                edited_features=["revenue_entry_create"])
    save_window(payload, "account", "cashier", inherit=False, supplied=False, days=None,
                edited_features=["staff_list"])
    assert effective_days(payload, "letan", "cashier") == 7
    save_window(payload, "account", "cashier", inherit=True, supplied=False, days=None)
    assert effective_days(payload, "letan", "cashier") == 3
    with pytest.raises(HTTPException):
        save_window(payload, "account", "cashier", inherit=False, supplied=True, days=None,
                    edited_features=["staff_list"])


@pytest.mark.parametrize("value", [0, -1, 36501, True, 3.5, "3", "all"])
def test_invalid_permission_window_is_rejected(value):
    with pytest.raises(ValidationError):
        PermissionUpdate(revenue_entry_window_days=value)


def test_explicit_all_differs_from_older_client_omission():
    assert "revenue_entry_window_days" not in PermissionUpdate().model_fields_set
    assert "revenue_entry_window_days" in PermissionUpdate(revenue_entry_window_days=None).model_fields_set


def test_revoked_scope_is_rechecked_on_write_and_duplicate_confirmation_cannot_bypass(monkeypatch):
    import vera_web_v2_revenue_leave_list as routes
    conn = Connection({"revenue_entry_windows": {"roles": {"letan": 3}}})
    @contextmanager
    def begin():
        yield conn
    app = FastAPI()
    app.get('/v2/leave/records')(lambda: {})
    app.get('/v2/leave/daily-stats')(lambda: {})
    routes.install_revenue_leave_list_routes(app, engine_instance=lambda: SimpleNamespace(begin=begin),
        current_identity=lambda: None, require_feature=lambda *args: None,
        feature_allowed=lambda *args: True, norm=str, progressive_key=str, google_client=lambda: None)
    create = next(r.endpoint for r in app.routes if r.path == '/v2/revenue/entry')
    monkeypatch.setattr(routes.revenue_auto, 'require_manual', lambda conn: None)
    writes = []
    monkeypatch.setattr(routes.revenue_store, 'find_duplicate_web_entries', lambda *args, **kwargs: [])
    monkeypatch.setattr(routes.revenue_store, 'insert_web_entries', lambda *args, **kwargs: writes.append(kwargs) or [])
    today = routes.datetime.now(routes.VN_TZ).date()
    body = routes.RevenueEntryCreate(transaction_date=today-timedelta(days=2), income_amount=100, expense_amount=50, confirm_duplicate=True)
    assert create(body, BackgroundTasks(), identity())["ok"]
    assert len(writes) == 1 and len(writes[0]['entries']) == 2
    conn.payload['revenue_entry_windows']['roles']['letan'] = 1
    with pytest.raises(HTTPException) as error:
        create(body, BackgroundTasks(), identity())
    assert error.value.status_code == 403 and len(writes) == 1


def test_permission_api_roundtrip_revision_and_reset():
    from test_live_tour_date_permission_catalog import permission_client
    client, store = permission_client()
    allowed = ["revenue_view", "revenue_entry_create"]
    response = client.put('/v2/permissions/role/letan', json={
        'allowed_features': allowed, 'expected_revision': 12, 'revenue_entry_window_days': 3})
    assert response.status_code == 200, response.text
    overview = client.get('/v2/permissions').json()
    assert overview['revenue_entry_window_policy_version'] == 1
    assert overview['revenue_entry_windows']['roles']['letan'] == 3
    response = client.put('/v2/permissions/account/operator', json={
        'allowed_features': allowed, 'edited_features': ['revenue_entry_create'],
        'preserve_unchanged': True, 'expected_revision': 13, 'revenue_entry_window_days': 5})
    assert response.status_code == 200, response.text
    assert effective_days(store['payload'], 'letan', 'operator') == 5
    response = client.put('/v2/permissions/account/operator', json={
        'allowed_features': allowed, 'expected_revision': 13, 'revenue_entry_window_days': None})
    assert response.status_code == 409
    assert effective_days(store['payload'], 'letan', 'operator') == 5
    response = client.put('/v2/permissions/account/operator', json={
        'allowed_features': allowed, 'expected_revision': 14, 'revenue_entry_window_days': None})
    assert response.status_code == 200, response.text
    assert effective_days(store['payload'], 'letan', 'operator') is None
    response = client.put('/v2/permissions/account/operator', json={'inherit': True, 'expected_revision': 15})
    assert response.status_code == 200, response.text
    assert effective_days(store['payload'], 'letan', 'operator') == 3

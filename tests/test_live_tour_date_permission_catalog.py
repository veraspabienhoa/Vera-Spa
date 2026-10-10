"""Date-only inheritance and Admin role/account persistence regressions."""
from copy import deepcopy
from datetime import timezone
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from vera_web_v2_api import Identity, _feature_allowed
from vera_web_v2_live_tour_permissions import (
    DATE_FILTER_DEPENDENCIES, DATE_FILTER_FEATURES, DATE_FILTER_PARENT_ANY,
    DATE_FILTER_POLICY_VERSION, DATE_FILTER_PRESETS, DATE_FILTER_SECTIONS,
)
from vera_web_v2_permissions import (
    FEATURES, ROLES, PermissionUpdate, install_permission_routes,
    permission_closure, permission_pages,
)


def identity(role="letan", username="operator"):
    return Identity(auth_user_id="test", employee_username=username, role=role)


def grant(feature, allowed, target="operator"):
    return {"target": target, "feature": feature, "allowed": allowed}


def section_read(feature, ident, payload):
    return all(_feature_allowed(None, ident, parent, payload) for parent in DATE_FILTER_DEPENDENCIES[feature]) and (
        not DATE_FILTER_PARENT_ANY.get(feature)
        or any(_feature_allowed(None, ident, parent, payload) for parent in DATE_FILTER_PARENT_ANY[feature])
    )


def test_versioned_catalog_has_exactly_four_sections_and_eight_independent_presets():
    assert DATE_FILTER_POLICY_VERSION == 1
    assert list(DATE_FILTER_PRESETS.values()) == ["Tất cả", "Hôm nay", "Hôm qua", "Tuần này", "Tuần trước", "Tháng này", "Tháng trước", "Tùy chỉnh"]
    assert len(DATE_FILTER_FEATURES) == 32
    assert set(DATE_FILTER_SECTIONS) == {"pending", "invoices", "reports", "history"}
    published = [key for page in permission_pages() for key in page["features"]]
    for feature in DATE_FILTER_FEATURES:
        assert feature in FEATURES
        assert published.count(feature) == 1
    assert PermissionUpdate(allowed_features=list(FEATURES)).allowed_features == list(FEATURES)


@pytest.mark.parametrize("role", ["admin", *ROLES, "giamdoc"])
@pytest.mark.parametrize("feature", DATE_FILTER_FEATURES)
def test_every_unconfigured_role_date_flag_inherits_existing_effective_section(role, feature):
    ident = identity(role)
    assert _feature_allowed(None, ident, feature, {}) == section_read(feature, ident, {})


@pytest.mark.parametrize("feature", DATE_FILTER_FEATURES)
def test_explicit_account_role_date_grants_are_independent_with_read_denials_winning(feature):
    ident = identity()
    parents = [*DATE_FILTER_DEPENDENCIES[feature], *DATE_FILTER_PARENT_ANY.get(feature, ())[:1]]
    payload = {"roles": [grant(parent, True, "letan") for parent in parents], "accounts": []}
    assert _feature_allowed(None, ident, feature, payload)
    payload["roles"].append(grant(feature, False, "letan"))
    assert not _feature_allowed(None, ident, feature, payload)
    payload["accounts"].append(grant(feature, True))
    assert _feature_allowed(None, ident, feature, payload)
    for parent in DATE_FILTER_DEPENDENCIES[feature]:
        denied = deepcopy(payload)
        denied["accounts"].append(grant(parent, False))
        assert not _feature_allowed(None, ident, feature, denied)
    payload["accounts"] = [grant(feature, False)]
    payload["roles"][-1]["allowed"] = True
    assert not _feature_allowed(None, ident, feature, payload)


@pytest.mark.parametrize("feature", DATE_FILTER_FEATURES)
def test_role_date_true_never_overrides_account_read_deny(feature):
    denied = list(DATE_FILTER_DEPENDENCIES[feature]) or list(DATE_FILTER_PARENT_ANY[feature])
    payload = {"roles": [grant(feature, True, "letan")], "accounts": [grant(parent, False) for parent in denied]}
    assert not _feature_allowed(None, identity(), feature, payload)


@pytest.mark.parametrize("preset", DATE_FILTER_PRESETS)
def test_backup_only_history_inheritance_never_adds_audit_access(preset):
    feature = f"live_tour_history_date_{preset}"
    payload = {"accounts": [grant("live_tour_view", True), grant("live_tour_backup", True), grant("live_tour_history_view", False)]}
    assert _feature_allowed(None, identity(), feature, payload)
    assert not _feature_allowed(None, identity(), "live_tour_history_view", payload)
    assert "live_tour_history_view" not in permission_closure({feature, "live_tour_backup"})
    payload["accounts"][1]["allowed"] = False
    assert not _feature_allowed(None, identity(), feature, payload)


@pytest.mark.parametrize("preset", DATE_FILTER_PRESETS)
def test_standalone_reports_do_not_gain_a_live_tour_view_requirement(preset):
    payload = {"accounts": [grant("live_tour_view", False), grant("live_tour_reports_view", True)]}
    assert _feature_allowed(None, identity(), f"live_tour_reports_date_{preset}", payload)
    assert "live_tour_view" not in permission_closure({f"live_tour_reports_date_{preset}"})


def test_unrelated_legacy_dependency_behavior_is_unchanged():
    payload = {"accounts": [grant("live_tour_payment", False), grant("live_tour_invoice_view", True)]}
    assert _feature_allowed(None, identity(), "live_tour_invoice_view", payload)


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)
    def mappings(self):
        return self
    def first(self):
        return self.rows[0] if self.rows else None
    def all(self):
        return self.rows
    def scalar_one_or_none(self):
        return next(iter(self.rows[0].values())) if self.rows else None


class MemoryConnection:
    def __init__(self, store):
        self.store = store
        self.is_active = True
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def begin(self):
        return self
    def commit(self):
        self.is_active = False
    def rollback(self):
        self.is_active = False
    def close(self):
        pass
    def execute(self, statement, params=None):
        sql = str(statement)
        if "pg_advisory_xact_lock" in sql:
            return Result()
        if "SELECT value_json, revision" in sql:
            return Result([{"value_json": deepcopy(self.store["payload"]), "revision": self.store["revision"]}])
        if "FROM employees" in sql:
            if "SELECT lower" in sql:
                return Result([{"role": "letan"}])
            return Result([{"username": "operator", "full_name": "Operator", "role": "letan"}])
        if "INSERT INTO vera_app_setting" in sql:
            self.store["payload"] = json.loads(params["payload"])
            self.store["revision"] += 1
            self.store["writes"] += 1
            return Result()
        raise AssertionError(sql)


def permission_client(payload=None):
    store = {"payload": deepcopy(payload or {}), "revision": 12, "writes": 0}
    engine = SimpleNamespace(connect=lambda: MemoryConnection(store))
    def mirror_unavailable():
        raise RuntimeError("offline test")
    app = FastAPI()
    install_permission_routes(app, engine_instance=lambda: engine,
        current_identity=lambda: identity("admin"), google_client=mirror_unavailable,
        identity_type=Identity, vn_tz=timezone.utc, feature_allowed=_feature_allowed)
    return TestClient(app), store


@pytest.mark.parametrize("scope,target", [("role", "letan"), ("account", "operator")])
def test_first_load_then_unchanged_save_preserves_effective_date_access(scope, target):
    client, store = permission_client()
    overview = client.get("/v2/permissions").json()
    assert overview["date_filter_policy_version"] == 1
    assert set(overview["date_filter_features"]) == set(DATE_FILTER_FEATURES)
    before = {key: _feature_allowed(None, identity(), key, store["payload"]) for key in FEATURES}
    response = client.put(f"/v2/permissions/{scope}/{target}", json={
        "allowed_features": [key for key, enabled in before.items() if enabled], "expected_revision": 12, "preserve_unchanged": True,
    })
    assert response.status_code == 200, response.text
    assert response.json()["date_filter_policy_version"] == 1
    assert store["payload"]["date_filter_policy_version"] == 1
    for key in DATE_FILTER_FEATURES:
        assert _feature_allowed(None, identity(), key, store["payload"]) == before[key]


def test_explicit_all_false_and_reset_account_follow_actual_role_date_defaults():
    date_keys = list(DATE_FILTER_FEATURES)
    role = [grant(feature, feature.endswith("_today"), "letan") for feature in date_keys]
    client, store = permission_client({"roles": role})
    allowed = [key for key in FEATURES if key not in DATE_FILTER_FEATURES and _feature_allowed(None, identity(), key, store["payload"])]
    response = client.put("/v2/permissions/account/operator", json={"allowed_features": allowed, "expected_revision": 12, "date_filter_policy_version": 1})
    assert response.status_code == 200, response.text
    assert not any(_feature_allowed(None, identity(), key, store["payload"]) for key in date_keys)
    response = client.put("/v2/permissions/account/operator", json={"inherit": True, "expected_revision": 13})
    assert response.status_code == 200, response.text
    assert store["payload"]["accounts"] == []
    for feature in date_keys:
        assert _feature_allowed(None, identity(), feature, store["payload"]) == (feature.endswith("_today") and section_read(feature, identity(), store["payload"]))


def test_stale_permission_revision_is_rejected_before_any_write():
    client, store = permission_client()
    response = client.put("/v2/permissions/role/letan", json={"allowed_features": [], "expected_revision": 11})
    assert response.status_code == 409
    assert store["writes"] == 0
    assert store["payload"] == {}


@pytest.mark.parametrize("scope,target", [("role", "letan"), ("account", "operator")])
def test_editor_save_preserves_existing_broader_denials_and_all_other_access(scope, target):
    payload = {"roles": [grant("live_tour_view", False, "letan"), grant("live_tour_reports_view", True, "letan"), grant("live_tour_payment", True, "letan")]}
    client, store = permission_client(payload)
    before = {key: _feature_allowed(None, identity(), key, store["payload"]) for key in FEATURES}
    response = client.put(f"/v2/permissions/{scope}/{target}", json={
        "allowed_features": [key for key, enabled in before.items() if enabled],
        "preserve_unchanged": True, "expected_revision": 12,
    })
    assert response.status_code == 200, response.text
    after = {key: _feature_allowed(None, identity(), key, store["payload"]) for key in FEATURES}
    assert after == before
    assert not after["live_tour_view"]
    assert after["live_tour_reports_date_custom"]


def test_editor_newly_enabled_permission_adds_parents_without_reenabling_date_denials():
    payload = {"accounts": [grant("live_tour_view", False), grant("live_tour_pending_view", False), grant("live_tour_pending_date_all", False)]}
    client, store = permission_client(payload)
    allowed = {key for key in FEATURES if _feature_allowed(None, identity(), key, payload)}
    allowed.add("live_tour_pending_date_today")
    response = client.put("/v2/permissions/account/operator", json={
        "allowed_features": sorted(allowed), "preserve_unchanged": True, "expected_revision": 12,
    })
    assert response.status_code == 200, response.text
    for parent in DATE_FILTER_DEPENDENCIES["live_tour_pending_date_today"]:
        assert _feature_allowed(None, identity(), parent, store["payload"])
    assert _feature_allowed(None, identity(), "live_tour_pending_date_today", store["payload"])
    assert not _feature_allowed(None, identity(), "live_tour_pending_date_all", store["payload"])


def test_editor_requires_revision_before_preserving_a_snapshot():
    client, store = permission_client()
    response = client.put("/v2/permissions/account/operator", json={"preserve_unchanged": True})
    assert response.status_code == 428
    assert store["writes"] == 0


def test_enabling_one_report_date_does_not_grant_board_or_other_date_presets():
    payload = {"accounts": [grant("live_tour_view", False), grant("live_tour_reports_view", True),
                            *[grant(f"live_tour_reports_date_{preset}", False) for preset in DATE_FILTER_PRESETS]]}
    client, store = permission_client(payload)
    allowed = {key for key in FEATURES if _feature_allowed(None, identity(), key, payload)}
    allowed.add("live_tour_reports_date_today")
    response = client.put("/v2/permissions/account/operator", json={
        "allowed_features": sorted(allowed), "preserve_unchanged": True, "expected_revision": 12,
    })
    assert response.status_code == 200, response.text
    assert not _feature_allowed(None, identity(), "live_tour_view", store["payload"])
    for preset in DATE_FILTER_PRESETS:
        assert _feature_allowed(None, identity(), f"live_tour_reports_date_{preset}", store["payload"]) == (preset == "today")


@pytest.mark.parametrize("scope,target,key", [("role", "letan", "roles"), ("account", "operator", "accounts")])
@pytest.mark.parametrize("existing", [None, False, True])
def test_pre_feature_tab_save_preserves_absent_or_explicit_date_rows(scope, target, key, existing):
    date_rows = [] if existing is None else [grant("live_tour_pending_date_today", existing, target)]
    payload = {key: deepcopy(date_rows)}
    client, store = permission_client(payload)
    allowed = [feature for feature in FEATURES if feature not in DATE_FILTER_FEATURES and _feature_allowed(None, identity(), feature, payload)]
    response = client.put(f"/v2/permissions/{scope}/{target}", json={"allowed_features": allowed, "expected_revision": 12})
    assert response.status_code == 200, response.text
    assert [row for row in store["payload"][key] if row["feature"] in DATE_FILTER_FEATURES] == date_rows


def test_new_editor_version_can_explicitly_disable_all_dates_without_any_date_id():
    client, store = permission_client()
    allowed = [key for key in FEATURES if key not in DATE_FILTER_FEATURES and _feature_allowed(None, identity(), key, {})]
    response = client.put("/v2/permissions/account/operator", json={
        "allowed_features": allowed, "expected_revision": 12, "date_filter_policy_version": 1, "preserve_unchanged": True,
    })
    assert response.status_code == 200, response.text
    rows = [row for row in store["payload"]["accounts"] if row["feature"] in DATE_FILTER_FEATURES]
    assert len(rows) == 32
    assert all(row["allowed"] is False for row in rows)


def test_unsupported_date_policy_version_cannot_modify_permissions():
    client, store = permission_client()
    response = client.put("/v2/permissions/account/operator", json={"expected_revision": 12, "date_filter_policy_version": 2})
    assert response.status_code == 422
    assert store["writes"] == 0


@pytest.mark.parametrize("section", ["pending", "invoices", "reports"])
@pytest.mark.parametrize("scope,target,key", [("role", "letan", "roles"), ("account", "operator", "accounts")])
def test_date_toggle_with_visible_minimal_parents_never_adds_hidden_broader_grants(section, scope, target, key):
    feature = f"live_tour_{section}_date_today"
    parents = DATE_FILTER_DEPENDENCIES[feature]
    payload = {key: [grant(parent, False, target) for parent in {*parents, "live_tour_view", "live_tour_payment"}]}
    client, store = permission_client(payload)
    allowed = {name for name in FEATURES if _feature_allowed(None, identity(), name, payload)}
    # Match the real editor: selecting the date visibly checks just its minimal
    # section read parents before the full allowed_features snapshot is sent.
    allowed.update({feature, *parents})
    response = client.put(f"/v2/permissions/{scope}/{target}", json={
        "allowed_features": sorted(allowed), "expected_revision": 12,
        "preserve_unchanged": True, "date_filter_policy_version": 1,
    })
    assert response.status_code == 200, response.text
    assert set(response.json()["allowed_features"]) == allowed
    saved = {row["feature"] for row in store["payload"][key] if row["target"] == target and row["allowed"]}
    assert saved == allowed
    assert _feature_allowed(None, identity(), feature, store["payload"])
    assert not _feature_allowed(None, identity(), "live_tour_view", store["payload"])
    assert not _feature_allowed(None, identity(), "live_tour_payment", store["payload"])

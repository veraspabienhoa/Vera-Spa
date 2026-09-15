from copy import deepcopy
from pathlib import Path

import vera_live_tour_relational as store


def state():
    return {
        "version": 1, "business_date": "2026-09-15", "bill_counters": {},
        "employees": [{"id": "e1", "name": "An"}, {"id": "e2", "name": "Bình"}],
        "rooms": [{"id": "r1", "name": "1.1"}], "services": [], "combos": [],
        "customers": [], "pending": [], "invoices": [], "reports": [],
        "combo_usage": [], "combo_sale_requests": [], "break_events": [],
        "audit": [], "backups": [], "pending_changes": [], "invoice_changes": [],
        "customer_changes": [],
    }


def test_split_has_independent_employee_and_room_resources():
    meta, resources = store._split(state())
    assert "employees" not in meta and "rooms" not in meta
    assert resources[("employees", "e1")][1]["name"] == "An"
    assert resources[("employees", "e2")][1]["name"] == "Bình"
    assert resources[("rooms", "r1")][1]["name"] == "1.1"


def test_diff_identifies_only_changed_resource():
    before = state()
    after = deepcopy(before)
    after["employees"][1]["name"] = "Bình mới"
    _, old = store._split(before)
    _, new = store._split(after)
    changed = [key for key, value in new.items() if old.get(key) != value]
    assert changed == [("employees", "e2")]


def test_resource_lock_order_is_canonical(monkeypatch):
    calls = []
    class Connection:
        def execute(self, _sql, params):
            calls.append(params["key"])
    keys = store.lock_resources(Connection(), [("rooms", "2"), ("employees", "b"), ("rooms", "1")])
    assert keys == sorted(keys)
    assert calls == keys


def test_schema_contains_room_uniqueness_and_idempotency():
    source = Path(store.__file__).read_text(encoding="utf-8")
    assert "room_key TEXT PRIMARY KEY" in source
    assert "idempotency_key TEXT PRIMARY KEY" in source
    assert "UNIQUE(employee_id, booking_id)" in source
    assert len(set(store.RESOURCE_TABLES.values())) == len(store.RESOURCE_COLLECTIONS)
    assert store.RESOURCE_TABLES["employees"] == "vera_live_tour_employee"
    assert store.RESOURCE_TABLES["invoices"] == "vera_live_tour_invoice"


def test_active_mode_is_never_selected_by_invalid_value(monkeypatch):
    monkeypatch.setenv("VERA_LIVE_TOUR_RELATIONAL_MODE", "unsafe")
    assert store.mode() == "shadow"

from pathlib import Path

import vera_resource_concurrency as concurrency


ROOT = Path(__file__).parents[1]


class Result:
    rowcount = 1

    def __init__(self, value=True):
        self.value = value

    def scalar(self):
        return self.value


class Connection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return Result()


def test_resource_locks_are_normalized_deduplicated_and_ordered():
    conn = Connection()
    keys = concurrency.lock_resources(conn, [
        ("Room", " 2 "), ("employee", "BÌNH"), ("room", "1"), ("Room", "2"),
    ])
    assert keys == sorted(set(keys))
    assert len(keys) == 3
    assert [params["key"] for _, params in conn.calls] == keys
    assert all("pg_advisory_xact_lock" in sql for sql, _ in conn.calls)
    assert concurrency.resource_key("employee", "Bình") == concurrency.resource_key("employee", "BINH")


def test_nonblocking_lock_fails_closed():
    conn = Connection()
    conn.execute = lambda statement, params=None: Result(False)
    try:
        concurrency.lock_resources(conn, [("invoice", "HD-1")], wait=False)
    except TimeoutError as exc:
        assert "resource busy" in str(exc)
    else:
        raise AssertionError("busy resource must not be treated as acquired")


def test_invalid_lock_mode_uses_safe_hybrid(monkeypatch):
    monkeypatch.setenv("VERA_RESOURCE_LOCK_MODE", "unsafe")
    assert concurrency.lock_mode() == "hybrid"


def test_schema_has_shared_idempotency_claim_revision_and_counter():
    source = (ROOT / "vera_resource_concurrency.py").read_text(encoding="utf-8")
    assert "PRIMARY KEY(scope, idempotency_key)" in source
    assert "PRIMARY KEY(domain, claim_key)" in source
    assert "PRIMARY KEY(domain, resource_id)" in source
    assert "PRIMARY KEY(scope, counter_key)" in source


def test_employee_and_leave_writes_use_scoped_transition_locks():
    staff = (ROOT / "vera_web_v2_staff.py").read_text(encoding="utf-8")
    security = (ROOT / "vera_web_v2_staff_security.py").read_text(encoding="utf-8")
    leave = (ROOT / "vera_web_v2_leave_sync_queue.py").read_text(encoding="utf-8")
    preview = (ROOT / "vera_web_v2_leave_preview.py").read_text(encoding="utf-8")
    assert '[("employee", username)]' in staff
    assert '[("employee", username)]' in security
    assert '[("leave_employee", body.employee_name)]' in leave
    assert '[("leave_employee", body.employee_name)]' in preview
    assert "next_counter(" in leave


def test_deploy_applies_and_verifies_concurrency_schema():
    workflow = (ROOT / ".github/workflows/deploy-vps.yml").read_text(encoding="utf-8")
    assert "vera_vps_concurrency_schema.py" in workflow
    assert "--apply --verify" in workflow

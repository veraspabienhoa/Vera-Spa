"""Read-only source visibility must never become a penalty execution path."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import vera_web_v2_auto_check as routes


NOW = datetime(2026, 10, 11, 0, 5, tzinfo=routes.attendance_source.VN_TZ)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz)


class ReadConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, *_args, **_kwargs):
        sql = str(statement)
        self.calls.append(sql)
        assert sql.startswith(("SET ", "SELECT ")), "Diagnostics attempted a business mutation"


class Engine:
    def __init__(self):
        self.conn = ReadConnection()
        self.checkouts = 0

    @contextmanager
    def begin(self):
        self.checkouts += 1
        yield self.conn


def forbidden(*_args, **_kwargs):
    raise AssertionError("Diagnostics attempted an unauthorized read or business write")


def client(engine, *, role="admin", require_feature=lambda *_: None):
    app = FastAPI()
    routes.install_auto_check_routes(app, engine_instance=lambda: engine,
        current_identity=lambda: SimpleNamespace(role=role, employee_username="test"),
        require_feature=require_feature, identity_type=SimpleNamespace)
    return TestClient(app)


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setattr(routes, "datetime", FixedDatetime)
    monkeypatch.setattr(routes.attendance_source, "source_for", lambda _: "facegate")
    monkeypatch.setattr(routes.attendance_source, "effective_date", lambda: date(2026, 9, 26))
    monkeypatch.setattr(routes.attendance_source, "health", lambda *_a, **_k: {
        "cache_fresh": True, "last_sync_at": NOW.isoformat(), "age_seconds": 0,
        "private_future_field": "never expose this",
    })
    # Lock out business entry points even if the endpoint is refactored later.
    for name in ("dashboard", "save_config", "save_violation", "ensure_schema"):
        monkeypatch.setattr(routes.core, name, forbidden)
    monkeypatch.setattr(routes.facegate_runtime, "publish", forbidden)
    monkeypatch.setattr(routes.facegate_runtime, "worker_frames", forbidden)
    return {
        "issues": [{"reason": "unmapped_reference", "username": "PRIVATE EMPLOYEE", "event_id": "PRIVATE EVENT"}],
        "events": [], "index": {}, "rows": [],
        "syncs": [{"work_date": day.isoformat(), "last_synced_at": NOW.isoformat(), "last_observed_count": 0}
                  for day in (NOW.date() - timedelta(days=1), NOW.date())],
    }


@pytest.mark.parametrize("role", ["nhanvien", "leader", "quanly", "letan", "", "unknown"])
def test_source_visibility_remains_admin_only_before_database_checkout(monkeypatch, role):
    engine = Engine()
    monkeypatch.setattr(routes.attendance_source, "health", forbidden)
    response = client(engine, role=role, require_feature=forbidden).get("/v2/auto-check/evidence")
    assert response.status_code == 403
    assert engine.checkouts == 0


def test_diagnostics_uses_single_readonly_snapshot_and_sanitized_two_day_report(monkeypatch, source):
    engine = Engine()
    reads = []
    grants = []

    def project(conn, start, end):
        assert conn is engine.conn
        reads.append((start, end))
        conn.execute(text("SELECT 'archived evidence only'"))
        return source

    monkeypatch.setattr(routes.facegate, "project_evidence", project)
    response = client(engine, require_feature=lambda conn, _ident, grant: grants.append((conn, grant))).get(
        "/v2/auto-check/evidence?start=1900-01-01&end=2999-12-31")
    assert response.status_code == 200
    report = response.json()
    assert engine.checkouts == 1
    assert engine.conn.calls[:3] == [
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
        "SET LOCAL statement_timeout='8s'", "SET LOCAL lock_timeout='2s'",
    ]
    assert grants == [(engine.conn, "auto_penalty")]
    assert reads == [(date(2026, 10, 10), date(2026, 10, 11))]
    assert report["checked_at"] == NOW.isoformat()
    assert report["evidence"]["global_issue_count"] == 1
    assert len(report["evidence"]["days"]) == 2
    assert all(day["archive_fresh"] for day in report["evidence"]["days"])
    assert "PRIVATE" not in response.text
    assert "private_future_field" not in response.text
    assert not any(key in response.text for key in ('"username"', '"event_id"', '"payload"'))


def test_first_cutover_day_does_not_project_legacy_day(monkeypatch, source):
    monkeypatch.setattr(routes.attendance_source, "effective_date", lambda: NOW.date())
    reads = []
    monkeypatch.setattr(routes.facegate, "project_evidence", lambda conn, start, end: reads.append((start, end)) or source)
    response = client(Engine()).get("/v2/auto-check/evidence")
    assert response.status_code == 200
    assert reads == [(NOW.date(), NOW.date())]
    assert len(response.json()["evidence"]["days"]) == 1


def test_legacy_source_never_projects_facegate_or_invokes_worker(monkeypatch, source):
    monkeypatch.setattr(routes.attendance_source, "source_for", lambda _: "timesoft")
    monkeypatch.setattr(routes.facegate, "project_evidence", forbidden)
    response = client(Engine()).get("/v2/auto-check/evidence")
    assert response.status_code == 200
    assert response.json()["source"] == "timesoft"
    assert response.json()["evidence"] is None


def test_existing_feature_and_password_checks_are_not_bypassed(monkeypatch, source):
    monkeypatch.setattr(routes.facegate, "project_evidence", forbidden)
    def deny(*_):
        raise HTTPException(428, "Password change required")
    response = client(Engine(), require_feature=deny).get("/v2/auto-check/evidence")
    assert response.status_code == 428


@pytest.mark.parametrize("error,status", [
    (routes.facegate.EvidenceError("PRIVATE bad event data"), 409),
    (RuntimeError("PRIVATE device configuration"), 409),
    (SQLAlchemyError("PRIVATE database parameters"), 503),
])
def test_failures_do_not_leak_evidence_or_sql(monkeypatch, source, error, status):
    def fail(*_):
        raise error
    monkeypatch.setattr(routes.facegate, "project_evidence", fail)
    response = client(Engine()).get("/v2/auto-check/evidence")
    assert response.status_code == status
    assert "PRIVATE" not in response.text


def test_postgres_readonly_transaction_rejects_accidental_business_write(monkeypatch, source):
    # Reuse the suite's isolated, single-connection PostgreSQL fixture when CI
    # supplies it; do not silently claim a mock proved database enforcement.
    import os
    from sqlalchemy import create_engine
    from uuid import uuid4
    url = os.getenv("VERA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Real PostgreSQL required")
    engine = create_engine(url, pool_size=1, max_overflow=0, pool_timeout=.05)
    table = "evidence_readonly_" + uuid4().hex
    try:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE TABLE {table}(amount integer)"))
            conn.execute(text(f"INSERT INTO {table} VALUES(123)"))
        def accidental_write(conn, *_):
            conn.execute(text(f"UPDATE {table} SET amount=0"))
            return source
        monkeypatch.setattr(routes.facegate, "project_evidence", accidental_write)
        response = client(engine).get("/v2/auto-check/evidence")
        assert response.status_code == 503
        with engine.connect() as conn:
            assert conn.execute(text(f"SELECT amount FROM {table}")).scalar_one() == 123
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        engine.dispose()

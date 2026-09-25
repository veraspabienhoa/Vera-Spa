"""Exercise scheduling against real PostgreSQL, independently of GitHub timers."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text

import vera_technical_retention as retention
from vera_web_v2_technical_retention import install_technical_retention_routes
from vera_postgres_job_queue import ensure_schema_conn
from test_live_tour_resource_postgres import database


def prepare(database):
    with database.begin() as conn:
        ensure_schema_conn(conn)
        retention.ensure_setting(conn)
        conn.execute(text("""INSERT INTO vera_background_job(queue_name,job_key,status,completed_at)
            VALUES('live_tour_projection','old','done',NOW()-INTERVAL '4 days')"""))


def config(database):
    with database.begin() as conn:
        return retention.read_setting(conn)


def test_upgrade_preserves_days_and_defaults_to_hourly(database):
    with database.begin() as conn:
        conn.execute(text(f'''CREATE TABLE {retention.SETTING_TABLE} (
            singleton smallint PRIMARY KEY,retention_days smallint NOT NULL,
            updated_at timestamptz DEFAULT NOW(),updated_by text DEFAULT 'system')'''))
        conn.execute(text(f'INSERT INTO {retention.SETTING_TABLE}(singleton,retention_days) VALUES(1,2)'))
        retention.ensure_setting(conn)
        retention.ensure_setting(conn)
    value = config(database)
    assert value['days'] == 2 and value['cleanup_interval_hours'] == 1
    assert value['due'] and value['last_cleanup_at'] is None


def test_scheduled_pass_skips_scans_until_due_and_dry_run_never_advances(database):
    prepare(database)
    assert retention.run(database)['eligible'] == 1
    assert config(database)['last_cleanup_at'] is None
    result = retention.run(database, apply=True, scheduled=True)
    assert result['removed'] == 1 and result['completed']
    before = config(database)
    assert before['last_cleanup_removed'] == 1 and not before['due']
    assert (before['next_cleanup_at']-before['last_cleanup_at']).total_seconds() == 3600
    statements = []
    def observe(conn, cursor, statement, params, context, executemany):
        statements.append(statement)
    event.listen(database, 'before_cursor_execute', observe)
    try:
        assert retention.run(database, apply=True, scheduled=True)['skipped'] == 'not_due'
    finally:
        event.remove(database, 'before_cursor_execute', observe)
    assert not any('vera_background_job' in statement for statement in statements)
    assert config(database)['last_cleanup_at'] == before['last_cleanup_at']


def test_admin_interval_changes_next_due_without_resetting_last_success(database):
    prepare(database)
    ident = SimpleNamespace(role='admin', employee_username='schedule-admin')
    app = FastAPI()
    install_technical_retention_routes(app, engine_instance=lambda: database, current_identity=lambda: ident)
    with TestClient(app) as client:
        assert client.get('/v2/settings/technical-retention').json()['cleanup_interval_hours'] == 1
        with database.begin() as conn:
            conn.execute(text(f"UPDATE {retention.SETTING_TABLE} SET last_cleanup_at=NOW()-INTERVAL '2 hours'"))
        response = client.put('/v2/settings/technical-retention', json={'days': 2, 'cleanup_interval_hours': 3})
        assert response.status_code == 200
        before = response.json()['last_cleanup_at']
        assert retention.run(database, True, scheduled=True)['skipped'] == 'not_due'
        # Older tabs saving only days must not silently reset the chosen interval.
        assert client.put('/v2/settings/technical-retention', json={'days': 3}).json()['cleanup_interval_hours'] == 3
        response = client.put('/v2/settings/technical-retention', json={'days': 2, 'cleanup_interval_hours': 1})
        assert response.json()['last_cleanup_at'] == before
        assert retention.run(database, True, scheduled=True)['removed'] == 1
        result = client.get('/v2/settings/technical-retention').json()
        assert result['last_cleanup_removed'] == 1 and result['last_cleanup_at'] != before


def test_simultaneous_runner_is_skipped_even_when_due(database):
    prepare(database)
    with database.connect() as other:
        other.execute(text('SELECT pg_advisory_lock(:key)'), {'key': retention.CLEANUP_LOCK})
        other.commit()
        try:
            assert retention.run(database, True, scheduled=True)['skipped'] == 'already_running'
            assert config(database)['last_cleanup_at'] is None
        finally:
            other.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': retention.CLEANUP_LOCK})
            other.commit()
    assert retention.run(database, True, scheduled=True)['removed'] == 1


def test_failure_releases_lock_and_keeps_schedule_due(database, monkeypatch):
    prepare(database)
    with monkeypatch.context() as patch:
        patch.setattr(retention, 'PRUNE', text('SELECT 1/0'))
        with pytest.raises(Exception):
            retention.run(database, True, scheduled=True)
    assert config(database)['last_cleanup_at'] is None
    assert retention.run(database, True, scheduled=True)['removed'] == 1


def test_incomplete_budget_is_retried_without_waiting_full_interval(database, monkeypatch):
    prepare(database)
    with monkeypatch.context() as patch:
        clock = iter([0, 21])
        patch.setattr(retention, 'monotonic', lambda: next(clock))
        assert not retention.run(database, True, scheduled=True)['completed']
    assert config(database)['last_cleanup_at'] is None
    assert retention.run(database, True, scheduled=True)['removed'] == 1


@pytest.mark.parametrize('role', ['letan', 'quanly', 'nhanvien', ''])
def test_non_admin_cannot_read_or_change_cleanup_schedule(role):
    def unexpected_db():
        raise AssertionError('Unauthorized request must not access the database')
    app = FastAPI()
    install_technical_retention_routes(app, engine_instance=unexpected_db,
        current_identity=lambda: SimpleNamespace(role=role))
    with TestClient(app) as client:
        assert client.get('/v2/settings/technical-retention').status_code == 403
        assert client.put('/v2/settings/technical-retention', json={'days': 2, 'cleanup_interval_hours': 1}).status_code == 403


@pytest.mark.parametrize('hours', [0, -1, 169, 1.5, True, '2'])
def test_invalid_interval_is_rejected_before_database_access(hours):
    def unexpected_db():
        raise AssertionError('Invalid request must not access the database')
    app = FastAPI()
    install_technical_retention_routes(app, engine_instance=unexpected_db,
        current_identity=lambda: SimpleNamespace(role='admin'))
    with TestClient(app) as client:
        assert client.put('/v2/settings/technical-retention', json={'days': 2, 'cleanup_interval_hours': hours}).status_code == 422

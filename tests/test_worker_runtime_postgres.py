"""Synthetic PostgreSQL coverage for split-role readiness and durable failover."""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import contextmanager
import multiprocessing
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

import vera_worker_runtime as workers
import vera_web_v2_leave_sync_queue as leave_queue
import vera_postgres_job_queue as queue


@pytest.fixture(autouse=True)
def synthetic_direct_connection(monkeypatch):
    monkeypatch.setenv('VERA_WORKER_DB_MODE', 'direct')


@pytest.fixture
def database():
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('VERA_TEST_POSTGRES_URL is required')
    schema = 'worker_test_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    engine.test_schema = schema
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
    admin.dispose()


def runtime(database, role, monkeypatch):
    monkeypatch.setenv('VERA_SERVICE_ROLE', role)
    result = workers.WorkerRuntime(lambda: database)
    result.register('synthetic', lambda stop: stop.wait(300), stale_after=400)
    return result


def test_api_split_is_not_ready_without_fresh_complete_worker(database, monkeypatch):
    api = runtime(database, 'api', monkeypatch)
    api.start()
    assert api.health()['ok']
    assert api.readiness() == {'ok': False, 'role': 'api', 'state': 'api', 'workers_ready': False, 'session_affinity_confirmed': True}
    worker = runtime(database, 'worker', monkeypatch)
    worker.start()
    try:
        assert worker.readiness()['ok']
        assert api.readiness()['ok']
        with database.begin() as conn:
            conn.execute(text(f"UPDATE {workers.TABLE} SET heartbeat_at=NOW()-INTERVAL '31 seconds'"))
        assert not api.readiness()['ok']
        worker.heartbeat()
        assert api.readiness()['ok']
        with database.begin() as conn:
            conn.execute(text(f"UPDATE {workers.TABLE} SET workers='[]'::jsonb"))
        assert not api.readiness()['ok']
        worker.heartbeat()
    finally:
        worker.stop()
        api.stop()
    with database.connect() as conn:
        assert conn.execute(text(f'SELECT state FROM {workers.TABLE}')).scalar_one() == 'stopped'


def test_default_combined_bootstraps_schema_and_keeps_jobs_running(database, monkeypatch):
    monkeypatch.delenv('VERA_SERVICE_ROLE', raising=False)
    app = workers.WorkerRuntime(lambda: database)
    app.register('synthetic', lambda stop: stop.wait(300), stale_after=400)
    app.start()
    try:
        assert app.role == 'combined'
        assert app.readiness()['ok']
    finally:
        app.stop()


def test_stopping_one_replica_preserves_another_replica_readiness(database, monkeypatch):
    one = runtime(database, 'worker', monkeypatch)
    two = runtime(database, 'worker', monkeypatch)
    one.start()
    two.start()
    one.stop()
    try:
        assert two.readiness()['ok']
        with database.connect() as conn:
            rows = conn.execute(text(f'SELECT state FROM {workers.TABLE}')).scalars().all()
        assert sorted(rows) == ['running', 'stopped']
    finally:
        two.stop()


def test_stalled_worker_cannot_refresh_a_healthy_readiness_heartbeat(database, monkeypatch):
    worker = runtime(database, 'worker', monkeypatch)
    worker.start()
    try:
        worker.workers['synthetic'].stop.progress_at -= 1000
        worker.heartbeat()
        assert not worker.readiness()['ok']
        with database.connect() as conn:
            assert conn.execute(text(f'SELECT state FROM {workers.TABLE}')).scalar_one() == 'degraded'
    finally:
        worker.stop()


def seed_leave(database):
    leave_queue._ensure_schema(lambda: database)
    with database.begin() as conn:
        conn.execute(text(f"""INSERT INTO {leave_queue.QUEUE_TABLE}
            (idempotency_key,record_uid,source_row) VALUES('one','synthetic-record',2)"""))


def _claim_in_process(url, schema, kind):
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    try:
        if kind == 'leave':
            return leave_queue._claim_one(lambda: engine)
        return queue.claim_one(lambda: engine, 'synthetic')
    finally:
        engine.dispose()


@pytest.mark.parametrize('kind', ['leave', 'projection'])
def test_multiple_processes_claim_one_committed_job_once(database, kind):
    if kind == 'leave':
        seed_leave(database)
    else:
        queue.ensure_schema(lambda: database)
        with ThreadPoolExecutor(max_workers=4) as executor:
            inserted = list(executor.map(lambda _: queue.enqueue(lambda: database, 'synthetic', 'same-bucket'), range(8)))
        assert sum(inserted) == 1
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) as executor:
        claims = list(executor.map(_claim_in_process,
            [os.environ['VERA_TEST_POSTGRES_URL']]*4, [database.test_schema]*4, [kind]*4))
    assert len([item for item in claims if item]) == 1


def test_leave_expired_claim_retries_and_stale_owner_cannot_finish_or_release(database):
    seed_leave(database)
    first = leave_queue._claim_one(lambda: database)
    assert leave_queue._claim_one(lambda: database) is None
    with database.begin() as conn:
        conn.execute(text(f"UPDATE {leave_queue.QUEUE_TABLE} SET locked_at=NOW()-INTERVAL '11 minutes'"))
    current = leave_queue._claim_one(lambda: database)
    assert current['id'] == first['id'] and current['locked_at'] != first['locked_at']
    assert not leave_queue._lease_current(lambda: database, first)
    leave_queue._mark_done(lambda: database, first)
    leave_queue._mark_retry(lambda: database, first, RuntimeError('stale secret'))
    with database.connect() as conn:
        row = conn.execute(text(f'SELECT * FROM {leave_queue.QUEUE_TABLE}')).mappings().one()
        assert row['status'] == 'processing' and row['locked_at'] == current['locked_at']
        assert row['attempts'] == 0
    leave_queue._mark_done(lambda: database, current)
    assert leave_queue._claim_one(lambda: database) is None


def test_leave_retry_does_not_store_sensitive_exception_text(database):
    seed_leave(database)
    current = leave_queue._claim_one(lambda: database)
    leave_queue._mark_retry(lambda: database, current, RuntimeError('secret text'))
    with database.connect() as conn:
        row = conn.execute(text(f'SELECT * FROM {leave_queue.QUEUE_TABLE}')).mappings().one()
        assert row['status'] == 'retry' and row['last_error'] == 'RuntimeError'


def test_leave_mirror_releases_connection_before_all_network_calls(database, monkeypatch):
    seed_leave(database)
    record = {'record_uid':'synthetic-record', 'source_row':2, 'leave_type':'normal'}
    monkeypatch.setattr(leave_queue, '_record_for_uid', lambda *_: record)
    calls = []
    class Sheet:
        def get_all_values(self):
            assert database.pool.checkedout() == 0
            return [['Loại nghỉ']]
        def update(self, **kwargs):
            assert database.pool.checkedout() == 0
            calls.append(kwargs)
    sheet = Sheet()
    class Client:
        def open_by_key(self, key):
            assert database.pool.checkedout() == 0
            return self
        def worksheet(self, name):
            assert database.pool.checkedout() == 0
            return sheet
    @contextmanager
    def mirror_client(_api):
        yield Client()
    monkeypatch.setattr(leave_queue, '_mirror_client', mirror_client)
    api = SimpleNamespace(LEAVE_SHEET_ID='synthetic-sheet', _google_client=lambda: Client(),
                          _norm=lambda value: value, _sheet_values_for_record=lambda *args:['normal'])
    assert leave_queue._process_one(engine_instance=lambda: database, api_module=api)
    assert calls == [{'range_name':'A2:M2','values':[['normal']], 'value_input_option':'USER_ENTERED'}]
    assert not leave_queue._process_one(engine_instance=lambda: database, api_module=api)


def test_delayed_heartbeat_cannot_restore_readiness_after_draining(database, monkeypatch):
    worker = runtime(database, 'worker', monkeypatch)
    worker.start()
    try:
        worker.state = 'draining'
        worker.heartbeat()
        worker.state = 'running'  # Simulate a pre-shutdown heartbeat finishing late.
        worker.heartbeat()
        assert not worker.readiness()['ok']
        with database.connect() as conn:
            assert conn.execute(text(f'SELECT state FROM {workers.TABLE}')).scalar_one() == 'draining'
    finally:
        worker.stop()


def test_unverified_combined_keeps_jobs_but_new_split_readiness_fails_closed(database, monkeypatch):
    monkeypatch.delenv('VERA_WORKER_DB_MODE', raising=False)
    combined = runtime(database, 'combined', monkeypatch)
    combined.start()
    try:
        assert combined.health()['ok']
        assert combined.workers['synthetic'].thread.is_alive()
        assert not combined.readiness()['ok']
        assert not combined.readiness()['session_affinity_confirmed']
        with database.connect() as conn:
            assert conn.execute(text(f'SELECT state FROM {workers.TABLE}')).scalar_one() == 'database_unverified'
    finally:
        combined.stop()


def test_leave_near_expiry_renewal_commits_before_outbound_and_fences_old_owner(database):
    seed_leave(database)
    old = leave_queue._claim_one(lambda: database)
    with database.begin() as conn:
        near_expiry = conn.execute(text(f"""UPDATE {leave_queue.QUEUE_TABLE}
            SET locked_at=NOW()-INTERVAL '599 seconds' RETURNING locked_at""")).scalar_one()
    current = {**old, 'locked_at': near_expiry}
    assert leave_queue._renew_claim(lambda: database, current)
    assert current['locked_at'] != near_expiry
    assert leave_queue._claim_one(lambda: database) is None
    assert not leave_queue._renew_claim(lambda: database, old)
    with database.connect() as conn:
        assert conn.execute(text(f'SELECT EXTRACT(EPOCH FROM clock_timestamp()-locked_at)<2 FROM {leave_queue.QUEUE_TABLE}')).scalar_one()


def test_leave_recovered_owner_prevents_stale_worker_from_opening_remote_client(database, monkeypatch):
    seed_leave(database)
    old = leave_queue._claim_one(lambda: database)
    with database.begin() as conn:
        conn.execute(text(f"UPDATE {leave_queue.QUEUE_TABLE} SET locked_at=NOW()-INTERVAL '11 minutes'"))
    recovered = leave_queue._claim_one(lambda: database)
    monkeypatch.setattr(leave_queue, '_claim_one', lambda _: old)
    monkeypatch.setattr(leave_queue, '_record_for_uid', lambda *_: {'source_row':2})
    monkeypatch.setattr(leave_queue, '_mirror_client', lambda _: pytest.fail('stale owner must not open remote client'))
    assert leave_queue._process_one(engine_instance=lambda: database, api_module=object())
    assert leave_queue._lease_current(lambda: database, recovered)


def test_api_only_may_use_different_route_when_verified_worker_is_healthy(database, monkeypatch):
    worker = runtime(database, 'worker', monkeypatch)
    worker.start()
    # Freeze the already committed worker heartbeat: actual services have
    # separate environments, unlike these two fixture runtimes in one process.
    worker.monitor_stop.set()
    worker.monitor_thread.join(1)
    monkeypatch.setenv('VERA_WORKER_DB_MODE', 'transaction')
    api = runtime(database, 'api', monkeypatch)
    api.start()
    try:
        result = api.readiness()
        assert result['ok'] and result['workers_ready']
        assert not result['session_affinity_confirmed']
    finally:
        api.stop()
        worker.stop()

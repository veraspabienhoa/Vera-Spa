"""Supervise existing in-process jobs, with an explicit opt-in API/worker split.

There is no long-lived coordination connection or global worker lock. Producers
retain their short transaction locks/deduplication keys; consumers retain their
committed, fenced queue claims. Network I/O never runs in heartbeat transactions.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
import logging
import os
from threading import Event, Thread
from time import monotonic
from uuid import uuid4

import anyio
from fastapi.responses import JSONResponse
from sqlalchemy import text

TABLE = 'vera_worker_runtime'
HEARTBEAT_SECONDS = 5
FRESH_SECONDS = 30
SHUTDOWN_SECONDS = 30
ROLES = frozenset({'combined', 'api', 'worker'})
EXPECTED_WORKERS = frozenset({
    'live-tour-projection-scheduler', 'live-tour-projection-worker',
    'live-tour-queue-alert-monitor', 'vera-leave-sheet-sync',
    'leave-quota-monitor', 'vera-notification-delivery', 'technical-retention-monitor',
})
LOG = logging.getLogger(__name__)


def service_role() -> str:
    role = os.environ.get('VERA_SERVICE_ROLE', 'combined').strip().lower()
    if role not in ROLES:
        raise ValueError('VERA_SERVICE_ROLE must be combined, api or worker')
    return role


def database_mode() -> str:
    """An operator declaration, never inferred from hostname/port or one query."""
    mode = os.environ.get('VERA_WORKER_DB_MODE', 'unknown').strip().lower()
    if mode not in {'unknown', 'direct', 'session', 'transaction'}:
        raise ValueError('VERA_WORKER_DB_MODE must be direct, session, transaction or unknown')
    return mode


def session_affinity_confirmed() -> bool:
    return database_mode() in {'direct', 'session'}


def ensure_schema_conn(conn):
    # Startup fallback preserves combined mode even before a schema-gate upgrade.
    # Recheck under the transaction lock to serialize simultaneous first starts.
    if conn.execute(text('SELECT to_regclass(:table)'), {'table': TABLE}).scalar():
        return
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera.worker.runtime.schema'))"))
    if conn.execute(text('SELECT to_regclass(:table)'), {'table': TABLE}).scalar():
        return
    conn.execute(text(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
        instance_id UUID PRIMARY KEY, role TEXT NOT NULL,
        state TEXT NOT NULL, workers JSONB NOT NULL DEFAULT '[]'::jsonb,
        started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    );
    ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;
    REVOKE ALL ON {TABLE} FROM PUBLIC;
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON {TABLE} FROM anon;
      END IF;
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON {TABLE} FROM authenticated;
      END IF;
    END $$;'''))


class ProgressEvent(Event):
    """A stop event whose interruptible waits also report loop responsiveness."""
    def __init__(self):
        super().__init__()
        self.progress_at = monotonic()

    def wait(self, timeout=None):
        self.progress_at = monotonic()
        result = super().wait(timeout)
        self.progress_at = monotonic()
        return result


@dataclass
class Worker:
    name: str
    target: object
    prepare: object = None
    stale_after: float = 300
    stop: ProgressEvent | None = None
    thread: Thread | None = None
    failed: bool = False

    def healthy(self):
        return bool(self.thread and self.thread.is_alive() and not self.failed
                    and monotonic() - self.stop.progress_at <= self.stale_after)


class WorkerRuntime:
    def __init__(self, engine_instance):
        self.engine_instance = engine_instance
        self.role = service_role()
        self.workers: dict[str, Worker] = {}
        self.instance_id = str(uuid4())
        self.state = 'stopped'
        self.monitor_stop = Event()
        self.monitor_thread = None

    def register(self, name, target, *, prepare=None, stale_after=300):
        if self.state != 'stopped':
            raise RuntimeError('Cannot register a worker after startup')
        if name in self.workers:
            raise ValueError('Duplicate worker registration')
        self.workers[name] = Worker(name, target, prepare, stale_after)

    def _run(self, worker):
        try:
            worker.target(worker.stop)
        except Exception as exc:
            worker.failed = True
            # Never include exception messages, SQL, employee data or credentials.
            LOG.error('Background worker %s stopped: %s', worker.name, type(exc).__name__)
        finally:
            if not worker.stop.is_set():
                worker.failed = True

    def heartbeat(self):
        state = self.state
        if state == 'running' and not session_affinity_confirmed():
            state = 'database_unverified'
        elif state == 'running' and not all(w.healthy() for w in self.workers.values()):
            state = 'degraded'
        with self.engine_instance().begin() as conn:
            conn.execute(text("SET LOCAL statement_timeout='2s'"))
            conn.execute(text("SET LOCAL lock_timeout='200ms'"))
            conn.execute(text(f'''INSERT INTO {TABLE}(instance_id,role,state,workers)
                VALUES(CAST(:id AS uuid),:role,:state,CAST(:workers AS jsonb))
                ON CONFLICT(instance_id) DO UPDATE SET state=CASE
                WHEN {TABLE}.state IN ('draining','stopped','drain_timeout')
                     AND EXCLUDED.state IN ('running','degraded','database_unverified')
                THEN {TABLE}.state ELSE EXCLUDED.state END,
                workers=EXCLUDED.workers,heartbeat_at=clock_timestamp()'''),
                {'id': self.instance_id, 'role': self.role, 'state': state,
                 'workers': json.dumps(sorted(self.workers))})

    def _monitor(self):
        while not self.monitor_stop.wait(HEARTBEAT_SECONDS):
            try:
                self.heartbeat()
            except Exception as exc:
                LOG.warning('Background worker heartbeat deferred: %s', type(exc).__name__)

    def start(self):
        if self.state != 'stopped':
            raise RuntimeError('Worker runtime is already started')
        self.role = service_role()
        mode = database_mode()
        if self.role == 'worker' and mode not in {'direct', 'session'}:
            raise RuntimeError('Worker split requires verified direct or session-affine PostgreSQL; set VERA_WORKER_DB_MODE after verification')
        if self.role == 'combined' and mode not in {'direct', 'session'}:
            LOG.warning('Existing combined jobs retained; worker split readiness requires verified session-affine PostgreSQL')
        self.instance_id = str(uuid4())
        with self.engine_instance().begin() as conn:
            ensure_schema_conn(conn)
            conn.execute(text(f"DELETE FROM {TABLE} WHERE heartbeat_at < NOW()-INTERVAL '1 day'"))
        # Both roles serve writes/queue health, so initialize their queue schema.
        # No thread starts until every prerequisite has passed.
        for worker in self.workers.values():
            if worker.prepare:
                worker.prepare()
        if self.role == 'api':
            self.state = 'api'
            return
        if not self.workers:
            raise RuntimeError('Worker role has no registered workers')
        self.state = 'starting'
        try:
            for worker in self.workers.values():
                worker.stop = ProgressEvent()
                worker.failed = False
                worker.thread = Thread(target=self._run, args=(worker,), name=worker.name, daemon=True)
                worker.thread.start()
            self.state = 'running'
            self.heartbeat()
            self.monitor_stop.clear()
            self.monitor_thread = Thread(target=self._monitor, name='vera-worker-heartbeat', daemon=True)
            self.monitor_thread.start()
        except BaseException:
            self.stop()
            raise

    def stop(self, *, timeout=SHUTDOWN_SECONDS):
        if self.state == 'stopped':
            return True
        self.state = 'draining'
        # Stop all loops together before joining, with one total drain deadline.
        self.monitor_stop.set()
        for worker in self.workers.values():
            if worker.stop:
                worker.stop.set()
        deadline = monotonic() + timeout
        if self.monitor_thread:
            self.monitor_thread.join(max(0, deadline-monotonic()))
        try:
            if self.role != 'api':
                self.heartbeat()
        except Exception as exc:
            LOG.warning('Background drain heartbeat deferred: %s', type(exc).__name__)
        for worker in self.workers.values():
            if worker.thread:
                worker.thread.join(max(0, deadline-monotonic()))
        drained = all(not w.thread or not w.thread.is_alive() for w in self.workers.values())
        self.state = 'stopped' if drained else 'drain_timeout'
        # Never release/reassign queue claims here. The owner finishes them, or
        # their existing lease expires after process exit and another worker retries.
        try:
            if self.role != 'api':
                self.heartbeat()
        except Exception as exc:
            LOG.warning('Background stop heartbeat deferred: %s', type(exc).__name__)
        if not drained:
            LOG.error('Background worker drain timed out; durable claims remain recoverable')
        return drained

    def health(self):
        local_ok = self.state in {'api', 'running'}
        if self.role != 'api':
            local_ok = local_ok and all(w.healthy() for w in self.workers.values())
            local_ok = local_ok and bool(self.monitor_thread and self.monitor_thread.is_alive())
        return {'ok': bool(local_ok), 'role': self.role, 'state': self.state}

    def readiness(self):
        local = self.health()
        with self.engine_instance().begin() as conn:
            conn.execute(text("SET LOCAL statement_timeout='2s'"))
            conn.execute(text("SET LOCAL lock_timeout='200ms'"))
            ready = bool(conn.execute(text(f'''SELECT EXISTS(
                SELECT 1 FROM {TABLE} WHERE role IN ('combined','worker')
                AND state='running' AND heartbeat_at >= clock_timestamp()-(:fresh*INTERVAL '1 second')
                AND workers @> CAST(:workers AS jsonb))'''),
                {'fresh': FRESH_SECONDS, 'workers': json.dumps(sorted(self.workers))}).scalar())
        compatible = session_affinity_confirmed()
        return {**local, 'ok': local['ok'] and ready and (self.role == 'api' or compatible), 'workers_ready': ready,
                'session_affinity_confirmed': compatible}


def runtime_for(app, engine_instance):
    runtime = getattr(app.state, 'worker_runtime', None)
    if runtime is not None:
        return runtime
    runtime = WorkerRuntime(engine_instance)
    app.state.worker_runtime = runtime
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application) as state:
            await anyio.to_thread.run_sync(runtime.start)
            try:
                yield state
            finally:
                await anyio.to_thread.run_sync(runtime.stop)

    app.router.lifespan_context = lifespan
    return runtime


def register_worker(app, *, engine_instance, name, target, prepare=None, stale_after=300):
    runtime_for(app, engine_instance).register(name, target, prepare=prepare, stale_after=stale_after)


def install_health_routes(app, runtime):
    @app.get('/v2/runtime/health')
    def runtime_health():
        payload = runtime.health()
        return JSONResponse(payload, status_code=200 if payload['ok'] else 503)

    @app.get('/v2/runtime/ready')
    def runtime_ready():
        try:
            payload = runtime.readiness()
        except Exception:
            payload = {'ok': False, 'role': runtime.role, 'workers_ready': False}
        return JSONResponse(payload, status_code=200 if payload['ok'] else 503)


def require_complete_registration(runtime):
    if set(runtime.workers) != EXPECTED_WORKERS:
        raise RuntimeError('Web V2 background worker registration is incomplete')

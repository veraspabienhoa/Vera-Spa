"""Runtime role/lifecycle checks do not import the credential-bearing API."""
from contextlib import asynccontextmanager
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock
import runpy
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_worker_runtime as workers


@pytest.fixture(autouse=True)
def synthetic_direct_connection(monkeypatch):
    monkeypatch.setenv('VERA_WORKER_DB_MODE', 'direct')


def fake_engine():
    return MagicMock()


def test_combined_is_compatible_default_and_bad_roles_fail_closed(monkeypatch):
    monkeypatch.delenv('VERA_SERVICE_ROLE', raising=False)
    assert workers.service_role() == 'combined'
    for role in ('api', 'worker', 'combined'):
        monkeypatch.setenv('VERA_SERVICE_ROLE', role)
        assert workers.service_role() == role
    monkeypatch.setenv('VERA_SERVICE_ROLE', 'ap1')
    with pytest.raises(ValueError):
        workers.service_role()


@pytest.mark.parametrize('role,expected', [('api', False), ('combined', True), ('worker', True)])
def test_registration_never_starts_at_import_and_lifespan_obeys_role(monkeypatch, role, expected):
    monkeypatch.setenv('VERA_SERVICE_ROLE', role)
    events, running = [], Event()
    @asynccontextmanager
    async def previous(app):
        events.append('previous-start')
        yield {'shared': 'preserved'}
        events.append('previous-stop')
    def work(stop):
        events.append('worker-start')
        running.set()
        stop.wait(10)
        events.append('worker-stop')
    app = FastAPI(lifespan=previous)
    workers.register_worker(app, engine_instance=fake_engine, name='synthetic', target=work,
                            prepare=lambda: events.append('prepared'))
    runtime = app.state.worker_runtime
    monkeypatch.setattr(runtime, 'heartbeat', lambda: None)
    assert not running.is_set()
    with TestClient(app):
        assert running.is_set() is expected
        assert runtime.health()['ok']
    assert runtime.state == 'stopped'
    assert events == (['previous-start', 'prepared', 'worker-start', 'worker-stop', 'previous-stop']
                      if expected else ['previous-start', 'prepared', 'previous-stop'])


def test_prerequisite_failure_starts_no_partial_workers(monkeypatch):
    monkeypatch.setenv('VERA_SERVICE_ROLE', 'combined')
    runtime = workers.WorkerRuntime(fake_engine)
    ran = []
    runtime.register('first', lambda stop: ran.append(True))
    def fail(): raise RuntimeError('missing prerequisite')
    runtime.register('second', lambda stop: None, prepare=fail)
    with pytest.raises(RuntimeError): runtime.start()
    assert ran == []


def test_worker_exception_and_stall_fail_local_health(monkeypatch):
    monkeypatch.setenv('VERA_SERVICE_ROLE', 'worker')
    runtime = workers.WorkerRuntime(fake_engine)
    crashed = Event()
    def fail(stop):
        crashed.set()
        raise RuntimeError('DO NOT LOG synthetic secret')
    runtime.register('crashed', fail)
    monkeypatch.setattr(runtime, 'heartbeat', lambda: None)
    runtime.start()
    assert crashed.wait(1)
    runtime.workers['crashed'].thread.join(1)
    assert not runtime.health()['ok']
    runtime.stop()
    stop = workers.ProgressEvent()
    thread = MagicMock(is_alive=lambda: True)
    item = workers.Worker('stalled', None, stale_after=1, stop=stop, thread=thread)
    stop.progress_at -= 2
    assert not item.healthy()
    stop.wait(0)
    assert item.healthy()


def test_bounded_shutdown_does_not_clear_an_inflight_claim(monkeypatch):
    monkeypatch.setenv('VERA_SERVICE_ROLE', 'worker')
    runtime = workers.WorkerRuntime(fake_engine)
    entered, release = Event(), Event()
    def blocked(stop):
        entered.set()
        release.wait(5)
    runtime.register('blocked', blocked)
    monkeypatch.setattr(runtime, 'heartbeat', lambda: None)
    runtime.start()
    assert entered.wait(1)
    assert runtime.stop(timeout=.01) is False
    assert runtime.state == 'drain_timeout'
    assert not runtime.health()['ok']
    release.set()
    runtime.workers['blocked'].thread.join(1)
    assert runtime.stop(timeout=1) is True


def test_worker_entrypoint_exposes_only_health_and_lifespan(monkeypatch):
    monkeypatch.setenv('VERA_SERVICE_ROLE', 'worker')
    app = FastAPI()
    app.state.worker_runtime = SimpleNamespace(
        health=lambda: {'ok': True, 'role': 'worker'},
        readiness=lambda: {'ok': True, 'role': 'worker'})
    monkeypatch.setitem(sys.modules, 'vera_web_v2_api_v38', SimpleNamespace(app=app))
    scope = runpy.run_path(str(Path(__file__).parents[1] / 'vera_web_v2_worker.py'))
    with TestClient(scope['app']) as client:
        assert client.get('/v2/runtime/health').status_code == 200
        assert client.get('/v2/runtime/ready').status_code == 200
        assert client.get('/v2/live-tour').status_code == 404
        assert client.get('/v2/auth/health').status_code == 404
        assert client.get('/openapi.json').status_code == 404
    monkeypatch.setenv('VERA_SERVICE_ROLE', 'api')
    with pytest.raises(RuntimeError):
        runpy.run_path(str(Path(__file__).parents[1] / 'vera_web_v2_worker.py'))


def test_role_health_does_not_replace_business_or_auth_health():
    source = (Path(__file__).parents[1] / 'vera_web_v2_api_v38.py').read_text()
    assert 'install_health_routes(app, runtime_for(app, _api._engine_instance))' in source
    assert 'install_auth_gateway(' in source


def test_no_ad_hoc_background_thread_or_import_start_remains():
    root = Path(__file__).parents[1]
    for name in ('vera_web_v2_live_tour.py', 'vera_web_v2_leave_sync_queue.py',
                 'vera_leave_quota_alerts.py', 'vera_web_v2_notification_settings.py',
                 'vera_technical_retention_scheduler.py'):
        source = (root / name).read_text()
        assert 'Thread(' not in source
        assert 'register_worker(' in source


def test_full_runtime_requires_the_complete_existing_job_inventory():
    import ast
    root = Path(__file__).parents[1]
    names = set()
    for filename in ('vera_web_v2_live_tour.py', 'vera_web_v2_leave_sync_queue.py',
                     'vera_leave_quota_alerts.py', 'vera_web_v2_notification_settings.py',
                     'vera_technical_retention_scheduler.py'):
        tree = ast.parse((root / filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'register_worker':
                names.update(kw.value.value for kw in node.keywords if kw.arg == 'name')
    assert names == workers.EXPECTED_WORKERS
    with pytest.raises(RuntimeError):
        workers.require_complete_registration(SimpleNamespace(workers={}))
    workers.require_complete_registration(SimpleNamespace(workers=dict.fromkeys(names)))


@pytest.mark.parametrize('mode', ['unknown', 'transaction'])
def test_worker_role_requires_operator_verified_session_affinity(monkeypatch, mode):
    monkeypatch.setenv('VERA_SERVICE_ROLE', 'worker')
    monkeypatch.setenv('VERA_WORKER_DB_MODE', mode)
    runtime = workers.WorkerRuntime(lambda: pytest.fail('reject before opening database'))
    runtime.register('synthetic', lambda stop: None)
    with pytest.raises(RuntimeError, match='verified direct or session-affine'):
        runtime.start()


@pytest.mark.parametrize('mode', ['direct', 'session', 'unknown', 'transaction', 'invalid'])
def test_worker_db_mode_managed_allowlist_and_process_precedence(monkeypatch, mode):
    import vera_web_v2_runtime_env as managed
    values = dict(VERA_DB_ENABLED='1', VERA_DATA_BACKEND='postgres', DB_HOST='synthetic',
                  DB_PORT='5432', DB_NAME='synthetic', DB_USER='synthetic', DB_PASS='synthetic',
                  DB_SSLMODE='require', DB_CONNECT_TIMEOUT='5', VERA_AUTH_PROVIDER='local',
                  VERA_SERVICE_ROLE='combined', VERA_WORKER_DB_MODE='transaction')
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(managed, '_read_private_file', lambda path: '\n'.join(f'{k}={v}' for k,v in values.items()))
    monkeypatch.setenv('VERA_WORKER_DB_MODE', mode)
    if mode == 'invalid':
        with pytest.raises(RuntimeError, match='invalid'):
            managed.load_managed_runtime_environment()
    else:
        assert managed.load_managed_runtime_environment()
        assert workers.database_mode() == mode


def test_sheet_transport_bounds_actual_request_and_refresh_without_shared_mutation(monkeypatch):
    import vera_web_v2_leave_sync_queue as queue
    from google.auth.credentials import Credentials
    import requests
    called = []
    class SyntheticCredentials(Credentials):
        def refresh(self, request):
            response = request(url='https://auth.synthetic/token', method='POST')
            assert response.status == 200
            self.token = 'synthetic-token'
    def request(session, method, url, **kwargs):
        # Exercise real AuthorizedSession, credential refresh, its retry, and
        # Google's Request transport without ever creating an external socket.
        called.append((url, kwargs['timeout']))
        assert session.get_adapter(url).max_retries.total == 0
        response = requests.Response()
        response.status_code = (401 if url.endswith('/sheet') and
            sum(item[0].endswith('/sheet') for item in called) == 1 else 200)
        response._content = b'{}'
        return response
    monkeypatch.setattr(requests.Session, 'request', request)
    shared = SimpleNamespace(http_client=SimpleNamespace(auth=SyntheticCredentials(), timeout=None))
    with queue._mirror_client(SimpleNamespace(_google_client=lambda: shared)) as client:
        response = client.http_client.request('GET', 'https://sheets.synthetic/sheet')
        assert response.status_code == 200
        assert client.http_client.timeout == (5, 30)
    assert called == [('https://auth.synthetic/token', (5, 10)),
                      ('https://sheets.synthetic/sheet', (5, 30)),
                      ('https://auth.synthetic/token', (5, 10)),
                      ('https://sheets.synthetic/sheet', (5, 30))]
    assert shared.http_client.timeout is None

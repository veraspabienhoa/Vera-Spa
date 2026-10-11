"""Import the real installed API/worker entrypoints in fresh, offline processes.

Only local connection configuration and per-loop work bodies are synthetic.
The canonical application, installers, registry, queue schema prepares, worker
entrypoint, ASGI lifespan and heartbeat/readiness execute without substitution.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_worker_runtime_postgres import database

ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import json, os, socket, threading
import requests
import sqlalchemy
from sqlalchemy import text
from fastapi.testclient import TestClient
import vera_web_v2_runtime_env as managed

# Do not read any real managed credentials. All nonlocal transports are blocked
# before canonical imports, including inherited HTTP proxies.
def no_private_file(_path):
    raise FileNotFoundError
managed._read_private_file = no_private_file
original_connect = socket.socket.connect
original_dns = socket.getaddrinfo

def local_connect(sock, address):
    if not isinstance(address, tuple) or address[0] not in {'127.0.0.1','localhost','::1'}:
        raise AssertionError('nonlocal network forbidden')
    return original_connect(sock, address)
def local_dns(host, *args, **kwargs):
    if host not in {'127.0.0.1','localhost','::1', b'127.0.0.1', b'localhost', b'::1', None}:
        raise AssertionError('nonlocal DNS forbidden')
    return original_dns(host, *args, **kwargs)
socket.socket.connect = local_connect
socket.getaddrinfo = local_dns
def no_http(*args, **kwargs):
    raise AssertionError('HTTP forbidden in canonical lifecycle fixture')
requests.sessions.Session.send = no_http

# The existing admin-audit installer performs schema DDL during canonical
# import. Supply only an isolated synthetic engine before that installer runs;
# do not replace the canonical app or its route/worker registration functions.
import vera_web_v2_api as base_api
assert base_api._engine is None
engine = sqlalchemy.create_engine(os.environ['VERA_TEST_POSTGRES_URL'],
    connect_args={'options':'-csearch_path='+os.environ['VERA_CANONICAL_TEST_SCHEMA']})
base_api._engine = engine
with engine.begin() as conn:
    conn.execute(text('CREATE TABLE synthetic_worker_seen(name text PRIMARY KEY)'))
    conn.execute(text('CREATE TABLE leave_records(id bigserial PRIMARY KEY, record_uid text, employee_name text, leave_date date)'))

original_start = threading.Thread.start
def forbidden(*args, **kwargs):
    raise AssertionError('canonical import must not start a background thread')
threading.Thread.start = forbidden
try:
    if os.environ['VERA_SERVICE_ROLE'] == 'worker':
        import vera_web_v2_worker as entrypoint
        import vera_web_v2_api_v38 as canonical
    else:
        import vera_web_v2_api_v38 as entrypoint
        canonical = entrypoint
finally:
    threading.Thread.start = original_start

import vera_worker_runtime as runtime_module
runtime = canonical.app.state.worker_runtime
assert set(runtime.workers) == runtime_module.EXPECTED_WORKERS
assert runtime.state == 'stopped'
assert all(worker.thread is None for worker in runtime.workers.values())
assert canonical._api._engine is engine

def synthetic_tick(name):
    def work(stop):
        with engine.begin() as conn:
            conn.execute(text('INSERT INTO synthetic_worker_seen VALUES(:name)'), {'name':name})
        stop.wait(300)
    return work
for name, worker in runtime.workers.items():
    assert callable(worker.target)
    worker.target = synthetic_tick(name)
    worker.stale_after = 400

with TestClient(entrypoint.app) as client:
    assert client.get('/v2/runtime/health').status_code == 200
    if runtime.role == 'api':
        assert all(worker.thread is None for worker in runtime.workers.values())
        assert client.get('/v2/runtime/ready').status_code == 503
    else:
        for worker in runtime.workers.values():
            assert worker.thread and worker.thread.is_alive()
        assert client.get('/v2/runtime/ready').status_code == 200
    if runtime.role == 'worker':
        assert client.get('/v2/auth/health').status_code == 404
        assert client.get('/v2/live-tour').status_code == 404
        assert client.get('/openapi.json').status_code == 404
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('vera_background_job')")).scalar_one()
        assert conn.execute(text("SELECT to_regclass('vera_leave_sheet_sync_queue')")).scalar_one()
        assert conn.execute(text("SELECT to_regclass('vera_worker_runtime')")).scalar_one()
assert runtime.state == 'stopped'
assert all(not worker.thread or not worker.thread.is_alive() for worker in runtime.workers.values())
with engine.connect() as conn:
    count = conn.execute(text('SELECT count(*) FROM synthetic_worker_seen')).scalar_one()
assert count == (0 if runtime.role == 'api' else 7)
engine.dispose()
print(json.dumps({'role':runtime.role,'registered':len(runtime.workers),'executed':count,'stopped':True}))
'''


@pytest.mark.parametrize('role', ['api', 'worker', 'combined'])
def test_real_canonical_entrypoint_import_registration_and_lifespan(database, role):
    # The subprocess inherits only explicitly necessary local test context.
    env = {key:value for key,value in os.environ.items()
           if key in {'PATH', 'PYTHONPATH', 'VIRTUAL_ENV', 'LD_LIBRARY_PATH', 'LANG', 'HOME'}}
    env.update(VERA_TEST_POSTGRES_URL=os.environ['VERA_TEST_POSTGRES_URL'],
               VERA_CANONICAL_TEST_SCHEMA=database.test_schema,
               VERA_SERVICE_ROLE=role, VERA_WORKER_DB_MODE='direct',
               VERA_AUTH_PROVIDER='local', VERA_DB_ENABLED='1',
               VERA_DATA_BACKEND='postgres',
               PYTHONPATH=str(ROOT)+os.pathsep+env.get('PYTHONPATH',''))
    result = subprocess.run([sys.executable, '-c', CHILD], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-6000:]
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        'role':role, 'registered':7, 'executed':0 if role == 'api' else 7, 'stopped':True}

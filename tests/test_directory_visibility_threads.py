import sys
import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import vera_web_v2_work_schedule_permissions as visibility


def test_json_filter_runs_off_event_loop_and_preserves_visibility(monkeypatch):
    app = FastAPI()
    loop_threads = []
    scan_threads = []
    @app.get('/directory')
    async def directory():
        loop_threads.append(threading.get_ident())
        return {'employees':[{'username':'thutrang'},{'username':'staff'}],
                'records':[{'employee_name':'Thu Trang','amount':100}]}
    def identity(authorization=None):
        if authorization == 'admin': return SimpleNamespace(role='admin')
        if authorization == 'fail': raise RuntimeError('unavailable')
        return SimpleNamespace(role='letan')
    monkeypatch.setitem(sys.modules,'vera_web_v2_api_shared',SimpleNamespace(app=app,_api=SimpleNamespace(current_identity=identity)))
    original = visibility._payload_contains_hidden_directory_account
    def scan(value):
        scan_threads.append(threading.get_ident())
        return original(value)
    monkeypatch.setattr(visibility,'_payload_contains_hidden_directory_account',scan)
    visibility._install_directory_visibility_middleware()
    with TestClient(app) as client:
        for role in ('admin','letan','fail'):
            result=client.get('/directory',headers={'authorization':role})
            assert result.status_code == 200
            assert len(result.json()['employees']) == (2 if role=='admin' else 1)
            assert result.json()['records']==[{'employee_name':'Thu Trang','amount':100}]
    assert set(scan_threads).isdisjoint(loop_threads)

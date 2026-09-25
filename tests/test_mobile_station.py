"""Mobile station API must reject untrusted input and require explicit confirmation."""
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

import vera_web_v2_mobile_station as station


def jpeg():
    buffer = BytesIO()
    Image.new('RGB', (100, 120), 'green').save(buffer, 'JPEG')
    return buffer.getvalue()


class FakeDB:
    def __init__(self):
        self.rows = {}

    @contextmanager
    def begin(self):
        yield self

    connect = begin

    def execute(self, sql, params=None):
        statement = str(sql)
        params = params or {}
        values = []
        if 'SELECT username FROM employees' in statement:
            values = [{'username': 'worker'}] if params.get('username') == 'worker' else []
        elif 'SELECT device_id,operator,event_type' in statement and 'image_sha256' in statement:
            values = [self.rows[params['id']]] if params['id'] in self.rows else []
        elif 'SELECT device_id,event_type,employee_username' in statement:
            values = [self.rows[params['id']]] if params['id'] in self.rows else []
        elif statement.startswith('INSERT INTO vera_mobile_station_event'):
            self.rows[params['id']] = {
                'device_id': params['device'], 'operator': params['actor'], 'event_type': params['type'],
                'employee_username': params['employee'], 'barcode': params['barcode'],
                'image_sha256': params['digest'], 'occurred_at': params['occurred'], 'confirmed_at': None,
            }
        elif statement.startswith('UPDATE vera_mobile_station_event'):
            self.rows[params['id']]['confirmed_at'] = datetime.now(timezone.utc)
        elif statement.startswith('SELECT id,device_id,operator,event_type'):
            values = [dict(id=key, **value, has_image=bool(value['image_sha256'])) for key, value in self.rows.items()]
        elif statement.startswith('SELECT image FROM vera_mobile_station_event'):
            values = []
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: values[0] if values else None, all=lambda: values),
                               scalar=lambda: next(iter(values[0].values())) if values else None)


def client(monkeypatch, role='admin'):
    db = FakeDB()
    monkeypatch.setattr(station, 'read_registry', lambda conn: {'devices': [{'id': 'phone', 'enabled': True, 'kind': 'camera'}]})
    app = FastAPI()
    station.install_mobile_station_routes(app, engine_instance=lambda: db,
        current_identity=lambda: SimpleNamespace(role=role, employee_username='admin'), identity_type=SimpleNamespace,
        require_feature=lambda conn, ident, feature: None if ident.role == 'admin' else (_ for _ in ()).throw(HTTPException(403, 'denied')))
    return TestClient(app), db


def test_mobile_station_rejects_non_admin_and_invalid_image(monkeypatch):
    api, _ = client(monkeypatch, 'nhanvien')
    path = f'/v2/devices/mobile-station/phone/events/{uuid4()}?event_type=photo'
    assert api.post(path, content=jpeg(), headers={'Content-Type': 'image/jpeg'}).status_code == 403
    api, _ = client(monkeypatch)
    assert api.post(path, content=b'bad', headers={'Content-Type': 'image/jpeg'}).status_code == 400
    assert api.post(path, content=b'x' * (station.MAX_IMAGE + 1), headers={'Content-Type': 'image/jpeg'}).status_code == 413
    assert api.post(path.replace('/phone/', '/missing/'), content=jpeg(), headers={'Content-Type': 'image/jpeg'}).status_code == 403


def test_checkin_evidence_requires_explicit_confirmation_and_is_idempotent(monkeypatch):
    api, db = client(monkeypatch)
    event_id = str(uuid4())
    url = f'/v2/devices/mobile-station/phone/events/{event_id}?event_type=checkin&employee_username=worker'
    calls = []
    import vera_web_v2_hr_enhancements as hr
    monkeypatch.setattr(hr, 'record_checkin', lambda *a, **kw: calls.append(kw) or {'attendance_log_id': 'log'})
    assert api.post(url, content=jpeg(), headers={'Content-Type': 'image/jpeg'}).status_code == 200
    assert not calls
    assert api.post(url, content=jpeg(), headers={'Content-Type': 'image/jpeg'}).status_code == 200
    assert api.post(url.replace('worker', 'other'), content=jpeg(), headers={'Content-Type': 'image/jpeg'}).status_code == 409
    confirmation = f'/v2/devices/mobile-station/events/{event_id}/confirm'
    assert api.post(confirmation).status_code == 200
    assert api.post(confirmation).json()['already_confirmed']
    assert len(calls) == 1 and calls[0]['source'] == 'mobile_admin_confirmed'
    assert calls[0]['username'] == 'worker'
    assert db.rows[event_id]['confirmed_at']

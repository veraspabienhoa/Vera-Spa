from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

import vera_web_v2_face_id as face


def png(width=300, height=400, color='blue'):
    out = BytesIO()
    Image.new('RGB', (width, height), color).save(out, format='PNG')
    return out.getvalue()


class Database:
    def __init__(self):
        self.photo = None
        self.active = False

    @contextmanager
    def begin(self):
        self.active = True
        try:
            yield self
        finally:
            self.active = False

    def execute(self, sql, params=None):
        sql, params = str(sql), params or {}
        rows = []
        if 'SELECT e.username' in sql:
            rows = [{'username': 'worker', 'sha256': self.photo.get('sha256') if self.photo else None}]
        elif 'SELECT username FROM employees' in sql:
            rows = [{'username': 'worker'}] if params.get('username', 'worker') == 'worker' else []
        elif 'INSERT INTO vera_employee_face_id' in sql:
            self.photo = {'content': params['content'], 'content_type': params['type'], 'size_bytes': params['size'], 'sha256': params['sha']}
        elif 'DELETE FROM vera_employee_face_id' in sql:
            self.photo = None
        elif 'SELECT sha256' in sql:
            rows = [{'sha256': self.photo['sha256']}] if self.photo else []
        elif 'FROM vera_employee_face_id' in sql:
            rows = [({k: self.photo.get(k) for k in ('size_bytes', 'sha256', 'updated_at')} if 'SELECT size_bytes' in sql else self.photo)] if self.photo else []
        elif 'FROM vera_employee_identity_document' in sql:
            rows = [{'content': png(), 'content_type': 'image/png'}]
        elif not any(word in sql for word in ('CREATE TABLE', 'ALTER TABLE', 'DO $$')):
            raise AssertionError(sql)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: rows[0] if rows else None, all=lambda: rows), scalar=lambda: next(iter(rows[0].values())) if rows else None)


def client(grants):
    db, app = Database(), FastAPI()
    class Identity:
        employee_username = 'operator'
    def require(conn, ident, feature):
        if feature not in grants:
            raise HTTPException(403, 'denied')
    face.install_face_id_routes(app, engine_instance=lambda: db, current_identity=lambda: Identity(), require_feature=require, identity_type=Identity)
    return db, TestClient(app)


def test_separate_store_roundtrip_and_read_only_permission():
    grants = {'employee_face_id_view', 'employee_face_id_manage'}
    db, api = client(grants)
    path = '/v2/staff/worker/face-id'
    assert api.put(path+'/image', content=png(), headers={'Content-Type': 'image/png'}).status_code == 200
    assert api.get(path+'/image').content == png()
    assert api.get(path+'/image').headers['cache-control'] == 'private, no-store'
    assert api.get(path).json()['photo']['size_bytes'] == len(png())
    grants.remove('employee_face_id_manage')
    assert not api.get(path).json()['can_manage']
    assert api.delete(path+'/image').status_code == 403
    assert api.put(path+'/image', content=png(), headers={'Content-Type': 'image/png'}).status_code == 403
    assert api.get(path+'/portrait-source').status_code == 403
    assert api.get(path+'/captures?day=2026-09-24').status_code == 403
    grants.clear()
    assert api.get(path).status_code == api.get(path+'/image').status_code == 403
    assert db.photo is not None


def test_reject_invalid_images_and_missing_employee():
    _, api = client({'employee_face_id_view', 'employee_face_id_manage'})
    path = '/v2/staff/worker/face-id/image'
    assert api.put(path, content=b'<svg/>', headers={'Content-Type':'image/svg+xml'}).status_code == 400
    assert api.put(path, content=png(400,300), headers={'Content-Type':'image/png'}).status_code == 400
    assert api.put(path, content=b'x' * (700*1024+1), headers={'Content-Type':'image/png'}).status_code == 413
    assert api.get('/v2/staff/missing/face-id').status_code == 404


def test_device_io_releases_connection_and_requires_unique_event(monkeypatch):
    import vera_facegate_control_log as device
    db, api = client({'employee_face_id_view', 'employee_face_id_manage'})
    def read(*args):
        assert not db.active
        return {'records': [{'event_id': 2, 'occurred_at':'2026-09-24T10:00:00+07:00', 'image_available':True, 'image_ref':{}}]}
    def image(*args):
        assert not db.active
        return png(), 'image/png'
    monkeypatch.setattr(device, 'fetch_capture_log', read)
    monkeypatch.setattr(device, 'fetch_capture_image', image)
    path = '/v2/staff/worker/face-id'
    assert api.get(path+'/captures?day=2026-09-24').json()['identity_verified'] is False
    assert api.get(path+'/capture-image?day=2026-09-24&event_id=2').status_code == 200
    assert api.get(path+'/capture-image?day=2026-09-24&event_id=9').status_code == 409


def test_permission_defaults_are_admin_only_and_pdf_has_no_face_photo():
    import vera_web_v2_permissions as permissions
    import vera_web_v2_staff_security as staff
    assert 'employee_face_id_manage' in permissions.DEFAULT_ROLE_FEATURES['admin']
    for role, features in permissions.DEFAULT_ROLE_FEATURES.items():
        if role != 'admin':
            assert 'employee_face_id_manage' not in features
    assert 'face_id' not in staff.MEDIA_SIDES
    # The PDF renderer only reads its explicit portrait/front/back keys.
    import inspect
    assert 'face_id' not in inspect.getsource(staff._build_employee_profile_pdf)


def test_batch_plan_uses_username_never_full_name_and_keeps_accents():
    rows = [{'username': 'Tuyết Nhi', 'full_name': 'Nguyễn Thị Nhi', 'sha256': 'saved'}, {'username': 'An', 'full_name': 'Khác'}]
    result = face.batch_plan(['Tuyết Nhi.jpg', 'Nguyễn Thị Nhi.jpg', 'Tuyet Nhi.jpg', '../An.png', 'An.jpg', 'an.png'], rows)
    assert result[0]['username'] == 'Tuyết Nhi' and result[0]['existing_sha256'] == 'saved'
    assert [row['status'] for row in result[1:]] == ['not_found','not_found','invalid_filename','duplicate_filename','duplicate_filename']
    import unicodedata
    assert face.batch_plan([unicodedata.normalize('NFD', 'Tuyết Nhi')+'.PNG'], rows)[0]['status'] == 'ready'
    assert face.batch_plan(['An.jpg'], [{'username':'An'}, {'username':'AN'}])[0]['status'] == 'ambiguous'


def test_batch_api_permissions_limit_and_existing_photo_guard():
    grants = {'employee_face_id_view','employee_face_id_manage'}
    db, api = client(grants)
    assert api.post('/v2/face-id/batch-plan', json={'filenames':['worker.jpg']}).json()['records'][0]['username'] == 'worker'
    assert api.post('/v2/face-id/batch-plan', json={'filenames':['worker.jpg']*51}).status_code == 422
    path = '/v2/staff/worker/face-id/image?filename=worker.jpg'
    headers = {'Content-Type':'image/png','If-None-Match':'*'}
    assert api.put(path,content=png(),headers=headers).status_code == 200
    old = db.photo['sha256']
    assert api.put(path,content=png(),headers=headers).status_code == 200  # retry lost response
    assert api.put(path,content=png(color='red'),headers=headers).status_code == 409
    assert db.photo['sha256'] == old
    assert api.put(path,content=png(color='red'),headers={'Content-Type':'image/png','If-Match':f'"{old}"'}).status_code == 200
    assert api.put(path,content=png(color='green'),headers={'Content-Type':'image/png','If-Match':f'"{old}"'}).status_code == 409
    assert api.put(path,content=png(),headers={'Content-Type':'image/png'}).status_code == 400
    assert api.put(path.replace('worker.jpg','someone.jpg'),content=png(),headers=headers).status_code == 409
    grants.remove('employee_face_id_manage')
    assert api.post('/v2/face-id/batch-plan',json={'filenames':['worker.jpg']}).status_code == 403

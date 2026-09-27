"""Real HTTP/PostgreSQL checks for explicit capture-to-Face-ID selection."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text

from test_face_id_photos import png
import vera_web_v2_face_id as face


@pytest.fixture
def fixture(monkeypatch):
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Real PostgreSQL required')
    schema = 'capture_photo_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    db = create_engine(url, pool_size=2, max_overflow=0,
                       connect_args={'options': f'-csearch_path={schema}'})
    with db.begin() as conn:
        conn.execute(text("CREATE TABLE employees(username text PRIMARY KEY,full_name text,payload jsonb DEFAULT '{}'::jsonb)"))
        conn.execute(text("""INSERT INTO employees VALUES ('Ánh Thử','Nguyễn Ánh Thử','{}'),
            ('Đã xóa','Không trả về',CAST(:deleted AS jsonb))"""), {'deleted': '{"__deleted":true}'})
        face.ensure_table(conn)
    grants = {'device_history_view', 'employee_face_id_view', 'employee_face_id_manage'}
    app = FastAPI()
    def require(conn, ident, feature):
        if feature not in grants:
            raise HTTPException(403, 'denied')
    ident = SimpleNamespace(employee_username='admin',role='admin')
    face.install_face_id_routes(app, engine_instance=lambda: db,
        current_identity=lambda: ident, require_feature=require, identity_type=SimpleNamespace)
    # Saving a chosen photo must not call the device or turn on attendance.
    import vera_facegate_control_log as device
    monkeypatch.setattr(device, 'fetch_capture_image', lambda *_a, **_k: pytest.fail('unexpected device I/O'))
    monkeypatch.setattr(device, 'fetch_capture_log', lambda *_a, **_k: pytest.fail('unexpected device I/O'))
    try:
        with TestClient(app) as api:
            yield db, api, grants
    finally:
        db.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def test_directory_is_small_unicode_projection_and_requires_both_permissions(fixture):
    db, api, grants = fixture
    calls = []
    def observe(_conn, _cursor, sql, _params, _context, _many): calls.append(sql)
    event.listen(db, 'before_cursor_execute', observe)
    response = api.get('/v2/face-id/assignment-employees')
    event.remove(db, 'before_cursor_execute', observe)
    assert response.status_code == 200
    assert response.json() == {'employees':[{'username':'Ánh Thử','full_name':'Nguyễn Ánh Thử'}]}
    assert len(calls) == 1 and 'LIMIT 1001' in calls[0] and 'content' not in calls[0]
    grants.remove('employee_face_id_manage')
    assert api.get('/v2/face-id/assignment-employees').status_code == 403
    grants.add('employee_face_id_all_users_edit')
    assert api.get('/v2/face-id/assignment-employees').status_code == 200
    grants.remove('device_history_view')
    assert api.get('/v2/face-id/assignment-employees').status_code == 403


def test_explicit_save_retry_conflict_permission_revocation_and_deleted_staff(fixture):
    db, api, grants = fixture
    path = '/v2/staff/Ánh Thử/face-id/image'
    initial = png()
    headers = {'Content-Type':'image/png','If-None-Match':'*'}
    assert api.put(path,content=initial,headers=headers).status_code == 200
    with db.connect() as conn:
        before = conn.execute(text('SELECT sha256,updated_at,updated_by FROM vera_employee_face_id')).mappings().one()
    assert before['updated_by'] == 'admin'
    assert api.put(path,content=initial,headers=headers).status_code == 200
    with db.connect() as conn:
        assert conn.execute(text('SELECT updated_at FROM vera_employee_face_id')).scalar() == before['updated_at']
    assert api.put(path,content=png(color='red'),headers=headers).status_code == 409
    matched = {'Content-Type':'image/png','If-Match':f'"{before["sha256"]}"'}
    assert api.put(path,content=png(color='red'),headers=matched).status_code == 200
    assert api.put(path,content=png(color='green'),headers=matched).status_code == 409
    assert api.get(path).content == png(color='red')
    grants.remove('employee_face_id_manage')
    assert api.put(path,content=initial,headers=matched).status_code == 403
    grants.add('employee_face_id_manage')
    assert api.put('/v2/staff/Đã xóa/face-id/image',content=initial,headers=headers).status_code == 404
    assert api.put(path,content=png(400,300),headers=matched).status_code == 409
    assert api.put(path,content=b'bad image',headers=matched).status_code == 400
    with db.connect() as conn:
        tables = set(conn.execute(text('SELECT tablename FROM pg_tables WHERE schemaname=current_schema()')).scalars())
        assert tables == {'employees','vera_employee_face_id','vera_face_id_self_update','vera_face_id_self_update_config'}


@pytest.mark.parametrize('suffix', ['image', 'capture-photo'])
def test_two_users_cannot_overwrite_each_other_after_same_photo_read(fixture, suffix):
    db, api, _ = fixture
    path = '/v2/staff/Ánh Thử/face-id/' + suffix
    initial = png()
    assert api.put(path,content=initial,headers={'Content-Type':'image/png','If-None-Match':'*'}).status_code == 200
    sha = hashlib.sha256(initial).hexdigest()
    barrier = Barrier(2)
    def update(color):
        barrier.wait(timeout=5)
        return api.put(path,content=png(color=color),headers={'Content-Type':'image/png','If-Match':f'"{sha}"'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update,['red','green']))
    assert sorted(results) == [200,409]
    assert api.get('/v2/staff/Ánh Thử/face-id/image').content in (png(color='red'),png(color='green'))


def test_capture_conversion_releases_connection_preserves_retry_and_rechecks_permission(fixture, monkeypatch):
    from io import BytesIO
    from PIL import Image
    from test_facegate_photo import raster
    import vera_facegate_photo as capture
    db, api, grants = fixture
    path = '/v2/staff/Ánh Thử/face-id/capture-photo'
    image_path = '/v2/staff/Ánh Thử/face-id/image'
    original = raster(size=(600,500), noise=True)
    assert 700*1024 < len(original) < capture.MAX_CAPTURE_BYTES
    prepare = capture.prepare_capture_photo
    revoke = False
    def convert(*args, **kwargs):
        assert db.pool.checkedout() == 0
        if revoke:
            grants.remove('device_history_view')
        return prepare(*args, **kwargs)
    monkeypatch.setattr(capture, 'prepare_capture_photo', convert)
    headers = {'Content-Type':'image/bmp','If-None-Match':'*'}
    assert api.put(path,content=original,headers=headers).status_code == 200
    saved = api.get(image_path)
    assert len(saved.content) <= 700*1024
    with Image.open(BytesIO(saved.content)) as image:
        assert image.size == (600,500)
    with db.connect() as conn:
        first = dict(conn.execute(text('SELECT sha256,updated_at FROM vera_employee_face_id')).mappings().one())
    assert api.put(path,content=original,headers=headers).status_code == 200
    with db.connect() as conn:
        assert dict(conn.execute(text('SELECT sha256,updated_at FROM vera_employee_face_id')).mappings().one()) == first
    assert api.put('/v2/staff/Đã xóa/face-id/capture-photo',content=original,headers=headers).status_code == 404
    revoke = True
    assert api.put(path,content=raster(),headers={'Content-Type':'image/bmp','If-Match':f'"{first["sha256"]}"'}).status_code == 403
    assert api.get(image_path).content == saved.content

"""Operator-authorized, exact account rename using the deployed business route."""
import hashlib
import json
import os
import traceback
from types import SimpleNamespace
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from vera_facegate_cutover import runtime_engine, verify_runtime
from vera_employee_names import previous_names
from vera_web_v2_system_name import install_system_name_routes, SystemNameUpdate
from vera_web_v2_facegate_enrollment import mappings, target
from vera_facegate_control_log import mapping_device_id, facegate_endpoint, registration_ref
from vera_facegate_enrollment import FaceGateEnrollmentClient

EXPECTED_RELEASE = '3155d04cd77fb219a0dc1877e2f1930219a459c9'


def directory(conn, name):
    return conn.execute(text("SELECT username,role,full_name,payload FROM employees WHERE lower(btrim(username))=lower(:name) AND COALESCE(payload->>'__deleted','false')<>'true'"), {'name': name}).mappings().all()


def photo_hash(conn, username):
    if not conn.execute(text("SELECT to_regclass('vera_employee_face_id')")).scalar():
        return None
    # Compare entire row minus its renamed owner without exposing face content.
    row = conn.execute(text("SELECT to_jsonb(f)-'employee_username' FROM vera_employee_face_id f WHERE employee_username=:name"), {'name': username}).scalar()
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


def auth_ids(conn, username):
    if not conn.execute(text("SELECT to_regclass('vera_v2_user_profile')")).scalar():
        return []
    return sorted(str(v) for v in conn.execute(text('SELECT auth_user_id FROM vera_v2_user_profile WHERE employee_username=:name'), {'name': username}).scalars())


def main():
    verify_runtime(EXPECTED_RELEASE)
    engine = runtime_engine()
    from vera_vps_data_check import _running_api_environment
    runtime = _running_api_environment()
    mode = runtime.get('VERA_LIVE_TOUR_RELATIONAL_MODE')
    if mode in {'off', 'shadow', 'verify', 'active'}:
        os.environ['VERA_LIVE_TOUR_RELATIONAL_MODE'] = mode
    from vera_web_v2_runtime_env import load_live_tour_mode_override
    load_live_tour_mode_override()
    print(json.dumps({'storage_mode': os.environ.get('VERA_LIVE_TOUR_RELATIONAL_MODE', 'shadow')}))
    client = None
    try:
        with engine.begin() as conn:
            source, destination = directory(conn, 'letan'), directory(conn, 'Assistant')
            if len(source) != 1:
                if len(destination) == 1 and any(n.casefold() == 'letan' for n in previous_names(destination[0])):
                    print(json.dumps({'status': 'already_renamed'}))
                    original = destination[0]['username']
                else:
                    raise HTTPException(409, 'Không tìm thấy duy nhất tài khoản letan đang hoạt động.')
            else:
                if destination:
                    raise HTTPException(409, 'Tên Assistant đã được dùng; chưa đổi tài khoản.')
                original = source[0]['username']
            old_photo = photo_hash(conn, original)
            old_auth = auth_ids(conn, original)
        if source:
            app = FastAPI()
            # This trusted SSH maintenance operation is authorized by the owner;
            # record that provenance rather than impersonating an employee login.
            actor = SimpleNamespace(role='admin', employee_username='maintenance:user-authorized:letan-to-Assistant')
            install_system_name_routes(app, engine_instance=lambda: engine,
                current_identity=lambda: actor, identity_type=SimpleNamespace)
            route = next(r.endpoint for r in app.routes if r.path == '/v2/staff/{username}/system-name')
            result = route(original, SystemNameUpdate(system_name='Assistant'), actor)
            print(json.dumps({'status': 'rename_committed', 'face_id_sync': result.get('face_id_sync')}))
        with engine.begin() as conn:
            saved = directory(conn, 'Assistant')
            if len(saved) != 1 or directory(conn, 'letan'):
                raise HTTPException(409, 'Kết quả danh bạ không khớp.')
            if photo_hash(conn, 'Assistant') != old_photo or auth_ids(conn, 'Assistant') != old_auth:
                raise HTTPException(409, 'Cần kiểm tra tính toàn vẹn hồ sơ.')
            device_id = mapping_device_id()
            entries = [r for r in mappings(conn, device_id) if r.get('username') == 'Assistant']
            address = target(conn)
        if not entries:
            print(json.dumps({'ok': True, 'account_name_verified': True, 'auth_identity_preserved': True,
                              'face_photo_preserved': True, 'device_rename_verified': False,
                              'reason': 'employee_has_no_confirmed_device_mapping'}))
            return 0
        if len(entries) != 1 or not entries[0].get('confirmed_by'):
            raise HTTPException(409, 'Ánh xạ máy cần được kiểm tra.')
        entry = entries[0]
        if entry.get('device_name') != 'Assistant':
            from vera_employee_rename_sync import queue_device_rename, sync_device_names
            with engine.begin() as conn:
                conn.execute(text('SELECT pg_advisory_xact_lock(723491, 1)'))
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:employees'))"))
                owners = directory(conn, 'Assistant')
                if len(owners) != 1:
                    raise HTTPException(409, 'Tài khoản đã thay đổi trước khi đồng bộ máy.')
                pending = conn.execute(text("SELECT 1 FROM vera_facegate_rename_job WHERE employee_username='Assistant' AND status='pending' LIMIT 1")).scalar()
                if not pending:
                    queue_device_rename(conn, 'Assistant', 'Assistant')
            sync_device_names(engine, 'Assistant')
            with engine.begin() as conn:
                entries = [r for r in mappings(conn, device_id) if r.get('username') == 'Assistant']
                if len(entries) != 1 or entries[0].get('profile_id') != entry.get('profile_id'):
                    raise HTTPException(409, 'Ánh xạ thay đổi trong lúc đồng bộ tên máy.')
                entry = entries[0]
        with facegate_endpoint('http://' + address):
            client = FaceGateEnrollmentClient()
            client.login()
            profile = client.profile_details(int(entry['profile_id']))
        verified = (profile.get('uname') == 'Assistant'
                    and registration_ref(profile) == entry.get('registration_ref')
                    and entry.get('device_name') == 'Assistant')
        print(json.dumps({'ok': verified, 'account_name_verified': True,
                          'auth_identity_preserved': True, 'face_photo_preserved': True,
                          'device_rename_verified': verified, 'device_profile_id_preserved': True}))
        return 0 if verified else 1
    finally:
        if client:
            client.close()
        engine.dispose()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except HTTPException as exc:
        print(json.dumps({'ok': False, 'http_status': exc.status_code, 'detail': exc.detail}, ensure_ascii=False))
        raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__,
                          'frames': [{'file': frame.filename.rsplit('/', 1)[-1], 'function': frame.name, 'line': frame.lineno}
                                     for frame in traceback.extract_tb(exc.__traceback__)[-5:]]}))
        raise SystemExit(1)

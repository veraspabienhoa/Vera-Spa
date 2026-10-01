"""Durable enrollment journal; device I/O always outside database transactions."""
from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv4Network
import json
import re
import uuid

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from vera_facegate_control_log import facegate_endpoint, mapping_device_id
from vera_facegate_enrollment import FaceGateEnrollmentClient, EnrollmentError, UploadRejected, jpeg_photo
from vera_web_v2_devices import read_registry, norm


class EnrollmentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    photo_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmed: bool


def ensure_enrollment(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_facegate_enrollment (
        operation_id text PRIMARY KEY, device_id text NOT NULL,
        device_address text NOT NULL, employee_username text NOT NULL,
        photo_sha256 text NOT NULL, device_name text NOT NULL,
        actor text NOT NULL, status text NOT NULL, stage text NOT NULL,
        upload_session text NOT NULL, registration_ref jsonb, profile_id bigint,
        error_code text, created_at timestamptz NOT NULL DEFAULT NOW(),
        updated_at timestamptz NOT NULL DEFAULT NOW()
    )'''))
    conn.execute(text('''CREATE UNIQUE INDEX IF NOT EXISTS vera_facegate_enrollment_busy
        ON vera_facegate_enrollment(device_id) WHERE status IN ('running','unverified')'''))


def decode(value, default):
    return json.loads(value) if isinstance(value, str) else value if value is not None else default


def target(conn):
    matches = [row for row in read_registry(conn)['devices'] if row.get('id') == 'facegate-current']
    if len(matches) != 1 or not matches[0].get('enabled') or matches[0].get('adapter') != 'facegate_server':
        raise HTTPException(409, 'Cần bật đúng máy FaceGate trong Thiết bị.')
    address = matches[0].get('address', '')
    try:
        if IPv4Address(address) not in IPv4Network('192.168.1.0/24'):
            raise ValueError()
    except ValueError:
        raise HTTPException(409, 'Cần lưu IP nội bộ hợp lệ của máy FaceGate.') from None
    return address


def mappings(conn, device_id, lock=False):
    value = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='facegate' AND setting_key=:key" + (' FOR UPDATE' if lock else '')),
                         {'key': 'mapping_' + device_id}).scalar()
    value = decode(value, [])
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise HTTPException(409, 'Dữ liệu ánh xạ cần được kiểm tra trước khi đăng ký.')
    return value


def public(row):
    if not row:
        return {'status': 'not_registered'}
    result = {key: row.get(key) for key in ('operation_id', 'status', 'stage', 'photo_sha256',
                                        'profile_id', 'updated_at', 'error_code')}
    updated = row.get('updated_at')
    result['stale'] = bool(row.get('status') == 'running' and updated and
                           (datetime.now(timezone.utc) - updated).total_seconds() >= 180)
    return result


def assert_new_mapping(rows, username):
    # Even stale IP mappings must be reviewed, never silently duplicated.
    if any(row.get('username', '').casefold() == username.casefold() for row in rows):
        raise HTTPException(409, 'Nhân viên đã có ánh xạ máy. Cần kiểm tra hồ sơ hiện có; không tạo thêm hồ sơ trùng.')
    if len(rows) >= 200:
        raise HTTPException(409, 'Máy đã đạt giới hạn ánh xạ trong VERA.')


def install_enrollment_routes(app, *, engine_instance, current_identity, require_feature, identity_type):
    def authorize(conn, ident):
        require_feature(conn, ident, 'employee_face_id_manage')
        require_feature(conn, ident, 'device_facegate_mapping_manage')
        actor = str(getattr(ident, 'employee_username', '') or '').strip()
        if not actor:
            raise HTTPException(403, 'Không xác định được người đăng ký.')
        return actor

    def employee(conn, username, *, lock=True):
        row = conn.execute(text('''SELECT username, full_name FROM employees
            WHERE lower(btrim(username))=lower(btrim(:username))
            AND role <> 'admin' AND COALESCE(payload->>'__deleted','false') <> 'true'
            ''' + (' FOR UPDATE' if lock else '')), {'username': username}).mappings().all()
        if len(row) != 1:
            raise HTTPException(404, 'Không tìm thấy duy nhất một hồ sơ nhân viên đang hoạt động.')
        return dict(row[0])

    def checkpoint(op, *, status='running', stage=None, ref=None, code=None, expected_status='running'):
        with engine_instance().begin() as conn:
            updated = conn.execute(text('''UPDATE vera_facegate_enrollment SET status=:status,
                stage=COALESCE(:stage,stage), registration_ref=COALESCE(CAST(:ref AS jsonb),registration_ref),
                error_code=:code, updated_at=NOW() WHERE operation_id=:op AND status=:expected_status '''),
                {'op': op, 'status': status, 'stage': stage,
                 'ref': json.dumps(ref) if ref is not None else None, 'code': code, 'expected_status': expected_status})
            if not updated.rowcount and status == 'running':
                raise HTTPException(409, 'Lượt đăng ký đã được xử lý bởi lần kiểm tra khác; không gửi lại lên máy.')
            return bool(updated.rowcount)

    def finish(row, profile):
        with engine_instance().begin() as conn:
            # Serialize with other enrollment finalizers; normal mapping writers
            # share the setting row lock acquired below.
            conn.execute(text('SELECT pg_advisory_xact_lock(723491, 1)'))
            current = conn.execute(text('SELECT * FROM vera_facegate_enrollment WHERE operation_id=:op FOR UPDATE'),
                                   {'op': row['operation_id']}).mappings().first()
            if current['status'] == 'verified':
                return public(current)
            if target(conn) != row['device_address'] or mapping_device_id() != row['device_id']:
                raise HTTPException(409, 'Cấu hình máy đã đổi; chưa xác nhận ánh xạ.')
            employee(conn, row['employee_username'])
            key = 'mapping_' + row['device_id']
            conn.execute(text('''INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
                VALUES ('facegate',:key,'[]'::jsonb,'web_v2',:actor,1,NOW(),NOW())
                ON CONFLICT(category,setting_key) DO NOTHING'''), {'key': key, 'actor': row['actor']})
            existing = mappings(conn, row['device_id'], lock=True)
            assert_new_mapping(existing, row['employee_username'])
            if any(item.get('profile_id') == profile['profile_id'] or item.get('registration_ref') == profile['registration_ref'] for item in existing):
                raise HTTPException(409, 'Hồ sơ hoặc ảnh máy đã gắn với nhân viên khác.')
            entry = {**profile, 'username': row['employee_username'], 'employee_code': '',
                     'device_address': row['device_address'], 'confirmed_by': row['actor'],
                     'confirmed_at': datetime.now(timezone.utc).isoformat(),
                     'enrollment_operation_id': row['operation_id']}
            conn.execute(text('''UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb),
                updated_by=:actor,updated_at=NOW(),revision=revision+1
                WHERE category='facegate' AND setting_key=:key'''),
                {'key': key, 'value': json.dumps(existing + [entry], ensure_ascii=False), 'actor': row['actor']})
            result = conn.execute(text('''UPDATE vera_facegate_enrollment SET status='verified',
                stage='verified', profile_id=:uid, error_code=NULL, updated_at=NOW()
                WHERE operation_id=:op RETURNING *'''),
                {'op': row['operation_id'], 'uid': profile['profile_id']}).mappings().first()
            return public(result)

    @app.get('/v2/staff/{username}/face-id/enrollment')
    def status(username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            authorize(conn, ident)
            person = employee(conn, username, lock=False)
            ensure_enrollment(conn)
            row = conn.execute(text('''SELECT * FROM vera_facegate_enrollment WHERE employee_username=:username
                ORDER BY created_at DESC LIMIT 1'''), {'username': person['username']}).mappings().first()
            result = public(row)
            busy = conn.execute(text("SELECT * FROM vera_facegate_enrollment WHERE device_id=:device AND status IN ('running','unverified')"),
                                {'device': mapping_device_id()}).mappings().first()
            result['device_pending'] = ({**public(busy), 'employee_username': busy['employee_username']}
                                        if busy else None)
            result['can_enroll'] = not busy
            return result

    @app.post('/v2/staff/{username}/face-id/enrollment')
    def enroll(username: str, body: EnrollmentInput, ident: identity_type = Depends(current_identity)):
        if not body.confirmed:
            raise HTTPException(400, 'Cần xác nhận ảnh thuộc đúng nhân viên trước khi gửi máy.')
        with engine_instance().begin() as conn:
            actor = authorize(conn, ident)
            conn.execute(text('SELECT pg_advisory_xact_lock(723491, 1)'))
            person = employee(conn, username)
            username = person['username']
            address = target(conn)
            device_id = mapping_device_id()
            ensure_enrollment(conn)
            conn.execute(text('SELECT pg_advisory_xact_lock(723491, 1)'))
            prior = conn.execute(text('''SELECT * FROM vera_facegate_enrollment WHERE device_id=:device
                AND employee_username=:username AND status='verified' ORDER BY created_at DESC LIMIT 1'''),
                {'device': device_id, 'username': username}).mappings().first()
            if prior:
                if prior['photo_sha256'] == body.photo_sha256 and prior['device_address'] == address:
                    return public(prior)
                raise HTTPException(409, 'Đã đăng ký trước đó. Ảnh mới chưa gửi lên máy; cần quy trình thay ảnh hồ sơ hiện có.')
            busy = conn.execute(text("SELECT * FROM vera_facegate_enrollment WHERE device_id=:device AND status IN ('running','unverified')"),
                                {'device': device_id}).mappings().first()
            if busy:
                if busy['employee_username'] == username:
                    return public(busy)
                raise HTTPException(409, 'Máy đang có lượt đăng ký chưa xác minh. Hãy hoàn tất lượt đó trước.')
            assert_new_mapping(mappings(conn, device_id), username)
            from vera_web_v2_face_id import ensure_table
            ensure_table(conn)
            photo = conn.execute(text('SELECT content, content_type, sha256 FROM vera_employee_face_id WHERE employee_username=:username'),
                                 {'username': username}).mappings().first()
            if not photo or photo['sha256'] != body.photo_sha256:
                raise HTTPException(409, 'Ảnh đã thay đổi hoặc chưa lưu. Hãy tải lại ảnh trước khi đăng ký.')
            name = str(person['full_name'] or username).strip()
            if not name or len(name.encode('utf-8')) >= 48 or sum(ord(c) > 127 for c in name) >= 16 or re.search(r'[\x00-\x1f\x7f]', name):
                raise HTTPException(400, 'Tên nhân viên vượt giới hạn tên của máy FaceGate.')
            original = bytes(photo['content'])
            row = {'operation_id': uuid.uuid4().hex, 'device_id': device_id, 'device_address': address,
                   'employee_username': username, 'photo_sha256': photo['sha256'], 'device_name': name,
                   'actor': actor, 'upload_session': str(uuid.uuid4().int % 90000000 + 10000000)}
            conn.execute(text('''INSERT INTO vera_facegate_enrollment
                (operation_id,device_id,device_address,employee_username,photo_sha256,device_name,actor,status,stage,upload_session)
                VALUES (:operation_id,:device_id,:device_address,:employee_username,:photo_sha256,:device_name,:actor,'running','preflight',:upload_session)'''), row)
        stage, client = 'preflight', None
        try:
            photo_bytes = jpeg_photo(original)
            with facegate_endpoint('http://' + address):
                client = FaceGateEnrollmentClient()
                client.login()
                profiles = client.profiles()
                if any(norm(p.get('uname')) in {norm(username), norm(name)} for p in profiles):
                    raise UploadRejected('existing_profile', 'Máy đã có tên tương ứng. Hãy đối chiếu hồ sơ hiện có trước khi tạo mới.')
                defaults = client.door_defaults()
                with engine_instance().begin() as conn:
                    authorize(conn, ident)
                    employee(conn, username)
                    if target(conn) != address or mapping_device_id() != device_id:
                        raise HTTPException(409, 'Máy đã đổi trong lúc chuẩn bị.')
                    assert_new_mapping(mappings(conn, device_id), username)
                    current_sha = conn.execute(text('SELECT sha256 FROM vera_employee_face_id WHERE employee_username=:username'), {'username': username}).scalar()
                    if current_sha != body.photo_sha256:
                        raise HTTPException(409, 'Ảnh đã đổi trong lúc chuẩn bị.')
                # Durable checkpoint commits BEFORE each potentially mutating call.
                checkpoint(row['operation_id'], stage='uploading')
                stage = 'uploading'
                ref = client.upload(photo_bytes, row['upload_session'])
                checkpoint(row['operation_id'], stage='uploaded', ref=ref)
                row['registration_ref'] = ref
                checkpoint(row['operation_id'], stage='committing')
                stage = 'committing'
                client.add(name, 'vera:' + row['operation_id'], ref, defaults)
                profile = client.verify(name, 'vera:' + row['operation_id'], ref)
            return finish(row, profile)
        except Exception as exc:
            rejected = stage == 'preflight' or isinstance(exc, UploadRejected)
            code = exc.code if isinstance(exc, EnrollmentError) else 'connection_or_verification_error'
            checkpoint(row['operation_id'], status='rejected' if rejected else 'unverified', code=code)
            message = str(exc) if isinstance(exc, EnrollmentError) else ('Chưa kết nối hoặc xác minh được máy.' if rejected else 'Chưa xác minh được kết quả. Hãy bấm Kiểm tra lại; không gửi lại ảnh.')
            raise HTTPException(409 if rejected else 502, message) from None
        finally:
            if client:
                client.close()

    @app.post('/v2/staff/{username}/face-id/enrollment/verify')
    def verify(username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            authorize(conn, ident)
            ensure_enrollment(conn)
            # A failed operation can belong to an employee since deleted or
            # disabled. Recovery still needs to release its precommit reservation;
            # finish() separately requires an active employee before mapping.
            row = conn.execute(text('''SELECT * FROM vera_facegate_enrollment WHERE lower(btrim(employee_username))=lower(btrim(:username))
                ORDER BY created_at DESC LIMIT 1'''), {'username': username}).mappings().first()
            if not row:
                raise HTTPException(404, 'Chưa có lượt đăng ký để kiểm tra.')
            row = dict(row)
            if row['status'] == 'verified':
                return public(row)
            if row['status'] == 'running' and (datetime.now(timezone.utc) - row['updated_at']).total_seconds() < 180:
                raise HTTPException(409, 'Lượt gửi ảnh đang chạy. Hãy chờ hoàn tất rồi kiểm tra lại.')
            if target(conn) != row['device_address'] or mapping_device_id() != row['device_id']:
                raise HTTPException(409, 'Cấu hình máy đã đổi; cần đối chiếu máy trước khi tiếp tục.')
            if row['status'] == 'running':
                # Fence the interrupted writer before any recovery I/O. Its next
                # checkpoint cannot upload/add or resurrect a closed journal.
                recovered = conn.execute(text('''UPDATE vera_facegate_enrollment SET status='unverified',
                    error_code='worker_interrupted',updated_at=NOW() WHERE operation_id=:op
                    AND status='running' AND updated_at=:updated RETURNING *'''),
                    {'op':row['operation_id'],'updated':row['updated_at']}).mappings().first()
                if not recovered:
                    raise HTTPException(409,'Lượt đăng ký vừa thay đổi. Hãy kiểm tra lại.')
                row = dict(recovered)
            ref = decode(row['registration_ref'], None)
        if row['status'] == 'rejected':
            return public(row)
        recover_precommit = row['status'] == 'unverified' and row['stage'] in {'preflight', 'uploading', 'uploaded'}
        if not recover_precommit and (not ref or row['stage'] not in {'committing', 'verified'}):
            raise HTTPException(409, 'Lượt gửi chưa xác định được kết quả. Giữ lượt này để đối chiếu, không gửi lặp.')
        client = None
        try:
            with facegate_endpoint('http://' + row['device_address']):
                client = FaceGateEnrollmentClient()
                client.login()
                if recover_precommit:
                    # The failed request never reached the durable committing
                    # checkpoint, so no profile add was issued. Read the complete
                    # device list before releasing its device-wide reservation.
                    profiles = client.profiles()
                    from vera_facegate_control_log import registration_ref
                    if any(p.get('utext') == 'vera:' + row['operation_id'] or
                           (ref and registration_ref(p) == ref) for p in profiles):
                        raise HTTPException(409, 'Máy có hồ sơ liên quan đến lượt này; cần đối chiếu trước khi mở đăng ký mới.')
                else:
                    profile = client.verify(row['device_name'], 'vera:' + row['operation_id'], ref)
            if recover_precommit:
                checkpoint(row['operation_id'], status='rejected', code='precommit_reconciled', expected_status='unverified')
                with engine_instance().begin() as conn:
                    current = conn.execute(text('SELECT * FROM vera_facegate_enrollment WHERE operation_id=:op'),
                                           {'op':row['operation_id']}).mappings().one()
                    return public(current)
            return finish(row, profile)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, 'Chưa xác minh được hồ sơ trên máy. VERA chưa xác nhận đăng ký thành công.') from None
        finally:
            if client:
                client.close()

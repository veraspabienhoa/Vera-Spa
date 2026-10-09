"""Durable enrollment journal; device I/O always outside database transactions."""
from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv4Network
import json
import re
import uuid

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from vera_facegate_control_log import facegate_endpoint, mapping_device_id, registration_ref
from vera_facegate_enrollment import FaceGateEnrollmentClient, EnrollmentError, UploadRejected, jpeg_photo, validate_device_name
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
    conn.execute(text("ALTER TABLE vera_facegate_enrollment ADD COLUMN IF NOT EXISTS operation_type text NOT NULL DEFAULT 'add'"))
    conn.execute(text('ALTER TABLE vera_facegate_enrollment ADD COLUMN IF NOT EXISTS previous_ref jsonb'))
    conn.execute(text('ALTER TABLE vera_facegate_enrollment ADD COLUMN IF NOT EXISTS device_token text'))
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
    result = {key: row.get(key) for key in ('operation_id', 'operation_type', 'status', 'stage', 'photo_sha256',
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

    def checkpoint(op, *, status='running', stage=None, ref=None, token=None, code=None, expected_status='running'):
        with engine_instance().begin() as conn:
            updated = conn.execute(text('''UPDATE vera_facegate_enrollment SET status=:status,
                stage=COALESCE(:stage,stage), registration_ref=COALESCE(CAST(:ref AS jsonb),registration_ref),
                device_token=COALESCE(:token,device_token), error_code=:code, updated_at=NOW()
                WHERE operation_id=:op AND status=:expected_status '''),
                {'op': op, 'status': status, 'stage': stage,
                 'ref': json.dumps(ref) if ref is not None else None, 'token': token,
                 'code': code, 'expected_status': expected_status})
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
            now = datetime.now(timezone.utc).isoformat()
            if row.get('operation_type', 'add') == 'replace':
                owners = [i for i, item in enumerate(existing)
                          if item.get('username', '').casefold() == row['employee_username'].casefold()]
                if len(owners) != 1:
                    raise HTTPException(409, 'Ánh xạ hồ sơ cũ đã thay đổi; chưa cập nhật ánh xạ mới.')
                pos = owners[0]
                old = existing[pos]
                previous_ref = decode(row.get('previous_ref'), None)
                if (old.get('profile_id') != row['profile_id']
                        or old.get('registration_ref') != previous_ref
                        or old.get('device_address') != row['device_address']
                        or old.get('confirmed_by') is None
                        or profile.get('profile_id') != row['profile_id']):
                    raise HTTPException(409, 'Hồ sơ hoặc ánh xạ cũ không còn khớp; chưa thay ảnh.')
                if any(i != pos and (item.get('profile_id') == profile['profile_id']
                                     or item.get('registration_ref') == profile['registration_ref'])
                       for i, item in enumerate(existing)):
                    raise HTTPException(409, 'Hồ sơ hoặc ảnh máy đang được ánh xạ cho nhân viên khác.')
                history = old.get('replaced_registration_refs', [])
                if not isinstance(history, list): history = []
                if previous_ref not in history: history.append(previous_ref)
                existing[pos] = {**old, **profile, 'username': row['employee_username'],
                                 'device_address': row['device_address'], 'confirmed_by': row['actor'],
                                 'confirmed_at': now, 'enrollment_operation_id': row['operation_id'],
                                 'replaced_registration_refs': history}
                value = existing
            else:
                assert_new_mapping(existing, row['employee_username'])
                if any(item.get('profile_id') == profile['profile_id'] or item.get('registration_ref') == profile['registration_ref'] for item in existing):
                    raise HTTPException(409, 'Hồ sơ hoặc ảnh máy đã gắn với nhân viên khác.')
                entry = {**profile, 'username': row['employee_username'], 'employee_code': '',
                         'device_address': row['device_address'], 'confirmed_by': row['actor'],
                         'confirmed_at': now, 'enrollment_operation_id': row['operation_id']}
                value = existing + [entry]
            conn.execute(text('''UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb),
                updated_by=:actor,updated_at=NOW(),revision=revision+1
                WHERE category='facegate' AND setting_key=:key'''),
                {'key': key, 'value': json.dumps(value, ensure_ascii=False), 'actor': row['actor']})
            result = conn.execute(text('''UPDATE vera_facegate_enrollment SET status='verified',
                stage='verified', profile_id=:uid, registration_ref=CAST(:ref AS jsonb),
                error_code=NULL, updated_at=NOW()
                WHERE operation_id=:op RETURNING *'''),
                {'op': row['operation_id'], 'uid': profile['profile_id'],
                 'ref': json.dumps(profile['registration_ref'])}).mappings().first()
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
            if not busy:
                current_mappings = mappings(conn, mapping_device_id())
                owned = [item for item in current_mappings
                         if item.get('username', '').casefold() == person['username'].casefold()]
                if len(owned) == 1 and owned[0].get('confirmed_by') and owned[0].get('device_address') == target(conn):
                    result['mapped_profile'] = {'profile_id': owned[0].get('profile_id'),
                                                'device_name': owned[0].get('device_name'),
                                                'registration_ref': owned[0].get('registration_ref')}
                    result['can_replace'] = True
                else:
                    result['can_replace'] = False
            return result

    @app.post('/v2/staff/{username}/face-id/enrollment')
    def enroll(username: str, body: EnrollmentInput, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            actor = authorize(conn, ident)
            conn.execute(text('SELECT pg_advisory_xact_lock(723491, 1)'))
            if conn.execute(text("SELECT to_regclass('vera_facegate_rename_job')")).scalar() and conn.execute(text("SELECT 1 FROM vera_facegate_rename_job WHERE status='pending' LIMIT 1")).scalar():
                raise HTTPException(409, 'Máy Face ID đang chờ đồng bộ tên nhân viên; hãy hoàn tất trước khi đăng ký hoặc thay ảnh.')
            person = employee(conn, username)
            username = person['username']
            address = target(conn)
            device_id = mapping_device_id()
            ensure_enrollment(conn)
            conn.execute(text('SELECT pg_advisory_xact_lock(723491, 1)'))
            prior = conn.execute(text('''SELECT * FROM vera_facegate_enrollment WHERE device_id=:device
                AND employee_username=:username AND status='verified' ORDER BY created_at DESC LIMIT 1'''),
                {'device': device_id, 'username': username}).mappings().first()
            mapped = [item for item in mappings(conn, device_id)
                      if item.get('username', '').casefold() == username.casefold()]
            operation_type = 'add'
            old_profile = None
            if prior:
                if prior['photo_sha256'] == body.photo_sha256 and prior['device_address'] == address:
                    if (len(mapped) == 1 and mapped[0].get('profile_id') == prior['profile_id']
                            and mapped[0].get('registration_ref') == decode(prior.get('registration_ref'), None)
                            and mapped[0].get('device_address') == address):
                        return public(prior)
                    raise HTTPException(409, 'Ánh xạ hiện tại không còn khớp lượt đăng ký; cần đối chiếu trước khi tiếp tục.')
                operation_type = 'replace'
                if len(mapped) != 1 or mapped[0].get('profile_id') != prior['profile_id']:
                    raise HTTPException(409, 'Ánh xạ hồ sơ cũ không còn khớp; cần kiểm tra lại trước khi thay ảnh.')
                old_profile = mapped[0]
            elif mapped:
                operation_type = 'replace'
                if len(mapped) != 1 or not mapped[0].get('confirmed_by'):
                    raise HTTPException(409, 'Nhân viên có nhiều hoặc chưa xác minh ánh xạ máy; cần đối chiếu trước khi thay ảnh.')
                old_profile = mapped[0]
            if operation_type == 'replace':
                try:
                    profile_id = int(old_profile.get('profile_id'))
                    old_ref = old_profile.get('registration_ref')
                    if (profile_id <= 0 or not isinstance(old_ref, dict)
                            or old_profile.get('device_address') != address):
                        raise ValueError()
                except (TypeError, ValueError):
                    raise HTTPException(409, 'Ánh xạ hồ sơ cũ chưa đủ thông tin để thay ảnh an toàn.') from None
            elif not body.confirmed:
                raise HTTPException(400, 'Cần xác nhận ảnh thuộc đúng nhân viên trước khi đăng ký lên máy.')
            busy = conn.execute(text("SELECT * FROM vera_facegate_enrollment WHERE device_id=:device AND status IN ('running','unverified')"),
                                {'device': device_id}).mappings().first()
            if busy:
                if busy['employee_username'] == username:
                    return public(busy)
                raise HTTPException(409, 'Máy đang có lượt đăng ký chưa xác minh. Hãy hoàn tất lượt đó trước.')
            if operation_type == 'add':
                assert_new_mapping(mappings(conn, device_id), username)
            from vera_web_v2_face_id import ensure_table
            ensure_table(conn)
            photo = conn.execute(text('SELECT content, content_type, sha256 FROM vera_employee_face_id WHERE employee_username=:username'),
                                 {'username': username}).mappings().first()
            if not photo or photo['sha256'] != body.photo_sha256:
                raise HTTPException(409, 'Ảnh đã thay đổi hoặc chưa lưu. Hãy tải lại ảnh trước khi đăng ký.')
            name = str((old_profile or {}).get('device_name') if operation_type == 'replace'
                       else username).strip()
            try:
                name = validate_device_name(name)
            except EnrollmentError as exc:
                raise HTTPException(400, str(exc)) from None
            original = bytes(photo['content'])
            row = {'operation_id': uuid.uuid4().hex, 'device_id': device_id, 'device_address': address,
                   'employee_username': username, 'photo_sha256': photo['sha256'], 'device_name': name,
                   'actor': actor, 'upload_session': str(uuid.uuid4().int % 90000000 + 10000000),
                   'operation_type': operation_type, 'profile_id': profile_id if operation_type == 'replace' else None,
                   'previous_ref': old_ref if operation_type == 'replace' else None}
            conn.execute(text('''INSERT INTO vera_facegate_enrollment
                (operation_id,device_id,device_address,employee_username,photo_sha256,device_name,actor,status,stage,upload_session,operation_type,profile_id,previous_ref)
                VALUES (:operation_id,:device_id,:device_address,:employee_username,:photo_sha256,:device_name,:actor,'running','preflight',:upload_session,:operation_type,:profile_id,CAST(:previous_ref AS jsonb))'''),
                {**row, 'previous_ref': json.dumps(row['previous_ref']) if row['previous_ref'] is not None else None})
        stage, client = 'preflight', None
        try:
            photo_bytes = jpeg_photo(original)
            with facegate_endpoint('http://' + address):
                client = FaceGateEnrollmentClient()
                client.login()
                profiles = client.profiles()
                if operation_type == 'replace':
                    matches = [p for p in profiles if p.get('uid') == str(row['profile_id'])]
                    if (len(matches) != 1 or norm(matches[0].get('uname')) != norm(name)
                            or norm(matches[0].get('uname')) != norm(old_profile.get('device_name'))
                            or registration_ref(matches[0]) != old_ref):
                        raise UploadRejected('profile_changed', 'Hồ sơ trên máy đã thay đổi; hãy đối chiếu lại trước khi cập nhật.')
                    device_profile = client.profile_details(row['profile_id'])
                    if (device_profile.get('uname') != matches[0].get('uname')
                            or device_profile.get('utext') != matches[0].get('utext')
                            or registration_ref(device_profile) != old_ref):
                        raise UploadRejected('profile_changed', 'Chi tiết hồ sơ trên máy không khớp ánh xạ; chưa thay ảnh.')
                else:
                    if any(norm(p.get('uname')) in {norm(username), norm(name)} for p in profiles):
                        raise UploadRejected('existing_profile', 'Máy đã có tên tương ứng. Hãy đối chiếu hồ sơ hiện có trước khi tạo mới.')
                    defaults = client.door_defaults()
                with engine_instance().begin() as conn:
                    authorize(conn, ident)
                    employee(conn, username)
                    if target(conn) != address or mapping_device_id() != device_id:
                        raise HTTPException(409, 'Máy đã đổi trong lúc chuẩn bị.')
                    if operation_type == 'add':
                        assert_new_mapping(mappings(conn, device_id), username)
                    else:
                        current = [item for item in mappings(conn, device_id)
                                   if item.get('username', '').casefold() == username.casefold()]
                        if (len(current) != 1 or current[0].get('profile_id') != row['profile_id']
                                or current[0].get('registration_ref') != old_ref
                                or current[0].get('device_address') != address
                                or not current[0].get('confirmed_by')):
                            raise HTTPException(409, 'Ánh xạ đã thay đổi trong lúc chuẩn bị cập nhật ảnh.')
                    current_sha = conn.execute(text('SELECT sha256 FROM vera_employee_face_id WHERE employee_username=:username'), {'username': username}).scalar()
                    if current_sha != body.photo_sha256:
                        raise HTTPException(409, 'Ảnh đã đổi trong lúc chuẩn bị.')
                # Durable checkpoint commits BEFORE each potentially mutating call.
                checkpoint(row['operation_id'], stage='uploading')
                stage = 'uploading'
                if operation_type == 'replace':
                    ref = client.upload(photo_bytes, row['upload_session'], profile_id=row['profile_id'])
                else:
                    ref = client.upload(photo_bytes, row['upload_session'])
                checkpoint(row['operation_id'], stage='uploaded', ref=ref)
                row['registration_ref'] = ref
                checkpoint(row['operation_id'], stage='committing',
                           token=matches[0].get('utext') if operation_type == 'replace' else None)
                stage = 'committing'
                if operation_type == 'replace':
                    client.update_photo(device_profile, ref)
                    profile = client.verify_replacement(row['profile_id'], name,
                                                        matches[0].get('utext'), ref)
                else:
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
                    if row.get('operation_type', 'add') == 'replace':
                        matches = [p for p in profiles if p.get('uid') == str(row['profile_id'])]
                        previous_ref = decode(row.get('previous_ref'), None)
                        if len(matches) != 1 or registration_ref(matches[0]) != previous_ref:
                            raise HTTPException(409, 'Hồ sơ trên máy đã đổi trong lượt cập nhật; cần đối chiếu thủ công.')
                    elif any(p.get('utext') == 'vera:' + row['operation_id'] or
                             (ref and registration_ref(p) == ref) for p in profiles):
                        raise HTTPException(409, 'Máy có hồ sơ liên quan đến lượt này; cần đối chiếu trước khi mở đăng ký mới.')
                else:
                    if row.get('operation_type', 'add') == 'replace':
                        if row.get('device_token') is None:
                            raise HTTPException(409, 'Thiếu dấu nhận diện hồ sơ cũ; cần đối chiếu trên máy.')
                        profile = client.verify_replacement(row['profile_id'], row['device_name'],
                                                            row['device_token'], ref)
                    else:
                        profile = client.verify(row['device_name'], 'vera:' + row['operation_id'], ref)
            if recover_precommit:
                # Reconciliation releases the reservation, but is not the cause
                # of the failed upload. Keep that cause available after recovery.
                checkpoint(row['operation_id'], status='rejected',
                           code=row.get('error_code') or 'precommit_reconciled', expected_status='unverified')
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

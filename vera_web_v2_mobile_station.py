"""Authenticated mobile camera/scanner station and separately sourced attendance evidence.

Browser devices communicate over the existing HTTPS API. No Web Bluetooth or
Wi-Fi Direct connection, facial recognition or FaceGate hardware enrollment is implied.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import UUID
import hashlib

from fastapi import Depends, HTTPException, Query, Request, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import text

from vera_web_v2_devices import read_registry

VN = timezone(timedelta(hours=7))
MAX_IMAGE = 2 * 1024 * 1024


def ensure_station_table(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_mobile_station_event (
        id uuid PRIMARY KEY, device_id text NOT NULL, operator text NOT NULL,
        event_type text NOT NULL, employee_username text NOT NULL DEFAULT '',
        barcode text NOT NULL DEFAULT '', image bytea, image_sha256 text,
        occurred_at timestamptz NOT NULL DEFAULT NOW(),
        confirmed_by text, confirmed_at timestamptz
    )'''))
    conn.execute(text('''CREATE INDEX IF NOT EXISTS vera_mobile_station_event_recent
        ON vera_mobile_station_event (occurred_at DESC)'''))


def install_mobile_station_routes(app, *, engine_instance, current_identity, identity_type, require_feature):
    def access(ident, feature):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, feature)

    def station(conn, device_id):
        device = next((item for item in read_registry(conn)['devices'] if item['id'] == device_id), None)
        if not device or not device['enabled'] or device['kind'] not in {'camera', 'scanner', 'faceid'}:
            raise HTTPException(403, 'Thiết bị chưa được đăng ký hoặc đã ngừng sử dụng.')
        return device

    @app.post('/v2/devices/mobile-station/{device_id}/events/{event_id}')
    async def capture(device_id: str, event_id: UUID, request: Request,
                      event_type: str = Query(..., pattern='^(photo|scan|checkin)$'),
                      employee_username: str = Query('', max_length=200), barcode: str = Query('', max_length=256),
                      ident: identity_type = Depends(current_identity)):
        access(ident, 'device_station_operate')
        if event_type == 'checkin' and not employee_username.strip():
            raise HTTPException(400, 'Chọn nhân viên trước khi chấm công.')
        if event_type == 'scan' and not barcode.strip():
            raise HTTPException(400, 'Nhập hoặc quét mã trước khi gửi.')
        photo = bytearray()
        async for chunk in request.stream():
            photo.extend(chunk)
            if len(photo) > MAX_IMAGE:
                raise HTTPException(413, 'Ảnh vượt quá 2 MB.')
        if event_type in {'photo', 'checkin'} and not photo:
            raise HTTPException(400, 'Cần chụp ảnh trước khi gửi.')
        if photo:
            if request.headers.get('content-type', '').split(';')[0].lower() != 'image/jpeg':
                raise HTTPException(400, 'Chỉ nhận ảnh JPEG.')
            try:
                with Image.open(BytesIO(photo)) as image:
                    if image.format != 'JPEG' or image.width * image.height > 12_000_000:
                        raise ValueError('bad image')
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise HTTPException(400, 'Ảnh JPEG không hợp lệ.') from exc
        with engine_instance().begin() as conn:
            station(conn, device_id)
            ensure_station_table(conn)
            conn.execute(text("DELETE FROM vera_mobile_station_event WHERE occurred_at < NOW() - INTERVAL '7 days'"))
            row = conn.execute(text('SELECT device_id,operator,event_type,employee_username,barcode,image_sha256,occurred_at FROM vera_mobile_station_event WHERE id=:id'), {'id': str(event_id)}).mappings().first()
            digest = hashlib.sha256(photo).hexdigest() if photo else None
            actor = ident.employee_username
            if row:
                if (row['device_id'], row['operator'], row['event_type'], row['employee_username'], row['barcode'], row['image_sha256']) != (device_id, actor, event_type, employee_username.strip(), barcode.strip(), digest):
                    raise HTTPException(409, 'Mã thao tác đã được dùng cho nội dung khác.')
                return {'id': str(event_id), 'occurred_at': row['occurred_at'], 'saved': True}
            if employee_username.strip():
                found = conn.execute(text("SELECT username FROM employees WHERE lower(btrim(username))=lower(btrim(:username)) AND COALESCE(payload->>'__deleted','false') <> 'true'"), {'username': employee_username.strip()}).scalar()
                if not found:
                    raise HTTPException(404, 'Không tìm thấy nhân viên.')
                employee_username = found
            now = datetime.now(VN)
            conn.execute(text('''INSERT INTO vera_mobile_station_event
                (id,device_id,operator,event_type,employee_username,barcode,image,image_sha256,occurred_at)
                VALUES (:id,:device,:actor,:type,:employee,:barcode,:image,:digest,:occurred)'''),
                {'id': str(event_id), 'device': device_id, 'actor': actor, 'type': event_type,
                 'employee': employee_username.strip(), 'barcode': barcode.strip(), 'image': bytes(photo) if photo else None,
                 'digest': digest, 'occurred': now})
            # Keep mobile evidence separate until an Admin reviews the photo
            # and explicitly confirms the employee in the history view.
        return {'id': str(event_id), 'occurred_at': now, 'saved': True}

    @app.get('/v2/devices/mobile-station/events')
    def events(ident: identity_type = Depends(current_identity)):
        access(ident, 'device_station_operate')
        with engine_instance().begin() as conn:
            ensure_station_table(conn)
            conn.execute(text("DELETE FROM vera_mobile_station_event WHERE occurred_at < NOW() - INTERVAL '7 days'"))
            rows = conn.execute(text('''SELECT id,device_id,operator,event_type,employee_username,barcode,
                image_sha256 IS NOT NULL AS has_image, occurred_at, confirmed_by, confirmed_at FROM vera_mobile_station_event
                WHERE occurred_at >= NOW() - INTERVAL '7 days' ORDER BY occurred_at DESC LIMIT 100''')).mappings().all()
        return {'records': [dict(row) for row in rows]}

    @app.post('/v2/devices/mobile-station/events/{event_id}/confirm')
    def confirm_checkin(event_id: UUID, ident: identity_type = Depends(current_identity)):
        access(ident, 'device_checkin_confirm')
        with engine_instance().begin() as conn:
            ensure_station_table(conn)
            row = conn.execute(text('''SELECT device_id,event_type,employee_username,occurred_at,confirmed_at
                FROM vera_mobile_station_event WHERE id=:id FOR UPDATE'''), {'id': str(event_id)}).mappings().first()
            if not row or row['event_type'] != 'checkin' or not row['employee_username']:
                raise HTTPException(404, 'Không tìm thấy lần chấm công cần xác nhận.')
            if row['confirmed_at']:
                return {'ok': True, 'already_confirmed': True}
            station(conn, row['device_id'])
            from vera_web_v2_hr_enhancements import record_checkin
            result = record_checkin(conn, username=row['employee_username'], checkin_at=row['occurred_at'],
                                    source='mobile_admin_confirmed', external_id=str(event_id),
                                    payload={'station_device_id': row['device_id'], 'event_id': str(event_id)},
                                    actor=ident.employee_username)
            conn.execute(text('''UPDATE vera_mobile_station_event SET confirmed_by=:actor,confirmed_at=NOW()
                WHERE id=:id'''), {'actor': ident.employee_username, 'id': str(event_id)})
        return {'ok': True, 'attendance_log_id': result.get('attendance_log_id')}

    @app.get('/v2/devices/mobile-station/events/{event_id}/image')
    def event_image(event_id: UUID, ident: identity_type = Depends(current_identity)):
        access(ident, 'device_station_operate')
        with engine_instance().begin() as conn:
            ensure_station_table(conn)
            photo = conn.execute(text('SELECT image FROM vera_mobile_station_event WHERE id=:id AND occurred_at >= NOW() - INTERVAL \'7 days\''), {'id': str(event_id)}).scalar()
        if not photo:
            raise HTTPException(404, 'Không tìm thấy ảnh.')
        return Response(bytes(photo), media_type='image/jpeg', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

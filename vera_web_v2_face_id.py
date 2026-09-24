"""Separate, permission-controlled Face ID photos; never part of profile PDF media.

Storing a photo is not device enrollment. No biometric matching or attendance
cutover is performed by these routes.
"""
from datetime import date
from io import BytesIO
import hashlib
import unicodedata
from collections import Counter
from pydantic import BaseModel, Field

from fastapi import Depends, HTTPException, Request, Response
from PIL import Image, ImageOps
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

HEADERS = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}


def ensure_table(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_employee_face_id (
        employee_username text PRIMARY KEY,
        content bytea NOT NULL, content_type text NOT NULL,
        size_bytes integer NOT NULL, sha256 text NOT NULL,
        updated_by text NOT NULL, updated_at timestamptz NOT NULL DEFAULT NOW()
    )'''))


def validate_photo(content, content_type):
    from vera_web_v2_staff_security import MAX_IDENTITY_BYTES, ALLOWED_IMAGE_TYPES, _valid_image, _image_dimensions
    if content_type not in ALLOWED_IMAGE_TYPES or not _valid_image(content, content_type):
        raise HTTPException(400, 'Chỉ chấp nhận ảnh JPEG, PNG hoặc WebP hợp lệ.')
    if len(content) > MAX_IDENTITY_BYTES:
        raise HTTPException(413, 'Ảnh vượt dung lượng cho phép; hãy nén ảnh trước khi lưu.')
    width, height = _image_dimensions(content)
    if abs(width / height - 0.75) > 0.035:
        raise HTTPException(400, 'ẢNH FACE ID cần được cắt theo tỷ lệ 3:4.')


class BatchPlanRequest(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=50)


def filename_key(filename):
    if not isinstance(filename, str) or len(filename) > 255 or '/' in filename or '\\' in filename:
        return None
    stem, dot, extension = filename.rpartition('.')
    if not dot or extension.casefold() not in {'jpg', 'jpeg', 'png', 'webp'} or not stem.strip():
        return None
    return unicodedata.normalize('NFC', stem.strip()).casefold()


def batch_plan(filenames, employees):
    # Match username only, preserving Vietnamese accents; never match full_name.
    keys = [filename_key(name) for name in filenames]
    counts = Counter(key for key in keys if key is not None)
    index = {}
    for row in employees:
        key = unicodedata.normalize('NFC', row['username'].strip()).casefold()
        index.setdefault(key, []).append(row)
    result = []
    for filename, key in zip(filenames, keys):
        matches = index.get(key, [])
        status = ('invalid_filename' if key is None else 'duplicate_filename' if counts[key] > 1
                  else 'not_found' if not matches else 'ambiguous' if len(matches) != 1 else 'ready')
        match = matches[0] if status == 'ready' else {}
        result.append({'filename': filename, 'status': status, 'username': match.get('username'),
                       'existing_sha256': match.get('sha256')})
    return result


def install_face_id_routes(app, *, engine_instance, current_identity, require_feature, identity_type):
    def access(conn, ident, username, *, write=False):
        require_feature(conn, ident, 'employee_face_id_manage' if write else 'employee_face_id_view')
        row = conn.execute(text('''SELECT username FROM employees
            WHERE lower(btrim(username))=lower(btrim(:username))
            AND COALESCE(payload->>'__deleted','false') <> 'true'
            LIMIT 1''' + (' FOR UPDATE' if write else '')), {'username': username}).mappings().first()
        if not row:
            raise HTTPException(404, 'Không tìm thấy nhân viên.')
        return row['username']

    def can_manage(conn, ident):
        try:
            require_feature(conn, ident, 'employee_face_id_manage')
            return True
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            return False

    @app.post('/v2/face-id/batch-plan')
    def preview_batch(body: BatchPlanRequest, ident: identity_type = Depends(current_identity)):
        if any(len(name) > 255 for name in body.filenames):
            raise HTTPException(400, 'Tên file quá dài.')
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'employee_face_id_manage')
            ensure_table(conn)
            employees = conn.execute(text("""SELECT e.username, f.sha256
                FROM employees e LEFT JOIN vera_employee_face_id f ON f.employee_username=e.username
                WHERE COALESCE(e.payload->>'__deleted','false') <> 'true'""")).mappings().all()
        return {'records': batch_plan(body.filenames, employees)}

    @app.get('/v2/staff/{username}/face-id')
    def metadata(username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            username = access(conn, ident, username)
            editable = can_manage(conn, ident)
            ensure_table(conn)
            row = conn.execute(text('''SELECT size_bytes, sha256, updated_at
                FROM vera_employee_face_id WHERE employee_username=:username'''), {'username': username}).mappings().first()
        return {'photo': dict(row) if row else None, 'can_manage': editable,
                'device_enrollment': 'not_verified'}

    @app.get('/v2/staff/{username}/face-id/image')
    def photo(username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            username = access(conn, ident, username)
            ensure_table(conn)
            row = conn.execute(text('SELECT content, content_type FROM vera_employee_face_id WHERE employee_username=:username'), {'username': username}).mappings().first()
        if not row:
            raise HTTPException(404, 'Chưa có ẢNH FACE ID.')
        return Response(bytes(row['content']), media_type=row['content_type'], headers=HEADERS)

    @app.get('/v2/staff/{username}/face-id/portrait-source')
    def portrait_source(username: str, ident: identity_type = Depends(current_identity)):
        from vera_web_v2_staff_security import _ensure_identity_table
        with engine_instance().begin() as conn:
            username = access(conn, ident, username, write=True)
            _ensure_identity_table(conn)
            row = conn.execute(text("SELECT content, content_type FROM vera_employee_identity_document WHERE employee_username=:username AND side='portrait'"), {'username': username}).mappings().first()
        if not row:
            raise HTTPException(404, 'Nhân viên chưa có ảnh đại diện.')
        return Response(bytes(row['content']), media_type=row['content_type'], headers=HEADERS)

    def save(username, ident, content, content_type, if_match=None, if_none_match=None, filename=None):
        validate_photo(content, content_type)
        with engine_instance().begin() as conn:
            username = access(conn, ident, username, write=True)
            ensure_table(conn)
            if filename is not None:
                employees = conn.execute(text("SELECT username FROM employees WHERE COALESCE(payload->>'__deleted','false') <> 'true'")).mappings().all()
                plan = batch_plan([filename], employees)[0]
                if plan['status'] != 'ready' or plan['username'] != username:
                    raise HTTPException(409, 'Tên file không còn khớp duy nhất với tên nhân viên. Hãy chọn lại lô ảnh.')
                if not if_match and if_none_match != '*':
                    raise HTTPException(400, 'Cần kiểm tra ảnh hiện có trước khi tải hàng loạt.')
            if if_match is not None or if_none_match is not None:
                existing = conn.execute(text('SELECT sha256 FROM vera_employee_face_id WHERE employee_username=:username'), {'username': username}).scalar()
                # Repeating the exact successful upload after a lost response is
                # safe: no rewrite and no accidental retry conflict.
                digest = hashlib.sha256(content).hexdigest()
                if existing == digest:
                    return {'ok': True, 'message': 'Ảnh này đã được lưu.'}
                if (if_none_match == '*' and existing) or (if_match is not None and existing != if_match.strip('"')):
                    raise HTTPException(409, 'Ảnh FACE ID đã thay đổi. Hãy chọn lại lô ảnh để kiểm tra trước khi thay.')
            conn.execute(text('''INSERT INTO vera_employee_face_id
                (employee_username,content,content_type,size_bytes,sha256,updated_by)
                VALUES (:username,:content,:type,:size,:sha,:actor)
                ON CONFLICT(employee_username) DO UPDATE SET content=EXCLUDED.content,
                content_type=EXCLUDED.content_type,size_bytes=EXCLUDED.size_bytes,
                sha256=EXCLUDED.sha256,updated_by=EXCLUDED.updated_by,updated_at=NOW()'''),
                {'username': username, 'content': content, 'type': content_type,
                 'size': len(content), 'sha': hashlib.sha256(content).hexdigest(),
                 'actor': str(getattr(ident, 'employee_username', ''))})
        return {'ok': True, 'message': 'Đã lưu ẢNH FACE ID trong VERA SPA. Chưa xác minh đăng ký ảnh trên thiết bị.'}

    @app.put('/v2/staff/{username}/face-id/image')
    async def upload(username: str, request: Request, ident: identity_type = Depends(current_identity)):
        from vera_web_v2_staff_security import MAX_IDENTITY_BYTES
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_IDENTITY_BYTES:
                raise HTTPException(413, 'Ảnh quá lớn; hãy nén ảnh trước khi lưu.')
        return await run_in_threadpool(save, username, ident, bytes(content), request.headers.get('content-type', '').split(';')[0].lower(),
                                       request.headers.get('if-match'), request.headers.get('if-none-match'), request.query_params.get('filename'))

    @app.delete('/v2/staff/{username}/face-id/image')
    def delete(username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            username = access(conn, ident, username, write=True)
            ensure_table(conn)
            conn.execute(text('DELETE FROM vera_employee_face_id WHERE employee_username=:username'), {'username': username})
        return {'ok': True, 'message': 'Đã xóa ẢNH FACE ID trong VERA SPA.'}

    @app.get('/v2/staff/{username}/face-id/captures')
    def captures(username: str, day: date, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            access(conn, ident, username, write=True)
        from vera_facegate_control_log import fetch_capture_log
        try:
            result = fetch_capture_log(day.isoformat(), day.isoformat())
        except (RuntimeError, ValueError, ConnectionError) as exc:
            raise HTTPException(503, 'Không đọc được ảnh chụp từ thiết bị FaceID.') from exc
        return {'records': [{'event_id': r['event_id'], 'occurred_at': r['occurred_at']} for r in result['records'] if r.get('image_available')],
                'identity_verified': False, 'truncated': bool(result.get('truncated'))}

    @app.get('/v2/staff/{username}/face-id/capture-image')
    def capture_image(username: str, day: date, event_id: int, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            access(conn, ident, username, write=True)
        from vera_facegate_control_log import fetch_capture_log, fetch_capture_image
        try:
            records = fetch_capture_log(day.isoformat(), day.isoformat())['records']
            matches = [r for r in records if r['event_id'] == event_id and r.get('image_available')]
            if len(matches) != 1:
                raise HTTPException(409, 'Ảnh không còn duy nhất trong danh sách. Hãy tải lại.')
            content, _ = fetch_capture_image(matches[0]['image_ref'])
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > 24_000_000:
                    raise ValueError('image too large')
                output = BytesIO()
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((1600, 1600))
                image.save(output, format='JPEG', quality=90)
            return Response(output.getvalue(), media_type='image/jpeg', headers=HEADERS)
        except (RuntimeError, ValueError, ConnectionError, OSError) as exc:
            raise HTTPException(503, 'Không tải được ảnh chụp từ thiết bị FaceID.') from exc

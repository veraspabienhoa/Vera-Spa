"""Signed website inbox, independent of Live Tour state and its locks."""
from datetime import date
from typing import Literal
from uuid import UUID
import hashlib
import hmac
import json
import os
import re
import time

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import text

ROLES = {'admin', 'quanly', 'letan'}
MAX_BODY = 32768


class WebsiteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    event_id: UUID
    kind: Literal['booking', 'contact']
    customer_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=9, max_length=20)
    appointment_date: date | None = None
    appointment_time: str | None = Field(default=None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    service: str = Field(default='', max_length=500)
    guests: int | None = Field(default=None, ge=1, le=50, strict=True)
    message: str = Field(default='', max_length=4000)

    @field_validator('phone')
    @classmethod
    def phone_format(cls, value):
        if not re.fullmatch(r'\+?[0-9 () .-]+', value) or not 9 <= len(re.sub(r'\D', '', value)) <= 15:
            raise ValueError('Invalid phone')
        return value

    @model_validator(mode='after')
    def required_booking_fields(self):
        if self.kind == 'booking' and not all((self.appointment_date, self.appointment_time, self.service, self.guests)):
            raise ValueError('Missing booking fields')
        if self.kind == 'contact' and not self.message:
            raise ValueError('Missing message')
        return self


class InboxUpdate(BaseModel):
    status: Literal['new', 'confirmed', 'handled', 'cancelled']
    note: str = Field(default='', max_length=2000)
    revision: int = Field(ge=0)


def verify_signature(body, timestamp, signature, secret, now=None):
    if len(secret) < 32:
        raise HTTPException(503, 'Kênh nhận booking chưa được cấu hình.')
    if not re.fullmatch(r'\d{10}', timestamp or '') or abs((time.time() if now is None else now) - int(timestamp)) > 300:
        raise HTTPException(401, 'Chữ ký không hợp lệ hoặc đã hết hạn.')
    expected = hmac.new(secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    if not re.fullmatch(r'[0-9a-f]{64}', signature or '') or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, 'Chữ ký không hợp lệ hoặc đã hết hạn.')


def ensure_schema(conn):
    if conn.execute(text("SELECT to_regclass('vera_online_booking_seen')")).scalar_one_or_none():
        return
    conn.execute(text("SELECT pg_advisory_xact_lock(726409291)"))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_online_booking (
      id bigserial PRIMARY KEY, event_id uuid UNIQUE NOT NULL, fingerprint text NOT NULL,
      kind text NOT NULL CHECK(kind IN ('booking','contact')), customer_name text NOT NULL,
      phone text NOT NULL, appointment_date date, appointment_time text, service text NOT NULL,
      guests integer, message text NOT NULL, status text NOT NULL DEFAULT 'new'
        CHECK(status IN ('new','confirmed','handled','cancelled')),
      note text NOT NULL DEFAULT '', revision integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      updated_by text NOT NULL DEFAULT '')'''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS vera_online_booking_status_idx ON vera_online_booking(status,id)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS vera_online_booking_date_idx ON vera_online_booking(appointment_date,id)'))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_online_booking_seen (
      booking_id bigint NOT NULL REFERENCES vera_online_booking(id), actor text NOT NULL,
      seen_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(booking_id,actor))'''))
    for table in ('vera_online_booking', 'vera_online_booking_seen'):
        conn.execute(text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
        conn.execute(text(f'REVOKE ALL ON {table} FROM PUBLIC'))
        for role in ('anon', 'authenticated'):
            if conn.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}).scalar():
                conn.execute(text(f'REVOKE ALL ON {table} FROM {role}'))


def ingest(conn, payload):
    values = payload.model_dump(mode='json')
    fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    values['fingerprint'] = fingerprint
    row = conn.execute(text('''INSERT INTO vera_online_booking
      (event_id,fingerprint,kind,customer_name,phone,appointment_date,appointment_time,service,guests,message)
      VALUES(CAST(:event_id AS uuid),:fingerprint,:kind,:customer_name,:phone,CAST(:appointment_date AS date),
      :appointment_time,:service,:guests,:message) ON CONFLICT(event_id) DO NOTHING RETURNING id'''), values).scalar_one_or_none()
    if row is not None:
        return {'ok': True, 'id': row, 'duplicate': False}
    prior = conn.execute(text('SELECT id,fingerprint FROM vera_online_booking WHERE event_id=CAST(:event_id AS uuid)'), values).mappings().one()
    if prior['fingerprint'] != fingerprint:
        raise HTTPException(409, 'Mã yêu cầu đã được dùng cho nội dung khác.')
    return {'ok': True, 'id': prior['id'], 'duplicate': True}


PUBLIC_COLUMNS = 'b.id,b.kind,b.customer_name,b.phone,b.appointment_date,b.appointment_time,b.service,b.guests,b.message,b.status,b.note,b.revision,b.created_at,b.updated_at,b.updated_by'


def install_online_booking_routes(app, *, engine_instance, current_identity):
    if getattr(app.state, 'online_booking_installed', False):
        return

    def authorized(ident=Depends(current_identity)):
        if ident.role not in ROLES or ident.must_change_password:
            raise HTTPException(403, 'Chỉ Admin, Quản lý và Lễ tân được xem Booking online.')
        return ident

    @app.post('/v2/integrations/website/requests')
    async def receive(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                raise HTTPException(413, 'Yêu cầu quá lớn.')
        verify_signature(bytes(body), request.headers.get('X-Vera-Timestamp'),
                         request.headers.get('X-Vera-Signature'), os.getenv('VERA_WEBSITE_WEBHOOK_SECRET', ''))
        try:
            payload = WebsiteRequest.model_validate_json(bytes(body))
        except ValidationError:
            # Never echo customer data from validation errors into responses/logs.
            raise HTTPException(422, 'Thông tin booking không hợp lệ.') from None
        # Blocking DB work must not occupy the ASGI event loop.
        from starlette.concurrency import run_in_threadpool
        def save():
            with engine_instance().begin() as conn:
                ensure_schema(conn)
                return ingest(conn, payload)
        return await run_in_threadpool(save)

    @app.get('/v2/online-bookings')
    def listing(page: int = Query(1, ge=1, le=100000), limit: int = Query(25, ge=1, le=100),
                status: Literal['', 'new', 'confirmed', 'handled', 'cancelled'] = '',
                kind: Literal['', 'booking', 'contact'] = '', q: str = Query('', max_length=100),
                ident=Depends(authorized)):
        where = "WHERE (:status='' OR b.status=:status) AND (:kind='' OR b.kind=:kind) AND (:q='' OR b.customer_name ILIKE :search OR b.phone ILIKE :search)"
        params = dict(status=status, kind=kind, q=q.strip(), search='%'+q.strip()+'%', limit=limit, offset=(page-1)*limit)
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            total = conn.execute(text('SELECT count(*) FROM vera_online_booking b '+where), params).scalar_one()
            rows = conn.execute(text(f'SELECT {PUBLIC_COLUMNS} FROM vera_online_booking b '+where+' ORDER BY b.id DESC LIMIT :limit OFFSET :offset'), params).mappings().all()
        return {'rows': [dict(row) for row in rows], 'total': total, 'page': page, 'limit': limit}

    @app.get('/v2/online-bookings/unread')
    def unread(ident=Depends(authorized)):
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            rows = conn.execute(text(f'''SELECT {PUBLIC_COLUMNS} FROM vera_online_booking b
              WHERE b.status='new' AND NOT EXISTS(SELECT 1 FROM vera_online_booking_seen s
                WHERE s.booking_id=b.id AND s.actor=:actor) ORDER BY b.id LIMIT 20'''),
                {'actor': ident.auth_user_id}).mappings().all()
        return {'rows': [dict(row) for row in rows]}

    @app.post('/v2/online-bookings/{booking_id}/seen')
    def seen(booking_id: int, ident=Depends(authorized)):
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            conn.execute(text('''INSERT INTO vera_online_booking_seen(booking_id,actor)
              SELECT id,:actor FROM vera_online_booking WHERE id=:id ON CONFLICT DO NOTHING'''),
              {'id': booking_id, 'actor': ident.auth_user_id})
        return {'ok': True}

    @app.patch('/v2/online-bookings/{booking_id}')
    def update(booking_id: int, payload: InboxUpdate, ident=Depends(authorized)):
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            row = conn.execute(text('''UPDATE vera_online_booking SET status=:status,note=:note,
              revision=revision+1,updated_at=now(),updated_by=:actor WHERE id=:id AND revision=:revision
              RETURNING id,revision'''), {**payload.model_dump(), 'id': booking_id, 'actor': ident.employee_username}).mappings().first()
            if not row:
                raise HTTPException(409, 'Yêu cầu đã thay đổi. Hãy tải lại trước khi lưu.')
        return dict(row)

    app.state.online_booking_installed = True

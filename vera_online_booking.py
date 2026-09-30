"""Signed booking inbox with Live Tour synchronization after inbox commits."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID
import hashlib
import hmac
import json
import os
import re
import time
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import text

ROLES = {'admin', 'quanly', 'letan'}
VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
MAX_BODY = 32768
# Keep the same bounded window for count and rows, before pagination. Compare
# full Vietnam timestamps so the two-hour lookback also crosses midnight.
UPCOMING_WINDOW_SQL = "b.kind='booking' AND b.status IN ('new','confirmed') AND (b.appointment_date + CAST(b.appointment_time AS time)) >= ((CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh') - INTERVAL '2 hours')"


class WebsiteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    event_id: UUID
    kind: Literal['booking', 'contact']
    customer_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(default='', max_length=20)
    appointment_date: date | None = None
    appointment_time: str | None = Field(default=None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    service: str = Field(default='', max_length=500)
    guests: int | None = Field(default=None, ge=1, le=50, strict=True)
    requested_staff: str = Field(default='', max_length=100)
    message: str = Field(default='', max_length=4000)

    @field_validator('phone')
    @classmethod
    def phone_format(cls, value):
        if not value:
            return value
        if not re.fullmatch(r'\+?[0-9 () .-]+', value) or not 9 <= len(re.sub(r'\D', '', value)) <= 15:
            raise ValueError('Invalid phone')
        return value

    @model_validator(mode='after')
    def required_booking_fields(self):
        if self.kind == 'booking' and not all((self.appointment_date, self.appointment_time, self.guests)):
            raise ValueError('Missing booking fields')
        if self.kind == 'contact' and (not self.message or not self.phone):
            raise ValueError('Missing message')
        return self


class ManualBookingRequest(WebsiteRequest):
    kind: Literal['booking'] = 'booking'
    phone: str = Field(default='', max_length=20)


class BookingDelete(BaseModel):
    revision: int = Field(ge=0)


class InboxUpdate(BaseModel):
    status: Literal['new', 'confirmed', 'handled', 'cancelled']
    note: str = Field(default='', max_length=2000)
    revision: int = Field(ge=0)
    booking: ManualBookingRequest | None = None


def verify_signature(body, timestamp, signature, secret, now=None):
    if len(secret) < 32:
        raise HTTPException(503, 'Kênh nhận booking chưa được cấu hình.')
    if not re.fullmatch(r'\d{10}', timestamp or '') or abs((time.time() if now is None else now) - int(timestamp)) > 300:
        raise HTTPException(401, 'Chữ ký không hợp lệ hoặc đã hết hạn.')
    expected = hmac.new(secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    if not re.fullmatch(r'[0-9a-f]{64}', signature or '') or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, 'Chữ ký không hợp lệ hoặc đã hết hạn.')


def ensure_schema(conn):
    conn.execute(text("SELECT pg_advisory_xact_lock(726409291)"))
    if conn.execute(text("SELECT to_regclass('vera_online_booking')")).scalar_one_or_none():
        conn.execute(text("ALTER TABLE vera_online_booking ADD COLUMN IF NOT EXISTS requested_staff text NOT NULL DEFAULT ''"))
        conn.execute(text("ALTER TABLE vera_online_booking ADD COLUMN IF NOT EXISTS deleted boolean NOT NULL DEFAULT false"))
        return
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_online_booking (
      id bigserial PRIMARY KEY, event_id uuid UNIQUE NOT NULL, fingerprint text NOT NULL,
      kind text NOT NULL CHECK(kind IN ('booking','contact')), customer_name text NOT NULL,
      phone text NOT NULL, appointment_date date, appointment_time text, service text NOT NULL,
      requested_staff text NOT NULL DEFAULT '',
      guests integer, message text NOT NULL, status text NOT NULL DEFAULT 'new'
        CHECK(status IN ('new','confirmed','handled','cancelled')),
      note text NOT NULL DEFAULT '', revision integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      updated_by text NOT NULL DEFAULT '')'''))
    conn.execute(text("ALTER TABLE vera_online_booking ADD COLUMN IF NOT EXISTS deleted boolean NOT NULL DEFAULT false"))
    conn.execute(text('CREATE INDEX IF NOT EXISTS vera_online_booking_status_idx ON vera_online_booking(status,id)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS vera_online_booking_date_idx ON vera_online_booking(appointment_date,id)'))
    conn.execute(text("ALTER TABLE vera_online_booking ADD COLUMN IF NOT EXISTS requested_staff text NOT NULL DEFAULT ''"))
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
      (event_id,fingerprint,kind,customer_name,phone,appointment_date,appointment_time,service,guests,requested_staff,message)
      VALUES(CAST(:event_id AS uuid),:fingerprint,:kind,:customer_name,:phone,CAST(:appointment_date AS date),
      :appointment_time,:service,:guests,:requested_staff,:message) ON CONFLICT(event_id) DO NOTHING RETURNING id'''), values).scalar_one_or_none()
    if row is not None:
        return {'ok': True, 'id': row, 'duplicate': False}
    prior = conn.execute(text('SELECT id,fingerprint FROM vera_online_booking WHERE event_id=CAST(:event_id AS uuid)'), values).mappings().one()
    if prior['fingerprint'] != fingerprint:
        raise HTTPException(409, 'Mã yêu cầu đã được dùng cho nội dung khác.')
    return {'ok': True, 'id': prior['id'], 'duplicate': True}


PUBLIC_COLUMNS = 'b.id,b.kind,b.customer_name,b.phone,b.appointment_date,b.appointment_time,b.service,b.guests,b.requested_staff,b.message,b.status,b.note,b.revision,b.created_at,b.updated_at,b.updated_by'


def install_online_booking_routes(app, *, engine_instance, current_identity,
                                  working_staff_provider=None, appointment_writer=None):
    if getattr(app.state, 'online_booking_installed', False):
        return
    working_staff_provider = working_staff_provider or getattr(app.state, 'website_booking_staff_provider', None)
    appointment_writer = appointment_writer or getattr(app.state, 'website_booking_appointment_writer', None)

    def authorized(ident=Depends(current_identity)):
        if ident.role not in ROLES or ident.must_change_password:
            raise HTTPException(403, 'Chỉ Admin, Quản lý và Lễ tân được xem Booking online.')
        return ident

    def validate_staff(payload):
        if not payload.requested_staff:
            return
        if not working_staff_provider:
            raise HTTPException(503, 'Danh sách nhân viên đi làm chưa sẵn sàng.')
        available = working_staff_provider().get('employees', [])
        if payload.requested_staff not in {row.get('value') for row in available}:
            raise HTTPException(422, 'Nhân viên yêu cầu không đi làm hoặc đang nghỉ phép hôm nay. Hãy chọn lại.')

    def sync_appointments(payload=None):
        sync = getattr(app.state, 'online_booking_appointment_sync', None)
        if sync:
            return sync()
        if payload and payload.requested_staff and payload.appointment_date == datetime.now(VN_TZ).date() and appointment_writer:
            return appointment_writer(payload.requested_staff, payload.appointment_date, payload.appointment_time)
        return None

    @app.get('/v2/online-bookings/staff')
    def staff(ident=Depends(authorized)):
        if not working_staff_provider:
            raise HTTPException(503, 'Danh sách nhân viên đi làm chưa sẵn sàng.')
        return working_staff_provider()

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
                result = ingest(conn, payload)
                return result
        result = await run_in_threadpool(save)
        appointment_result = None
        if (payload.kind == 'booking' and payload.requested_staff and payload.appointment_date
                and payload.appointment_date == datetime.now(VN_TZ).date()
                and (appointment_writer or getattr(app.state, 'online_booking_appointment_sync', None))):
            appointment_result = await run_in_threadpool(
                sync_appointments, payload,
            )
        return {**result, **({'staff_appointment': appointment_result} if appointment_result is not None else {})}

    @app.get('/v2/integrations/website/booking-staff')
    def website_booking_staff(request: Request):
        timestamp = request.headers.get('X-Vera-Timestamp')
        signature = request.headers.get('X-Vera-Signature')
        verify_signature(b'', timestamp, signature, os.getenv('VERA_WEBSITE_WEBHOOK_SECRET', ''))
        if not working_staff_provider:
            raise HTTPException(503, 'Danh sách nhân viên đang đi làm chưa sẵn sàng.')
        return working_staff_provider()

    @app.post('/v2/online-bookings')
    def create_manual_booking(payload: ManualBookingRequest, ident=Depends(authorized)):
        validate_staff(payload)
        actor = str(getattr(ident, 'employee_username', '') or getattr(ident, 'auth_user_id', '') or ident.role)
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            result = ingest(conn, payload)
            if not result['duplicate']:
                conn.execute(text('UPDATE vera_online_booking SET updated_by=:actor WHERE id=:id'),
                             {'actor': actor, 'id': result['id']})
        appointment_result = sync_appointments(payload)
        return {**result, 'staff_appointment': appointment_result}

    @app.get('/v2/online-bookings')
    def listing(page: int = Query(1, ge=1, le=100000), limit: int = Query(25, ge=1, le=100),
                status: Literal['', 'new', 'confirmed', 'handled', 'cancelled'] = '',
                kind: Literal['', 'booking', 'contact'] = '', q: str = Query('', max_length=100),
                date_from: date | None = None, date_to: date | None = None, upcoming: bool = False,
                ident=Depends(authorized)):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, 'Ngày kết thúc phải từ ngày bắt đầu trở đi.')
        where = "WHERE NOT b.deleted AND (:status='' OR b.status=:status) AND (:kind='' OR b.kind=:kind) AND (:q='' OR b.customer_name ILIKE :search OR b.phone ILIKE :search)"
        where += " AND (CAST(:date_from AS date) IS NULL OR COALESCE(b.appointment_date,(b.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)>=CAST(:date_from AS date)) AND (CAST(:date_to AS date) IS NULL OR COALESCE(b.appointment_date,(b.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)<=CAST(:date_to AS date))"
        if upcoming:
            where += " AND " + UPCOMING_WINDOW_SQL
        ordering = 'b.appointment_date ASC, b.appointment_time ASC, b.id ASC' if upcoming else 'b.id DESC'
        params = dict(date_from=date_from, date_to=date_to, status=status, kind=kind, q=q.strip(), search='%'+q.strip()+'%', limit=limit, offset=(page-1)*limit)
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            total = conn.execute(text('SELECT count(*) FROM vera_online_booking b '+where), params).scalar_one()
            rows = conn.execute(text(f'SELECT {PUBLIC_COLUMNS} FROM vera_online_booking b '+where+f' ORDER BY {ordering} LIMIT :limit OFFSET :offset'), params).mappings().all()
        return {'rows': [dict(row) for row in rows], 'total': total, 'page': page, 'limit': limit}

    @app.get('/v2/online-bookings/unread')
    def unread(ident=Depends(authorized)):
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            rows = conn.execute(text(f'''SELECT {PUBLIC_COLUMNS} FROM vera_online_booking b
              WHERE NOT b.deleted AND b.status='new' AND NOT EXISTS(SELECT 1 FROM vera_online_booking_seen s
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
        if payload.booking:
            validate_staff(payload.booking)
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            current = conn.execute(text('SELECT kind,revision FROM vera_online_booking WHERE id=:id AND NOT deleted FOR UPDATE'), {'id': booking_id}).mappings().first()
            if not current or current['revision'] != payload.revision:
                raise HTTPException(409, 'Yêu cầu đã thay đổi. Hãy tải lại trước khi lưu.')
            if payload.booking and current['kind'] != 'booking':
                raise HTTPException(422, 'Chỉ sửa thông tin lịch hẹn cho yêu cầu đặt lịch.')
            params = {'status': payload.status, 'note': payload.note, 'revision': payload.revision, 'id': booking_id, 'actor': ident.employee_username}
            fields = ''
            if payload.booking:
                editable = payload.booking.model_dump(exclude={'event_id', 'kind'})
                params.update(editable)
                fields = ''.join(f'{key}=:{key},' for key in editable)
            row = conn.execute(text(f"UPDATE vera_online_booking SET {fields}status=:status,note=:note,revision=revision+1,updated_at=now(),updated_by=:actor WHERE id=:id AND revision=:revision AND NOT deleted RETURNING id,revision"), params).mappings().first()
        sync_appointments(payload.booking)
        return dict(row)

    @app.delete('/v2/online-bookings/{booking_id}')
    def delete(booking_id: int, payload: BookingDelete, ident=Depends(authorized)):
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            row = conn.execute(text("UPDATE vera_online_booking SET deleted=true,status='cancelled',revision=revision+1,updated_at=now(),updated_by=:actor WHERE id=:id AND revision=:revision AND NOT deleted RETURNING id,revision"), {'id': booking_id, 'revision': payload.revision, 'actor': ident.employee_username}).mappings().first()
            if not row:
                raise HTTPException(409, 'Yêu cầu đã thay đổi. Hãy tải lại trước khi xóa.')
        sync_appointments()
        return dict(row)

    app.state.online_booking_installed = True

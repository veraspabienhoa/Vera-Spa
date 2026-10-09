"""Approved holiday periods, with snapshotted HR cohorts and caller-owned SQL."""
from datetime import date, datetime, time, timedelta
import hashlib
import json
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')


class HolidayCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    scope: Literal['all', 'departments', 'employees']
    departments: list[str] = Field(default_factory=list, max_length=100)
    employees: list[str] = Field(default_factory=list, max_length=2000)
    mode: Literal['day', 'dates', 'range', 'hours']
    dates: list[date] = Field(default_factory=list, max_length=366)
    date_from: date | None = None
    date_to: date | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    note: str = Field(min_length=1, max_length=1000)


class HolidayCancel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)


def local(value):
    if isinstance(value, str): value = datetime.fromisoformat(value)
    return value.replace(tzinfo=VN_TZ) if value.tzinfo is None else value.astimezone(VN_TZ)


def merge_periods(values):
    merged = []
    for start, end in sorted(values):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def periods_for(body):
    if not body.note.strip():
        raise HTTPException(422, 'Cần nhập tên lễ hoặc ghi chú.')
    if body.mode == 'hours':
        if not body.starts_at or not body.ends_at or body.dates or body.date_from or body.date_to:
            raise HTTPException(422, 'Chọn đúng ngày giờ bắt đầu và kết thúc.')
        start, end = local(body.starts_at), local(body.ends_at)
        if end <= start or end - start > timedelta(days=366):
            raise HTTPException(422, 'Giờ kết thúc phải sau giờ bắt đầu; khoảng nghỉ tối đa 366 ngày.')
        return [(start, end)]
    if body.starts_at or body.ends_at:
        raise HTTPException(422, 'Không nhập giờ cho chế độ nghỉ cả ngày.')
    if body.mode == 'range':
        if not body.date_from or not body.date_to or body.dates or body.date_to < body.date_from:
            raise HTTPException(422, 'Khoảng ngày nghỉ không hợp lệ.')
        if (body.date_to - body.date_from).days >= 366:
            raise HTTPException(422, 'Chọn tối đa 366 ngày cho một lần đăng ký.')
        days = [body.date_from + timedelta(days=i) for i in range((body.date_to-body.date_from).days+1)]
    else:
        days = sorted(set(body.dates))
        if days and ((days[-1]-days[0]).days >= 366 or days[-1].year >= 9999):
            raise HTTPException(422, 'Các ngày tự chọn phải nằm trong khoảng tối đa 366 ngày.')
        if not days or (body.mode == 'day' and len(days) != 1) or body.date_from or body.date_to:
            raise HTTPException(422, 'Chưa chọn đúng ngày nghỉ.')
    return merge_periods([(datetime.combine(day, time.min, VN_TZ), datetime.combine(day+timedelta(days=1), time.min, VN_TZ)) for day in days])


def ensure_schema(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_holiday_leave (
        id uuid PRIMARY KEY, scope text NOT NULL, mode text NOT NULL, note text NOT NULL,
        input_hash text NOT NULL, selection jsonb NOT NULL, created_by text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT NOW(), revision integer NOT NULL DEFAULT 1,
        cancelled_at timestamptz, cancelled_by text)'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_holiday_leave_member (
        registration_id uuid NOT NULL REFERENCES vera_holiday_leave(id) ON DELETE CASCADE,
        employee_username text NOT NULL REFERENCES employees(username) ON UPDATE CASCADE ON DELETE CASCADE,
        department_code text NOT NULL, PRIMARY KEY(registration_id,employee_username))'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_holiday_leave_period (
        registration_id uuid NOT NULL REFERENCES vera_holiday_leave(id) ON DELETE CASCADE,
        starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL,
        CHECK(ends_at>starts_at), PRIMARY KEY(registration_id,starts_at))'''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS vera_holiday_member_username ON vera_holiday_leave_member(employee_username,registration_id)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS vera_holiday_period_range ON vera_holiday_leave_period(starts_at,ends_at)'))


def ready(conn):
    return bool(conn.execute(text("SELECT to_regclass('vera_holiday_leave_period')")).scalar())


def roster(conn):
    from vera_web_v2_hr import registry, department_code
    state = registry(conn)
    departments = {code: item for code, item in state['departments'].items() if item.get('active', True)}
    rows = conn.execute(text('''SELECT username,COALESCE(full_name,'') AS full_name,role FROM employees
        WHERE COALESCE(payload->>'__deleted','false')<>'true' AND lower(COALESCE(role,''))<>'admin'
          AND lower(COALESCE(payload->>'Trạng thái làm việc',payload->>'employment_status','đang làm việc')) IN ('đang làm việc','thử việc')
        ORDER BY COALESCE(stt,2147483647),username''')).mappings().all()
    employees = [{**dict(row), 'department': department_code(row, state)} for row in rows]
    return employees, [{'code': code, 'name': item['name']} for code, item in departments.items()]


def select_members(body, employees, departments):
    available = {d['code'] for d in departments}
    by_name = {e['username']: e for e in employees}
    if body.scope == 'all':
        if body.departments or body.employees:
            raise HTTPException(422, 'Phạm vi toàn bộ nhân viên không dùng danh sách chọn riêng.')
        targets = employees
    elif body.scope == 'departments':
        selected = set(body.departments)
        if not selected or body.employees or not selected <= available:
            raise HTTPException(422, 'Chọn bộ phận đang hoạt động trong Nhân sự.')
        targets = [e for e in employees if e['department'] in selected]
    else:
        selected = set(body.employees)
        if not selected or body.departments or not selected <= by_name.keys():
            raise HTTPException(422, 'Chọn nhân viên đang làm việc hoặc thử việc.')
        targets = [e for e in employees if e['username'] in selected]
    if not targets:
        raise HTTPException(422, 'Phạm vi đã chọn chưa có nhân viên phù hợp.')
    return targets


def intervals(conn, start, end, usernames=None):
    """Half-open periods; one batch query on the caller's connection."""
    if not ready(conn):
        return {}
    rows = conn.execute(text('''SELECT m.employee_username,p.starts_at,p.ends_at,r.note,r.id
        FROM vera_holiday_leave_period p JOIN vera_holiday_leave r ON r.id=p.registration_id
        JOIN vera_holiday_leave_member m ON m.registration_id=r.id
        WHERE r.cancelled_at IS NULL AND p.starts_at<:end AND p.ends_at>:start
          AND (CAST(:names AS text[]) IS NULL OR m.employee_username=ANY(:names))
        ORDER BY p.starts_at'''), {'start': local(start), 'end': local(end), 'names': usernames}).mappings().all()
    result = {}
    for row in rows:
        result.setdefault(row['employee_username'], []).append(dict(row))
    return result


def uncovered(start, end, periods):
    start, end = local(start), local(end)
    remaining = [(start, end)] if end > start else []
    for left, right in merge_periods([(local(p['starts_at']), local(p['ends_at'])) for p in periods]):
        next_values = []
        for a, b in remaining:
            if right <= a or left >= b:
                next_values.append((a, b))
            else:
                if a < left: next_values.append((a, left))
                if right < b: next_values.append((right, b))
        remaining = next_values
    return remaining


def approved_day(conn, username, day):
    start = datetime.combine(day, time.min, VN_TZ)
    return bool(intervals(conn, start, start+timedelta(days=1), [username]).get(username))


def project_live(state, values, now):
    now = local(now)
    for employee in state['employees']:
        periods = values.get(employee.get('username') or employee.get('name'), [])
        if not periods and 'holiday_leave_active' not in employee:
            continue
        active = [p for p in periods if local(p['starts_at']) <= now < local(p['ends_at'])]
        employee['holiday_leave_periods'] = [{'starts_at':local(p['starts_at']).isoformat(), 'ends_at':local(p['ends_at']).isoformat()} for p in periods]
        employee['holiday_leave_active'] = bool(active)
        employee['holiday_leave_note'] = '; '.join(dict.fromkeys(p['note'] for p in active))
        employee['holiday_leave_until'] = max((local(p['ends_at']).isoformat() for p in active), default='')


def registrations(conn, username=None, start=None, end=None):
    if not ready(conn): return []
    rows = conn.execute(text('''SELECT r.id,r.scope,r.mode,r.note,r.created_by,r.created_at,r.revision,r.cancelled_at,
        0::integer AS calculated_days,
        (SELECT jsonb_agg(jsonb_build_object('starts_at',p.starts_at,'ends_at',p.ends_at) ORDER BY p.starts_at)
          FROM vera_holiday_leave_period p WHERE p.registration_id=r.id) AS periods,
        (SELECT jsonb_agg(jsonb_build_object('username',m.employee_username,'department',m.department_code) ORDER BY m.employee_username)
          FROM vera_holiday_leave_member m WHERE m.registration_id=r.id AND (CAST(:username AS text) IS NULL OR m.employee_username=:username)) AS employees
        FROM vera_holiday_leave r WHERE
          (CAST(:username AS text) IS NULL OR EXISTS(SELECT 1 FROM vera_holiday_leave_member m WHERE m.registration_id=r.id AND m.employee_username=:username))
          AND (CAST(:start AS timestamptz) IS NULL OR EXISTS(SELECT 1 FROM vera_holiday_leave_period p WHERE p.registration_id=r.id AND p.ends_at>:start AND p.starts_at<:end))
        ORDER BY r.created_at DESC LIMIT 200'''), {'username': username, 'start': start, 'end': end}).mappings().all()
    return [dict(row) for row in rows]


def install_routes(app, *, engine_instance, current_identity, require_feature, feature_allowed, identity_type):
    @app.get('/v2/holiday-leave')
    def listing(start: date, end: date, ident: identity_type = Depends(current_identity)):
        if end < start or (end-start).days > 366:
            raise HTTPException(422, 'Khoảng xem tối đa 366 ngày.')
        with engine_instance().connect() as conn:
            require_feature(conn, ident, 'birthday')
            can_register = bool(feature_allowed(conn, ident, 'holiday_leave_register'))
            can_cancel = bool(feature_allowed(conn, ident, 'holiday_leave_cancel'))
            employees, departments = roster(conn) if can_register else ([], [])
            return {'registrations': registrations(conn, None if can_register or can_cancel else ident.employee_username,
                datetime.combine(start,time.min,VN_TZ), datetime.combine(end+timedelta(days=1),time.min,VN_TZ)),
                'employees': employees, 'departments': departments, 'can_register': can_register, 'can_cancel': can_cancel}

    @app.post('/v2/holiday-leave')
    def create(body: HolidayCreate, ident: identity_type = Depends(current_identity)):
        periods = periods_for(body)
        digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'holiday_leave_register')
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:holiday_leave'))"))
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:employees'))"))
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
            ensure_schema(conn)
            prior = conn.execute(text('SELECT input_hash,created_by FROM vera_holiday_leave WHERE id=:id'), {'id':body.request_id}).mappings().first()
            if prior:
                if prior['input_hash'] != digest or prior['created_by'] != ident.employee_username:
                    raise HTTPException(409, 'Mã đăng ký đã được dùng cho nội dung khác.')
                return {'ok':True, 'id':body.request_id, 'duplicate':True, 'calculated_days':0, 'message':'Lịch nghỉ lễ đã được lưu trước đó.'}
            employees, departments = roster(conn)
            targets = select_members(body, employees, departments)
            names = [e['username'] for e in targets]
            existing = intervals(conn, periods[0][0], periods[-1][1], names)
            if any(local(old['starts_at']) < end and local(old['ends_at']) > start for values in existing.values() for old in values for start,end in periods):
                raise HTTPException(409, 'Có nhân viên đã đăng ký nghỉ lễ trong khoảng này. Hãy kiểm tra lịch đã lưu.')
            conn.execute(text('''INSERT INTO vera_holiday_leave(id,scope,mode,note,input_hash,selection,created_by)
                VALUES(:id,:scope,:mode,:note,:hash,CAST(:selection AS jsonb),:actor)'''),
                {'id':body.request_id,'scope':body.scope,'mode':body.mode,'note':body.note.strip(),'hash':digest,
                 'selection':json.dumps({'departments':body.departments,'employees':body.employees, 'originals': [{'username':e['username'],'department':e['department']} for e in targets]}),'actor':ident.employee_username})
            conn.execute(text('INSERT INTO vera_holiday_leave_member(registration_id,employee_username,department_code) VALUES(:id,:name,:department)'),
                [{'id':body.request_id,'name':e['username'],'department':e['department']} for e in targets])
            conn.execute(text('INSERT INTO vera_holiday_leave_period(registration_id,starts_at,ends_at) VALUES(:id,:start,:end)'),
                [{'id':body.request_id,'start':start,'end':end} for start,end in periods])
            return {'ok':True,'id':body.request_id,'employee_count':len(targets),'calculated_days':0,'message':f'Đã đăng ký nghỉ lễ cho {len(targets)} nhân viên.'}

    @app.post('/v2/holiday-leave/{registration_id}/cancel')
    def cancel(registration_id: UUID, body: HolidayCancel, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'holiday_leave_cancel')
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:holiday_leave'))"))
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
            if not ready(conn): raise HTTPException(404, 'Không tìm thấy lịch nghỉ lễ.')
            row = conn.execute(text('''UPDATE vera_holiday_leave SET cancelled_at=NOW(),cancelled_by=:actor,revision=revision+1
                WHERE id=:id AND revision=:revision AND cancelled_at IS NULL RETURNING id'''),
                {'actor':ident.employee_username,'id':registration_id,'revision':body.revision}).first()
            if not row: raise HTTPException(409, 'Lịch nghỉ lễ đã thay đổi hoặc đã huỷ. Hãy làm mới.')
            return {'ok':True,'message':'Đã huỷ lịch nghỉ lễ.'}


def apply_attendance(rows, values):
    """Annotate approved time; retain actual scans and earned/payable evidence."""
    from vera_facegate_attendance import shift_interval
    for row in rows:
        day = datetime.strptime(row['date'], '%d/%m/%Y').date()
        period = shift_interval(day, row.get('shift_start'), row.get('shift_end'))
        employee_periods = values.get(row.get('employee_name'), [])
        relevant = [p for p in employee_periods if period and local(p['starts_at']) < local(period[1]) and local(p['ends_at']) > local(period[0])]
        if not relevant:
            continue
        row['holiday_leave'] = [{'starts_at':local(p['starts_at']).isoformat(), 'ends_at':local(p['ends_at']).isoformat(), 'note':p['note']} for p in relevant]
        row['holiday_leave_full_shift'] = not uncovered(*period, relevant)
        row['attendance_note'] = ' · '.join(filter(None, [row.get('attendance_note'), 'Nghỉ lễ: ' + '; '.join(dict.fromkeys(p['note'] for p in relevant))]))
        if row['holiday_leave_full_shift']:
            row['attendance_expected'] = False
        arrival = row.get('check_in_at')
        if not arrival and row.get('check_in'):
            from vera_web_v2_attendance_v42 import _parse_datetime
            arrival = _parse_datetime(row['check_in'], day)
        if arrival:
            arrival = local(datetime.fromisoformat(arrival) if isinstance(arrival, str) else arrival)
            left, right = map(local, period)
            row['late_minutes'] = int(sum((b-a).total_seconds() for a,b in uncovered(left, min(right,arrival), relevant))//60)
            row['arrival_status'] = 'Đi trễ' if row['late_minutes'] else 'Đúng giờ'
    return rows


HOLIDAY_ACTIONS = frozenset({'booking', 'multi_booking', 'start', 'start_room', 'change_employee', 'restart_booking', 'update_booking'})


def refresh_action_holidays(conn, state, action, payload, now):
    """Refresh only action-owned employees; cached board flags cannot grant access."""
    from vera_web_v2_live_tour import _room_action_members, _parse_datetime
    ids = {str(value) for value in (payload.get('employee_ids') or [])}
    ids.update(str(row.get('employee_id')) for row in payload.get('bookings', []))
    for field in ('employee_id', 'target_employee_id'):
        if payload.get(field): ids.add(str(payload[field]))
    targets = (_room_action_members(state, str(payload.get('room') or ''), action) if action == 'start_room'
               else [e for e in state['employees'] if str(e['id']) in ids])
    names = [e.get('username') or e.get('name') for e in targets]
    project_live({'employees':targets}, intervals(conn, now, now+timedelta(seconds=1), names), now)
    if action in {'booking','multi_booking','update_booking'}:
        for row in payload.get('bookings') or [payload]:
            booked = _parse_datetime(row.get('booked_at')) or now
            booked_names = ([e.get('username') or e.get('name') for e in targets if str(e['id']) == str(row.get('employee_id'))]
                            if row.get('employee_id') else names)
            if intervals(conn, booked, booked+timedelta(seconds=1), booked_names):
                raise HTTPException(409, 'Nhân viên đang nghỉ lễ tại thời điểm Booking đã chọn.')

"""HC penalties: VERA shifts + verified fresh FaceGate evidence, caller-owned transaction."""
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
import uuid

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_facegate_control_log import VN_TZ
import vera_web_v2_hr as hr

KEY = 'hc_rules'
EXCLUDED = frozenset({'leader', 'nhanvien', 'admin', 'giamdoc'})
SOURCE = 'VERA · NỘI QUY HC'


class Toggle(BaseModel):
    enabled: bool
    expected_revision: int = Field(ge=0)


def definitions(conn):
    return {k: v for k, v in hr.departments(conn).items() if k not in EXCLUDED}


def policy(conn):
    row = conn.execute(text("SELECT value_json,revision FROM vera_app_setting WHERE category='leave_rules' AND setting_key=:key"), {'key': KEY}).mappings().first()
    value = (row or {}).get('value_json') or {}
    return {'departments': value.get('departments', {}), 'revision': int((row or {}).get('revision') or 0)}


def dashboard(conn):
    current = policy(conn)
    return {'revision': current['revision'], 'departments': [
        {'code': code, 'name': value['name'], 'salary_mode': value['salary_mode'],
         'enabled': current['departments'].get(code, {}).get('enabled') is True,
         'enabled_since': current['departments'].get(code, {}).get('enabled_since')}
        for code, value in definitions(conn).items()], 'multiplier': 2}


def install_routes(app, *, engine_instance, current_identity, require_feature, identity_type):
    @app.get('/v2/rules/hc')
    def read(ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'official_rules_view')
            return dashboard(conn)

    @app.put('/v2/rules/hc/{department}')
    def toggle(department: str, body: Toggle, ident: identity_type = Depends(current_identity)):
        if str(ident.role).strip().lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được kích hoạt Nội quy HC.')
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'official_rules_edit')
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:hc-rules'))"))
            if department not in definitions(conn):
                raise HTTPException(400, 'Bộ phận không thuộc Nội quy HC.')
            current = policy(conn)
            if current['revision'] != body.expected_revision:
                raise HTTPException(409, 'Nội quy đã thay đổi. Hãy làm mới rồi thử lại.')
            old = current['departments'].get(department, {})
            current['departments'][department] = {'enabled': body.enabled,
                'enabled_since': old.get('enabled_since') if old.get('enabled') and body.enabled else datetime.now(VN_TZ).isoformat(),
                'updated_by': ident.employee_username}
            conn.execute(text('''INSERT INTO vera_app_setting(category,setting_key,value_json,revision,source,updated_by,created_at,updated_at)
                VALUES('leave_rules',:key,CAST(:value AS jsonb),1,'hc_rules',:actor,NOW(),NOW())
                ON CONFLICT(category,setting_key) DO UPDATE SET value_json=EXCLUDED.value_json,
                revision=vera_app_setting.revision+1,source=EXCLUDED.source,updated_by=EXCLUDED.updated_by,updated_at=NOW()'''),
                {'key': KEY, 'value': json.dumps({'departments': current['departments']}), 'actor': ident.employee_username})
            return dashboard(conn)


def ensure_schema(conn):
    # The caller already owns the HC initialization lock; avoid repeated DDL.
    if conn.execute(text("SELECT to_regclass('vera_hc_penalty_event')")).scalar():
        return
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_hc_penalty_event (
        id bigserial PRIMARY KEY, work_date date NOT NULL, employee_name text NOT NULL,
        department text NOT NULL, kind text NOT NULL, amount numeric NOT NULL,
        basis jsonb NOT NULL, leave_record_uid text NOT NULL, created_at timestamptz NOT NULL DEFAULT NOW(),
        UNIQUE(work_date,employee_name));
        ALTER TABLE vera_hc_penalty_event ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON vera_hc_penalty_event FROM PUBLIC;
        DO $$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON vera_hc_penalty_event FROM anon; END IF;
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON vera_hc_penalty_event FROM authenticated; END IF;
        END $$;'''))


def interval(day, left, right):
    try:
        start = datetime.combine(day, time.fromisoformat(str(left)), tzinfo=VN_TZ)
        end = datetime.combine(day, time.fromisoformat(str(right)), tzinfo=VN_TZ)
    except (TypeError, ValueError):
        return None
    if end == start:
        return None
    if end < start:
        end += timedelta(days=1)
    return start, end


def wage(config, start, end, shift, *, work_day=None):
    """Exact configured wage for an interval; no allowances, overtime or fallback zero."""
    if end <= start:
        return Decimal(0)
    def number(key):
        value = Decimal(str(config.get(key) or 0))
        if not value.is_finite() or value <= 0:
            raise ValueError('missing_hourly_rate')
        return value
    if config.get('calculation_mode') == 'monthly':
        rate = number('default_base_salary') / number('standard_month_days') / number('standard_day_hours')
        return rate * Decimal(str((end-start).total_seconds())) / Decimal(3600)
    if config.get('calculation_mode') != 'hourly':
        raise ValueError('unsupported_salary_mode')
    ca1 = shift == 'Ca 1' or (shift == 'Giờ làm' and start.hour < 12)
    seconds = Decimal(str((end-start).total_seconds()))
    if ca1:
        return number('rate_ca1') * seconds / Decimal(3600)
    cutoff = datetime.combine(work_day or start.date(), time(22), tzinfo=VN_TZ)
    before = max(0, (min(end, cutoff)-start).total_seconds())
    after = (end-start).total_seconds()-before
    return sum(number(key) * Decimal(str(duration)) / Decimal(3600)
               for key, duration in [('rate_ca2_before_22', before), ('rate_ca2_after_22', after)] if duration > 0)


def penalty(config, start, end, shift):
    return int((2 * wage(config, start, end, shift)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def decision_penalty(config, row, day, decision):
    """Price missed scheduled time once; split main/OT rates and exclude gaps."""
    periods = [(interval(day, row['main_start'], row['main_end']), row['shift_code'])]
    ot = interval(day, row.get('ot_start'), row.get('ot_end')) if row.get('overtime_shift') else None
    if decision['kind'] == 'late' and ot:
        main = periods[0][0]
        if row['overtime_shift'] == 'Từ giờ tới giờ' and main[1].date() > day and ot[0].hour < main[0].hour and ot[1].hour <= main[0].hour:
            ot = tuple(t+timedelta(days=1) for t in ot)
        shift = row['overtime_shift'].replace('TC ', '') if row['overtime_shift'].startswith('TC ') else 'Giờ làm'
        periods.append((ot, shift))
    left, right = decision['start'], decision['end']
    edges = sorted({left, right, *(max(left, min(right, t)) for period, _ in periods for t in period)})
    total = Decimal(0)
    segments = []
    for a, b in zip(edges, edges[1:]):
        shift = next((shift for period, shift in periods if period[0] <= a and b <= period[1]), None)
        if not shift or b <= a:
            continue
        total += wage(config, a, b, shift, work_day=day)
        segments.append({'start': a.isoformat(), 'end': b.isoformat(), 'shift': shift})
    decision['wage_segments'] = segments
    return int((2*total).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def scheduled_rows(conn, day):
    # Main-shift times remain separate from the attendance window including overtime.
    return [dict(r) for r in conn.execute(text(f'''SELECT ws.*, e.role AS employee_role,
        {hr.DEPARTMENT_SQL.replace('username', 'e.username').replace('role,', 'e.role,')} AS hc_department,
        e.payload AS employee_payload,
        COALESCE(NULLIF(ws.start_time,''),d.start_time,'') AS main_start,
        COALESCE(NULLIF(ws.end_time,''),d.end_time,'') AS main_end,
        COALESCE(NULLIF(ws.overtime_start_time,''),ot.start_time,'') AS ot_start,
        COALESCE(NULLIF(ws.overtime_end_time,''),ot.end_time,'') AS ot_end
        FROM vera_work_schedule ws JOIN employees e ON lower(btrim(e.username))=lower(btrim(ws.employee_username))
        LEFT JOIN vera_work_shift_definition d ON d.department=ws.department AND d.shift_code=ws.shift_code
        LEFT JOIN vera_work_shift_definition ot ON ot.department=ws.department AND ot.shift_code=
          CASE ws.overtime_shift WHEN 'TC Ca 1' THEN 'Ca 1' WHEN 'TC Ca 2' THEN 'Ca 2' END
        WHERE ws.work_date=:day AND COALESCE(e.payload->>'__deleted','false')<>'true'
          AND lower(COALESCE(e.payload->>'Trạng thái làm việc',e.payload->>'employment_status','đang làm việc'))='đang làm việc'
        ORDER BY ws.employee_username'''), {'day': day}).mappings()]


def candidate(row, day, data, current, now, leaves):
    from vera_schedule_attendance_window import attendance_window
    username = row['employee_username']
    department = str(row.get('hc_department') or '').strip().lower()
    cfg = current['departments'].get(department, {})
    if department in EXCLUDED or str(row.get('employee_role') or '').strip().lower() in EXCLUDED:
        return None
    if not cfg.get('enabled') or row.get('department') != department or row.get('hc_department') not in current.get('eligible_departments', {department}):
        return None
    main = interval(day, row.get('main_start'), row.get('main_end'))
    if not main or row.get('shift_code') in ('', 'Nghỉ', None):
        return None
    since = cfg.get('enabled_since')
    if not since or main[0] < datetime.fromisoformat(since).astimezone(VN_TZ):
        return None  # Activation never backfills a shift already started.
    if not any(m['username'] == username for m in data['index'].values()):
        return None
    # Only an explicit full-day unpaid absence may coexist with this money-only record.
    if any(float(l.get('penalty') or 0) > 0 or _norm(l.get('leave_reason')) not in {'nghi khong phep', 'nghi cuoi tuan khong phep'} for l in leaves):
        return None
    arrivals = [datetime.fromisoformat(r['_vera_checkin_at']).astimezone(VN_TZ) for r in data['rows']
                if r.get('EmployeeName') == username and r.get('WorkDateStr') == day.strftime('%d/%m/%Y')]
    effective = attendance_window({**row, 'start_time': row['main_start'], 'end_time': row['main_end'],
                                   'overtime_start_time': row.get('ot_start'), 'overtime_end_time': row.get('ot_end')})
    window = interval(day, *effective)
    if not window:
        return None
    if arrivals:
        arrival = min(arrivals)
        if leaves or arrival <= window[0] or arrival >= window[1]:
            return None
        # The configured first shift determines the hourly rate for earlier overtime.
        first_shift = row['overtime_shift'].replace('TC ', '') if window[0] < main[0] and row.get('overtime_shift','').startswith('TC ') else row['shift_code']
        return {'kind': 'late', 'start': window[0], 'end': arrival, 'shift': first_shift,
                'minutes': (arrival-window[0]).total_seconds()/60}
    if any(i.get('username') == username for i in data['issues']):
        return None  # A mapped scan outside the expected window still proves presence.
    if now <= main[1]:
        return None
    from vera_facegate_runtime import archive_complete
    if not all(archive_complete(data, d, after=main[1]) for d in {day, main[1].date()}):
        return None
    return {'kind': 'absence', 'start': main[0], 'end': main[1], 'shift': row['shift_code'],
            'minutes': (main[1]-main[0]).total_seconds()/60}


def _norm(value):
    from vera_auto_check import _norm as norm
    return norm(value)


def write_penalty(conn, row, day, decision, amount, revision, config):
    from vera_notification_delivery import enqueue
    uid = str(uuid.uuid4())
    basis = {**decision, 'start': decision['start'].isoformat(), 'end': decision['end'].isoformat(),
             'config': config, 'revision': revision, 'multiplier': 2}
    event = conn.execute(text('''INSERT INTO vera_hc_penalty_event(work_date,employee_name,department,kind,amount,basis,leave_record_uid)
        VALUES(:day,:employee,:department,:kind,:amount,CAST(:basis AS jsonb),:uid)
        ON CONFLICT(work_date,employee_name) DO NOTHING RETURNING id'''),
        {'day': day, 'employee': row['employee_username'], 'department': row['hc_department'],
         'kind': decision['kind'], 'amount': amount, 'basis': json.dumps(basis), 'uid': uid}).scalar()
    if not event:
        return False
    reason = ('Đi trễ' if decision['kind'] == 'late' else 'Nghỉ KHÔNG phép') + ' · Nội quy HC'
    detail = f"Nội quy HC v{revision} · {decision['start']:%H:%M} → {decision['end']:%H:%M} · {decision['minutes']:.2f} phút · 2 × lương giờ · {amount:,}đ"
    # Zero leave days: the penalty must not invent a second leave day or alter attendance.
    payload = {'record_uid': uid, 'Lý do nghỉ': reason, 'Phạt vi phạm': amount,
               'Số ngày tính': 0, 'hc_basis': basis, '__source_sheet_id': 'postgres:hc_rules', '__source_row': -event}
    now = datetime.now(VN_TZ)
    conn.execute(text('''INSERT INTO leave_records(source_sheet_id,source_row,leave_date,employee_name,leave_reason,leave_type,detail,
        calculated_days,accumulated_leave,penalty,update_date,update_time,updated_by,weekday_label,payload,record_uid,created_at,updated_at)
        VALUES('postgres:hc_rules',:srow,:day,:employee,:reason,'Vi phạm',:detail,0,0,:amount,:udate,:utime,:actor,:weekday,CAST(:payload AS jsonb),:uid,NOW(),NOW())'''),
        {'srow': -event, 'day': day, 'employee': row['employee_username'], 'reason': reason, 'detail': detail,
         'amount': amount, 'udate': now.strftime('%d/%m/%Y'), 'utime': now.strftime('%H:%M:%S'), 'actor': SOURCE,
         'weekday': 'Chủ nhật' if day.weekday()==6 else f'Thứ {day.weekday()+2}', 'payload': json.dumps(payload), 'uid': uid})
    tag = f'vera-hc-{event}'
    enqueue(conn, 'auto_penalty', {'title': 'Phạt tự động · Nội quy HC', 'employee': row['employee_username'],
        'kind': 'auto_penalty', 'tag': tag, 'body': f"{row['employee_username']} · {day:%d-%m-%Y} · {reason} · {amount:,}đ. {detail}"}, event_key=tag)
    return True


def fresh_evidence(data, day, now):
    from vera_facegate_runtime import archive_complete
    try:
        saved = next((s for s in data['syncs'] if str(s['work_date']) == now.date().isoformat()), None)
        return bool(saved and data['events'] and archive_complete(data, day) and
            archive_complete(data, now.date()) and
            not any(i.get('reason') != 'no_vera_shift' for i in data['issues']) and
            0 <= (now-datetime.fromisoformat(str(saved['last_synced_at'])).astimezone(VN_TZ)).total_seconds() <= 300)
    except (ValueError, TypeError, KeyError):
        return False


def process(conn, *, now=None):
    from vera_attendance_source import source_for
    import vera_facegate_attendance as fg
    import vera_web_v2_department_payroll as pay
    from vera_attendance_participation import suspended
    from vera_resource_concurrency import lock_transition
    now = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:hc-rules'))"))
    current = policy(conn)
    result = {'added': 0, 'pending': 0}
    if not any(v.get('enabled') for v in current['departments'].values()):
        return {**result, 'reason': 'disabled'}
    ensure_schema(conn)
    current['eligible_departments'] = set(definitions(conn))
    configs = pay._employee_config_map(conn)
    department_configs = {}
    for day in (now.date()-timedelta(days=1), now.date()):
        if source_for(day) != 'facegate':
            continue
        data = fg.project_evidence(conn, day, day)
        if not fresh_evidence(data, day, now):
            result['pending'] += 1
            continue
        for row in scheduled_rows(conn, day):
            username = row['employee_username']
            if suspended(username, day) or username.strip().lower() in {'admin','akamen'}:
                continue
            lock_transition(conn, [('leave_employee', username)], legacy_keys=['vera:phase4:leave_primary'])
            if conn.execute(text('SELECT 1 FROM vera_hc_penalty_event WHERE work_date=:day AND employee_name=:name'), {'day': day, 'name': username}).scalar():
                continue
            leaves = [dict(l) for l in conn.execute(text('SELECT leave_reason,penalty FROM leave_records WHERE leave_date=:day AND lower(btrim(employee_name))=lower(btrim(:name))'), {'day': day, 'name': username}).mappings()]
            latest = fg.project_evidence(conn, day, day)
            if not fresh_evidence(latest, day, now):
                result['pending'] += 1
                continue
            decision = candidate(row, day, latest, current, now, leaves)
            if not decision:
                continue
            department = row['hc_department']
            try:
                if department not in department_configs:
                    department_configs[department] = pay._settings(conn, department)['config']
                config = configs.get(username.casefold(), department_configs[department])
                amount = decision_penalty(config, row, day, decision)
            except (ValueError, HTTPException):
                result['pending'] += 1
                continue
            if amount <= 0:
                result['pending'] += 1
                continue
            if write_penalty(conn, row, day, decision, amount, current['revision'], config):
                result['added'] += 1
    return result

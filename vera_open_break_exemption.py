"""Exempt one open FaceID break after a trusted manual unauthorized departure.

All reads/writes use the owning transaction. Never infer a departure from the
last scan; a server-stamped leave registration is the authority.
"""
from datetime import datetime, timedelta, timezone
import json
import re
import unicodedata
from sqlalchemy import text

VN_TZ = timezone(timedelta(hours=7))
MARKER = '_vera_manual_early_departure'
ROLES = {'admin', 'quanly', 'letan'}


def norm(value):
    value = unicodedata.normalize('NFD', str(value or '').lower().replace('đ', 'd'))
    return ' '.join(''.join(c for c in value if unicodedata.category(c) != 'Mn').split())


def unauthorized(reason):
    return norm(reason) in {'ve som khong phep', 've som cuoi tuan khong phep'}


def local_time(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.astimezone(VN_TZ).replace(tzinfo=None) if value.tzinfo else value


def clock(value, day):
    for fmt in ('%H:%M:%S', '%H:%M', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            parsed = datetime.strptime(str(value or ''), fmt)
            return parsed.replace(year=day.year, month=day.month, day=day.day) if parsed.year == 1900 else parsed
        except ValueError:
            pass
    return None


def qualifying_break(item, rows, day):
    """Fail closed on missing actor, timestamp, shift, or FaceID evidence."""
    if (str(item.get('shift') or '').strip().lower() not in {'ca 1', 'ca 2', '1', '2'}
            or item.get('break_in') or item.get('attendance_evidence_issues')
            or item.get('attendance_fine_evidence_ready') is not True
            or item.get('evidence_source') != 'facegate'):
        return None
    # Canonical FaceGate groups retain calendar dates. Exactly two groups mean
    # shift check-in followed by one break-out; any later scan blocks exemption.
    punches = [local_time(p) for p in (item.get('punch_datetimes') or [])]
    if len(punches) != 2 or any(p is None for p in punches) or punches[0] >= punches[1]:
        return None
    out = punches[1]
    from vera_web_v2_attendance_break_window import _is_break_start
    if not _is_break_start(out, day):
        return None
    projected_out = clock(item.get('break_out'), day)
    if projected_out and projected_out != out:
        return None
    confirmations = []
    for row in rows:
        # Automatic violations are not a registered leave schedule.
        if row.get('automatic') or row.get('source_sheet_id') == 'postgres:auto_check':
            continue
        marker = (row.get('payload') or {}).get(MARKER) or {}
        registered = local_time(marker.get('registered_at'))
        if (unauthorized(row.get('leave_reason')) and marker.get('role') in ROLES
                and registered and registered.date() == day and registered > out
                and local_time(row.get('created_at')) and local_time(row['created_at']) > out):
            confirmations.append(row)
        else:
            # Any other schedule (including half-day/benefit/support) blocks it.
            return None
    return out if confirmations else None


def registrations(conn, employee, day):
    rows = [dict(r) for r in conn.execute(text('''
        SELECT r.* FROM leave_records r
        WHERE r.employee_name=:employee AND r.leave_date=:day
    '''), {'employee': employee, 'day': day}).mappings().all()]
    # Standalone workers bootstrap auto-check tables only when saving their
    # first event. Ordinary days must not depend on that schema already existing.
    if not any((r.get('payload') or {}).get(MARKER) for r in rows):
        return rows
    linked = set(conn.execute(text('''
        SELECT leave_record_uid FROM vera_auto_check_event
        WHERE employee_name=:employee AND work_date=:day
    '''), {'employee': employee, 'day': day}).scalars().all())
    for row in rows:
        row['automatic'] = row.get('record_uid') in linked
    return rows


def exemption(conn, employee, day, item=None):
    rows = registrations(conn, employee, day)
    if not any((r.get('payload') or {}).get(MARKER) for r in rows):
        return None
    if item is None:
        from vera_facegate_runtime import records
        matches = [r for r in records(conn, day, day) if norm(r.get('employee_name')) == norm(employee)]
        if len(matches) != 1 or matches[0].get('attendance_fine_evidence_ready') is not True:
            from vera_leave_penalty_recheck import EvidencePending
            raise EvidencePending('open_break_evidence_pending')
        item = matches[0]
    out = qualifying_break(item, rows, day)
    if out:
        from vera_holiday_leave import approved_day
        if approved_day(conn, employee, day):
            return None
    return out


def matches_event(reason, detail, out):
    if not norm(reason).startswith('ra ngoai '):
        return False
    match = re.search(r'Giờ ra\s+(\d{2}:\d{2}(?::\d{2})?)(?![\d:])', str(detail or ''), re.I)
    return bool(match and clock(match.group(1), out.date()) == out)


def revoke(conn, employee, day, out):
    """Only revoke untouched system rows linked to this exact outside event."""
    rows = conn.execute(text('''SELECT e.id,e.reason,e.detail,e.leave_record_uid
        FROM vera_auto_check_event e JOIN leave_records r ON r.record_uid=e.leave_record_uid
        WHERE e.work_date=:day AND e.employee_name=:employee AND e.status='added'
          AND r.source_sheet_id='postgres:auto_check' AND r.leave_reason=e.reason
          AND r.detail=e.detail AND r.updated_by=e.source
        FOR UPDATE OF e,r'''), {'day': day, 'employee': employee}).mappings().all()
    count = 0
    for row in rows:
        if not matches_event(row['reason'], row['detail'], out):
            continue
        conn.execute(text("DELETE FROM leave_records WHERE record_uid=:uid AND source_sheet_id='postgres:auto_check'"),
                     {'uid': row['leave_record_uid']})
        conn.execute(text('''UPDATE vera_auto_check_event SET status='revoked',leave_record_uid=NULL,
            employee_notify_claimed_at=NULL,
            detail=CONCAT(COALESCE(detail,''),' · Miễn phạt ra ngoài: về sớm không phép nhập sau giờ ra, không có giờ vào lại')
            WHERE id=:id'''), {'id': row['id']})
        count += 1
    return count


def reconcile(conn, employee, day):
    out = exemption(conn, employee, day)
    return revoke(conn, employee, day, out) if out else 0


def _now():
    return datetime.now(VN_TZ)


def register(conn, record, ident):
    """Stamp authenticated role, commit a retry, and attempt immediate correction."""
    role = str(getattr(ident, 'role', '') or '').strip().lower()
    if role not in ROLES or not unauthorized(record.get('leave_reason')):
        return
    marker = json.dumps({MARKER: {'role': role, 'registered_at': _now().isoformat()}}, ensure_ascii=False)
    conn.execute(text("UPDATE leave_records SET payload=COALESCE(payload,'{}'::jsonb) || CAST(:marker AS jsonb) WHERE record_uid=:uid"),
                 {'uid': record['record_uid'], 'marker': marker})
    from vera_postgres_job_queue import enqueue_conn
    from vera_leave_penalty_recheck import QUEUE
    day = record['leave_date']
    enqueue_conn(conn, QUEUE, 'open-break:' + record['record_uid'],
                 {'employee': record['employee_name'], 'work_date': day.isoformat(), 'mode': 'open-break'})
    try:
        with conn.begin_nested():
            reconcile(conn, record['employee_name'], day)
    except Exception:
        # Durable job retries after commit; a projection failure cannot lose
        # the operator's otherwise valid leave registration.
        pass

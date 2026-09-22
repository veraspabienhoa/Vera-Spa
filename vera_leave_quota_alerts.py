"""Admin monthly leave audit and retryable, per-device push delivery."""
from contextlib import asynccontextmanager
from datetime import date
from calendar import monthrange
from collections import defaultdict
from hashlib import sha256
import json
import logging
from threading import Event, Thread

from fastapi import Depends, HTTPException, Query
from sqlalchemy import text
from vera_leave_registration_shared import summarize_leave_days
from vera_leave_advance import balances as advance_balances
from vera_web_v2_policy_v40 import GROUP3_WEEKEND_REASON_KEYS, _reason_key
import vera_web_v2_notification_settings as settings
from vera_auto_penalty_notifications import _send, _vault_secret, APP_URL

LIMITS = {'days': 5, 'weekends': 2, 'generated': 2}


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        day = row['leave_date']
        if isinstance(day, str):
            day = date.fromisoformat(day[:10])
        employee = str(row['employee_name'] or '').strip()
        if employee:
            groups[(employee.casefold(), day.strftime('%Y-%m'))].append({**dict(row), 'leave_date': day})
    result = []
    histories = defaultdict(list)
    for (employee, _), records in groups.items():
        histories[employee].extend(records)
    allowances = {employee: advance_balances(records, max(r['leave_date'] for r in records)) for employee, records in histories.items()}
    for (employee, month), records in sorted(groups.items()):
        summary = summarize_leave_days(records)
        weekends = {r['leave_date'] for r in records if r['leave_date'].weekday() >= 5
                    and _reason_key(r['leave_reason']) in GROUP3_WEEKEND_REASON_KEYS}
        values = {'days': summary['total_leave'], 'weekends': len(weekends), 'generated': summary['generated']}
        balance = allowances[employee][month]
        values['days'] = balance['ordinary']
        exceeded = [key for key, limit in LIMITS.items() if (balance['ordinary_excess'] > 0 if key == 'days' else values[key] > limit)]
        if exceeded:
            result.append({'employee': records[0]['employee_name'].strip(), 'month': month,
                           **values, 'day_limit': balance['available'], 'borrowed': balance['borrowed'], 'exceeded': exceeded})
    return result


def read_report(conn, start=None, end=None):
    # Whole calendar months, even when the UI selects only part of a month.
    params = {}
    where = ''
    if start is not None:
        params = {'start': start.replace(day=1), 'end': end.replace(day=monthrange(end.year, end.month)[1])}
        where = 'WHERE leave_date <= :end'
    rows = conn.execute(text(f'''SELECT employee_name, leave_date, leave_reason, leave_type,
        calculated_days FROM leave_records {where} ORDER BY leave_date, record_uid'''), params).mappings().all()
    items = summarize(rows)
    return [item for item in items if start is None or item['month'] >= start.strftime('%Y-%m')]


def ensure_schema(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_leave_quota_alert (
        fingerprint TEXT PRIMARY KEY, payload JSONB NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_leave_quota_delivery (
        fingerprint TEXT NOT NULL REFERENCES vera_leave_quota_alert(fingerprint),
        subscription_id UUID NOT NULL, sent_at TIMESTAMPTZ, claimed_at TIMESTAMPTZ,
        attempted_at TIMESTAMPTZ, PRIMARY KEY(fingerprint, subscription_id))'''))


def fingerprint(item):
    return sha256(json.dumps({**item, 'employee': item['employee'].casefold()}, sort_keys=True).encode()).hexdigest()


def scan(engine):
    with engine.begin() as conn:
        # Serialize scans across workers, without keeping locks during delivery.
        if not conn.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('vera:leave-quota-alerts'))")).scalar():
            return
        ensure_schema(conn)
        items = read_report(conn)
        conn.execute(text('UPDATE vera_leave_quota_alert SET active=FALSE WHERE active=TRUE'))
        for item in items:
            conn.execute(text('''INSERT INTO vera_leave_quota_alert(fingerprint,payload)
                VALUES(:fingerprint,CAST(:payload AS jsonb)) ON CONFLICT(fingerprint)
                DO UPDATE SET active=TRUE'''), {'fingerprint': fingerprint(item), 'payload': json.dumps(item)})
        if not settings.is_enabled(conn, 'leave_quota_exceeded'):
            return
        conn.execute(text('''INSERT INTO vera_leave_quota_delivery(fingerprint,subscription_id)
            SELECT a.fingerprint,s.subscription_id FROM vera_leave_quota_alert a
            CROSS JOIN vera_v2_push_subscription s
            JOIN vera_v2_user_profile p ON p.auth_user_id=s.auth_user_id
            WHERE a.active AND s.is_active AND p.is_active AND lower(btrim(p.role))='admin'
            ON CONFLICT DO NOTHING'''))


def deliver(engine):
    with engine.begin() as conn:
        ensure_schema(conn)
        if not settings.is_enabled(conn, 'leave_quota_exceeded'):
            return
        private_key = _vault_secret(conn, 'vera_v2_vapid_private_key')
        subject = _vault_secret(conn, 'vera_v2_vapid_subject') or APP_URL
        if not private_key:
            return
        deliveries = [dict(r) for r in conn.execute(text('''WITH candidates AS (
            SELECT d.fingerprint,d.subscription_id FROM vera_leave_quota_delivery d
            JOIN vera_leave_quota_alert a USING(fingerprint)
            JOIN vera_v2_push_subscription s USING(subscription_id)
            JOIN vera_v2_user_profile p ON p.auth_user_id=s.auth_user_id
            WHERE a.active AND s.is_active AND p.is_active AND lower(btrim(p.role))='admin'
              AND d.sent_at IS NULL AND (d.claimed_at IS NULL OR d.claimed_at < NOW()-INTERVAL '5 minutes')
              AND (d.attempted_at IS NULL OR d.attempted_at < NOW()-INTERVAL '1 minute')
            ORDER BY a.created_at LIMIT 10 FOR UPDATE OF d SKIP LOCKED
        ) UPDATE vera_leave_quota_delivery d SET claimed_at=NOW(),attempted_at=NOW()
          FROM candidates c,vera_leave_quota_alert a,vera_v2_push_subscription s
          WHERE d.fingerprint=c.fingerprint AND d.subscription_id=c.subscription_id
            AND a.fingerprint=d.fingerprint AND s.subscription_id=d.subscription_id
          RETURNING d.fingerprint,d.subscription_id,s.endpoint,s.p256dh,s.auth_secret,a.payload''')).mappings()]
    for delivery in deliveries:
        item = delivery['payload']
        month = '/'.join(reversed(item['month'].split('-')))
        labels = {'days': 'ngày nghỉ', 'weekends': 'lần cuối tuần Nhóm 3', 'generated': 'lần phát sinh'}
        detail = '; '.join(f"{item[k]:g}/{item.get('day_limit', 5) if k == 'days' else LIMITS[k]} {labels[k]}" for k in item['exceeded'])
        payload = {'title': 'VERA SPA · Đăng ký nghỉ vượt hạn mức',
                   'body': f"{item['employee']} · {month}: {detail}",
                   'tag': f"leave-quota-{delivery['fingerprint']}", 'url': APP_URL,
                   'kind': 'leave-quota-exceeded'}
        ok, status, _ = _send(delivery, payload, private_key, subject)
        with engine.begin() as conn:
            conn.execute(text('''UPDATE vera_leave_quota_delivery SET claimed_at=NULL,
                sent_at=CASE WHEN :ok THEN NOW() ELSE sent_at END
                WHERE fingerprint=:fingerprint AND subscription_id=:subscription_id'''),
                {'ok': ok, 'fingerprint': delivery['fingerprint'], 'subscription_id': delivery['subscription_id']})
            if status in (404, 410):
                conn.execute(text('UPDATE vera_v2_push_subscription SET is_active=FALSE WHERE subscription_id=:id'),
                             {'id': delivery['subscription_id']})


def check_and_notify(engine_instance):
    try:
        engine = engine_instance()
        scan(engine)
        deliver(engine)
    except Exception as exc:
        # No employee data, credentials, or SQL parameters in worker logs.
        logging.getLogger(__name__).warning('Leave quota notification retry: %s', type(exc).__name__)


def install(app, *, engine_instance, current_identity, identity_type):
    @app.get('/v2/leave/quota-check')
    def check(start: date = Query(), end: date = Query(), ident: identity_type = Depends(current_identity)):
        if str(ident.role).strip().lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được kiểm tra hạn mức.')
        if end < start or (end.year-start.year)*12+end.month-start.month > 11:
            raise HTTPException(400, 'Chọn khoảng thời gian tối đa 12 tháng.')
        with engine_instance().connect() as conn:
            items = read_report(conn, start, end)
        return {'items': items, 'limits': LIMITS, 'start': start.replace(day=1).isoformat(),
                'end': end.replace(day=monthrange(end.year,end.month)[1]).isoformat()}

    stop = Event()
    def monitor():
        while not stop.is_set():
            check_and_notify(engine_instance)
            stop.wait(60)

    previous = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with previous(application) as state:
            stop.clear()
            worker = Thread(target=monitor, name='leave-quota-monitor', daemon=True)
            worker.start()
            try:
                yield state
            finally:
                stop.set()
                worker.join(timeout=2)
    app.router.lifespan_context = lifespan

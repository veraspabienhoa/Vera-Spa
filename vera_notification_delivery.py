"""Durable notification routing. Producers enqueue; only the worker does network I/O."""
from __future__ import annotations
import hashlib
import json
import logging
from sqlalchemy import text
from vera_notification_periods import current_month, quota_month, current_quota_sql

APP_URL = 'https://app.veraspa.vn/'


def ensure_schema(conn):
    from vera_web_v2_notification_settings import ensure_schema as ensure_settings
    ensure_settings(conn)
    if not conn.execute(text("SELECT to_regclass('public.vera_notification_group')")).scalar_one_or_none():
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera.notification.schema'))"))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_notification_group (
            key TEXT PRIMARY KEY, label TEXT NOT NULL, members JSONB NOT NULL DEFAULT '[]',
            updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
            ALTER TABLE vera_notification_group ENABLE ROW LEVEL SECURITY;
            REVOKE ALL ON vera_notification_group FROM PUBLIC;
            DO $$ BEGIN
              IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON vera_notification_group FROM anon; END IF;
              IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON vera_notification_group FROM authenticated; END IF;
            END $$;'''))
    if conn.execute(text("SELECT to_regclass('public.vera_notification_route')")).scalar_one_or_none():
        return
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera.notification.schema'))"))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_notification_route (
        key TEXT PRIMARY KEY, source_key TEXT NOT NULL, label TEXT NOT NULL,
        recipients JSONB NOT NULL DEFAULT '[]', channels JSONB NOT NULL DEFAULT '[]',
        custom BOOLEAN NOT NULL DEFAULT FALSE, updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
        CREATE TABLE IF NOT EXISTS vera_notification_config (
        id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0, ordering JSONB NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS vera_notification_group (
        key TEXT PRIMARY KEY, label TEXT NOT NULL, members JSONB NOT NULL DEFAULT '[]',
        updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
        INSERT INTO vera_notification_config(id) VALUES(1) ON CONFLICT DO NOTHING;
        CREATE TABLE IF NOT EXISTS vera_notification_delivery (
        id BIGSERIAL PRIMARY KEY, event_key TEXT NOT NULL, rule_key TEXT NOT NULL,
        recipient TEXT NOT NULL, channel TEXT NOT NULL, payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), read_at TIMESTAMPTZ,
        sent_at TIMESTAMPTZ, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        claimed_at TIMESTAMPTZ, last_error TEXT, sent_subscriptions JSONB NOT NULL DEFAULT '[]',
        UNIQUE(event_key,rule_key,recipient,channel));
        CREATE INDEX IF NOT EXISTS vera_notification_pending ON vera_notification_delivery(next_attempt_at) WHERE sent_at IS NULL AND channel='push';
        ALTER TABLE vera_notification_route ENABLE ROW LEVEL SECURITY;
        ALTER TABLE vera_notification_config ENABLE ROW LEVEL SECURITY;
        ALTER TABLE vera_notification_group ENABLE ROW LEVEL SECURITY;
        ALTER TABLE vera_notification_delivery ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON vera_notification_route,vera_notification_config,vera_notification_delivery,vera_notification_group FROM PUBLIC;
        DO $$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON vera_notification_route,vera_notification_config,vera_notification_delivery,vera_notification_group FROM anon;
          END IF;
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON vera_notification_route,vera_notification_config,vera_notification_delivery,vera_notification_group FROM authenticated;
          END IF;
        END $$;
    '''))


def fingerprint(source, payload):
    # Ignore changing countdown/body for stable event tags supplied by the source.
    identity = payload.get('event_id') or payload.get('tag') or json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(f'{source}:{identity}'.encode()).hexdigest()


RECIPIENT_GROUPS = {
    'group:nhanvien': 'Nhân viên', 'group:letan': 'Lễ tân',
    'group:watchers': 'Người theo dõi', 'group:quanly': 'Quản lý',
    'group:giamdoc': 'Giám đốc', 'group:all': 'Tất cả tài khoản', 'group:admin': 'Admin', 'group:leader':'Leader',
}


def recipient_membership_sql(recipients='r.recipients', source='r.source_key', watched_date=':watched_date'):
    """Trusted SQL fragments only; the account alias p must be joined and active."""
    return f"""({recipients} ? p.auth_user_id::text
        OR {recipients} ? 'group:all'
        OR (p.role IN ('nhanvien','leader','letan','quanly','giamdoc','admin')
            AND {recipients} ? ('group:' || p.role))
        OR ({recipients} ? 'group:watchers' AND {source}='leave_watch'
            AND EXISTS(SELECT 1 FROM vera_v2_leave_watch w
                WHERE w.auth_user_id=p.auth_user_id AND w.watched_date::text={watched_date}))
        OR EXISTS(SELECT 1 FROM vera_notification_group g
            WHERE {recipients} ? g.key AND g.members ? p.auth_user_id::text))"""


def resolve_recipients(conn, values, source, payload):
    # Legacy explicit-ID rules keep their existing path; inserts still check active accounts.
    if not any(value.startswith('group:') for value in values):
        return set(values)
    predicate=recipient_membership_sql('CAST(:recipients AS jsonb)', ':source')
    return {str(row['id']) for row in conn.execute(text(
        'SELECT p.auth_user_id::text AS id FROM vera_v2_user_profile p WHERE p.is_active AND '+predicate),
        {'recipients':json.dumps(values),'source':source,'watched_date':payload.get('watched_date')}).mappings()}


def enqueue(conn, source_key, payload, event_key=None):
    if source_key == 'leave_quota_exceeded' and quota_month(payload) != current_month():
        return True  # Handled: do not fall back to sending an expired quota notice.
    ensure_schema(conn)
    rules = [dict(row) for row in conn.execute(text('''SELECT r.*, COALESCE(s.enabled,TRUE) AS enabled
        FROM vera_notification_route r LEFT JOIN vera_v2_notification_setting s ON s.notification_key=r.key
        WHERE r.source_key=:source'''), {'source': source_key}).mappings()]
    handled = any(not row['custom'] for row in rules)
    event_key = event_key or fingerprint(source_key, payload)
    # Store plain text and a fixed application URL, never arbitrary HTML or external links.
    title = str(payload.get('title') or 'Thông báo').strip()
    if title.upper().startswith('VERA SPA'):
        title = title[8:].lstrip(' ·:-–') or 'Thông báo'
    safe = {'title': title[:160], 'body': str(payload.get('body') or '')[:2000],
            'url': APP_URL, 'tag': event_key, 'kind': str(payload.get('kind') or source_key)[:80]}
    if source_key == 'leave_quota_exceeded':
        safe['quota_month'] = quota_month(payload)
    if source_key == 'leave_watch' and payload.get('watched_date'):
        from datetime import date
        try: safe['watched_date'] = date.fromisoformat(str(payload['watched_date'])).isoformat()
        except ValueError: pass
    for rule in rules:
        if not rule['enabled']:
            continue
        disabled_channels = {row['channel'] for row in conn.execute(text('''SELECT channel
            FROM vera_v2_notification_channel_setting WHERE notification_key=:key AND enabled=FALSE'''),
            {'key':rule['key']}).mappings()}
        for recipient in resolve_recipients(conn, rule['recipients'], source_key, safe):
            # Mid-shift reminders belong to the employee. Admins only receive
            # the overdue event, even when a broad rule targets all accounts.
            if source_key == 'attendance_break' and payload.get('kind') == 'attendance-break-reminder':
                admin = conn.execute(text('''SELECT 1 FROM vera_v2_user_profile
                    WHERE auth_user_id::text=:recipient AND lower(role)='admin' '''),
                    {'recipient': recipient}).scalar_one_or_none()
                if admin:
                    continue
            for channel in set(rule['channels']):
                if channel in disabled_channels: continue
                conn.execute(text('''INSERT INTO vera_notification_delivery(event_key,rule_key,recipient,channel,payload)
                    SELECT :event,:rule,:recipient,:channel,CAST(:payload AS jsonb)
                    WHERE EXISTS(SELECT 1 FROM vera_v2_user_profile WHERE auth_user_id::text=:recipient AND is_active)
                    ON CONFLICT DO NOTHING'''), {'event': event_key, 'rule': rule['key'], 'recipient': recipient,
                    'channel': channel, 'payload': json.dumps({**safe, **({'title':str(rule.get('label') or safe['title'])[:160]} if rule['custom'] else {})}, ensure_ascii=False)})
    return handled


def route_event(engine, source_key, payload, event_key=None):
    """Called after business transactions. Failure must not fall back to unintended recipients."""
    with engine.begin() as conn:
        return enqueue(conn, source_key, payload, event_key)


def dispatch_pending(engine, send, vault, limit=30):
    with engine.begin() as conn:
        ensure_schema(conn)
        rows = [dict(row) for row in conn.execute(text('''WITH pending AS (
          SELECT id FROM vera_notification_delivery WHERE channel='push' AND sent_at IS NULL
          AND next_attempt_at<=NOW() AND (claimed_at IS NULL OR claimed_at<NOW()-INTERVAL '5 minutes')
          ORDER BY id FOR UPDATE SKIP LOCKED LIMIT :limit)
          UPDATE vera_notification_delivery d SET claimed_at=NOW(), attempts=attempts+1
          FROM pending p WHERE d.id=p.id RETURNING d.*'''), {'limit': limit}).mappings()]
    for row in rows:
        error = None
        sent_ids = set(row.get('sent_subscriptions') or [])
        try:
            with engine.connect() as conn:
                # Recheck current recipient/channel grants before delivering a queued notification.
                allowed = conn.execute(text(f'''SELECT 1 FROM vera_notification_route r
                    JOIN vera_v2_user_profile p ON p.auth_user_id::text=:recipient AND p.is_active
                    LEFT JOIN vera_v2_notification_setting s ON s.notification_key=r.key
                    LEFT JOIN vera_v2_notification_channel_setting cs ON cs.notification_key=r.key AND cs.channel='push'
                    WHERE r.key=:key AND {recipient_membership_sql()} AND r.channels ? 'push'
                    AND {current_quota_sql(payload='CAST(:payload AS jsonb)')}
                    AND COALESCE(s.enabled,TRUE) AND COALESCE(cs.enabled,TRUE)
                    AND NOT (r.source_key='attendance_break' AND p.role='admin'
                        AND :kind='attendance-break-reminder')'''), {'key': row['rule_key'], 'recipient': row['recipient'], 'watched_date':row['payload'].get('watched_date'), 'kind':row['payload'].get('kind'), 'payload': json.dumps(row['payload'])}).scalar_one_or_none()
                subscriptions = [dict(r) for r in conn.execute(text('''SELECT subscription_id::text AS subscription_id,
                    endpoint,p256dh,auth_secret FROM vera_v2_push_subscription
                    WHERE auth_user_id::text=:recipient AND is_active'''), {'recipient': row['recipient']}).mappings()] if allowed else []
                private_key = vault(conn, 'vera_v2_vapid_private_key') if allowed else ''
                subject = vault(conn, 'vera_v2_vapid_subject') or APP_URL if allowed else APP_URL
            complete = not allowed
            if allowed:
                if not subscriptions or not private_key:
                    error = 'Chưa có thiết bị đăng ký hoặc chưa cấu hình Web Push.'
                else:
                    dead_ids = set()
                    for subscription in subscriptions:
                        sid = subscription['subscription_id']
                        if sid in sent_ids:
                            continue
                        ok, status, _ = send({**subscription, 'payload': {**row['payload'], 'notification_id': str(row['id']), 'url': APP_URL + '?notification=' + str(row['id'])}}, private_key, subject)
                        if status in (404, 410): dead_ids.add(sid)
                        if ok or status in (404, 410):
                            sent_ids.add(sid)
                        else:
                            error = 'Gửi Web Push chưa thành công; hệ thống sẽ thử lại.'
                        with engine.begin() as conn:
                            if status in (404, 410):
                                conn.execute(text('UPDATE vera_v2_push_subscription SET is_active=FALSE WHERE subscription_id::text=:id'), {'id': sid})
                            conn.execute(text('UPDATE vera_notification_delivery SET sent_subscriptions=CAST(:ids AS jsonb) WHERE id=:id'), {'ids': json.dumps(sorted(sent_ids)), 'id': row['id']})
                    complete = all(s['subscription_id'] in sent_ids for s in subscriptions) and any(s['subscription_id'] not in dead_ids for s in subscriptions)
            with engine.begin() as conn:
                conn.execute(text('''UPDATE vera_notification_delivery SET claimed_at=NULL,last_error=:error,
                    sent_at=CASE WHEN :complete THEN NOW() ELSE NULL END,
                    next_attempt_at=NOW()+INTERVAL '1 minute' * LEAST(60, attempts * 2) WHERE id=:id'''),
                    {'id': row['id'], 'error': error, 'complete': complete})
        except Exception:
            # Claims expire so another process can retry. Do not log delivery payloads/secrets.
            logging.getLogger(__name__).warning('Notification delivery deferred: id=%s', row['id'])

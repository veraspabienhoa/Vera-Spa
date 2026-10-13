"""Enqueue early completion notices atomically; the delivery worker sends push."""
import hashlib
import json
import logging
from sqlalchemy import text

SOURCE = 'service_completed_early'


def completion_events(result):
    candidates = []
    def walk(value):
        if not isinstance(value, dict):
            return
        if value.get('employee'):
            candidates.append(value['employee'])
        candidates.extend((value.get('pending') or {}).get('entries', []))
        for item in value.get('items', []):
            walk(item)
    walk(result)
    events = {}
    for row in candidates:
        delta = row.get('completion_delta_minutes')
        if delta is None or float(delta) > -5 or not row.get('completed_at') or not row.get('started_at'):
            continue
        username = str(row.get('username') or row.get('employee_name') or row.get('name') or '').strip()
        if not username:
            continue
        identity = [SOURCE, row.get('employee_id') or row.get('id'), row.get('started_at'), row.get('completed_at')]
        event = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        reason = str(row.get('early_completion_reason') or '').strip() or 'Chưa có lý do'
        events[event] = {'event': event, 'username': username, 'payload': {
            'title': 'Dịch vụ hoàn thành sớm',
            'body': f"{username} · {row.get('service') or 'Dịch vụ'} · Phòng {row.get('room') or '—'} · Sớm {abs(int(delta))} phút · Thực hiện: {row.get('started_by') or '—'} · Hoàn thành: {row.get('completed_by') or '—'} · Lý do ra sớm: {reason}",
            'employee': username, 'kind': SOURCE, '_source_key': SOURCE, 'tag': SOURCE + '-' + event,
            'url': 'https://app.veraspa.vn/',
        }}
    return list(events.values())


def enqueue_early_completions(conn, result):
    events = completion_events(result)
    if not events:
        return
    try:
        with conn.begin_nested():
            conn.execute(text('''INSERT INTO vera_notification_delivery(event_key,rule_key,recipient,channel,payload)
                SELECT e.event,'native:service_completed_early',p.auth_user_id::text,c.channel,
                    e.payload || jsonb_build_object('_native_recipients',jsonb_build_array(p.auth_user_id::text))
                FROM jsonb_to_recordset(CAST(:events AS jsonb)) AS e(event text,username text,payload jsonb)
                JOIN vera_v2_user_profile p ON p.is_active AND
                    (p.role IN ('admin','quanly','letan') OR lower(btrim(p.employee_username))=lower(btrim(e.username)))
                CROSS JOIN (VALUES ('in_app'),('popup'),('push')) c(channel)
                WHERE NOT EXISTS(SELECT 1 FROM vera_v2_notification_setting s WHERE s.notification_key='service_completed_early' AND NOT s.enabled)
                  AND NOT EXISTS(SELECT 1 FROM vera_v2_notification_channel_setting cs WHERE cs.notification_key='service_completed_early' AND cs.channel=c.channel AND NOT cs.enabled)
                ON CONFLICT(event_key,rule_key,recipient,channel) DO NOTHING'''), {'events': json.dumps(events, ensure_ascii=False)})
    except Exception:
        logging.getLogger(__name__).warning('Early completion notification enqueue failed; completion remains valid')

"""Bounded, transactional booking notices. Network delivery belongs to the worker."""
import hashlib
import json
import logging
from sqlalchemy import text

SOURCE = 'live_tour_booking'


def enqueue_bookings(conn, action, result, operation_key):
    if action not in {'booking', 'multi_booking'}:
        return
    workers = [result.get('employee')] if action == 'booking' else result.get('employees', [])
    events = []
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        # The persisted roster username owns the assignment; never use customer
        # names, fuzzy matching, request-supplied recipients or all-staff groups.
        username = str(worker.get('username') or worker.get('name') or '').strip()
        if not username:
            continue
        event = hashlib.sha256(f'{SOURCE}:{operation_key}:{worker["id"]}'.encode()).hexdigest()
        body = ' | '.join(str(value or '—').strip() for value in (
            worker.get('name') or username, worker.get('service'), worker.get('request') or 'Tua', worker.get('room')))
        events.append({'event': event, 'username': username, 'payload': {
            'title': 'Booking mới', 'body': body[:2000], 'kind': SOURCE,
            'tag': 'vera-booking-' + event, 'url': 'https://app.veraspa.vn/',
            '_source_key': SOURCE, '_booking_username': username,
        }})
    if not events:
        return
    try:
        # One INSERT for all booked staff and both channels; no schema checks,
        # extra connection, polling request, catalog read or network send here.
        # A failed notification write must not poison the booking transaction.
        with conn.begin_nested():
            conn.execute(text('''INSERT INTO vera_notification_delivery
                (event_key,rule_key,recipient,channel,payload)
                SELECT e.event,'native:live_tour_booking',p.auth_user_id::text,c.channel,
                    e.payload || jsonb_build_object('_native_recipients',jsonb_build_array(p.auth_user_id::text))
                FROM jsonb_to_recordset(CAST(:events AS jsonb)) AS e(event text,username text,payload jsonb)
                JOIN vera_v2_user_profile p ON lower(btrim(p.employee_username))=lower(btrim(e.username)) AND p.is_active
                CROSS JOIN (VALUES ('in_app'),('push')) c(channel)
                WHERE NOT EXISTS(SELECT 1 FROM vera_v2_notification_setting s
                    WHERE s.notification_key='live_tour_booking' AND NOT s.enabled)
                  AND NOT EXISTS(SELECT 1 FROM vera_v2_notification_channel_setting cs
                    WHERE cs.notification_key='live_tour_booking' AND cs.channel=c.channel AND NOT cs.enabled)
                ON CONFLICT(event_key,rule_key,recipient,channel) DO NOTHING'''),
                {'events': json.dumps(events, ensure_ascii=False)})
    except Exception:
        logging.getLogger(__name__).warning('Booking notification enqueue failed; booking remains valid')

"""Default event audiences, independent of whether an account owns a push device.

Configured routes still override the native audience. No browser-supplied list
is accepted here; producers supply event context or their resolved usernames.
"""
from sqlalchemy import text

GROUPS = {
    'leave_quota_exceeded': ['group:admin'],
    'admin_leave_changes': ['group:admin'],
    'long_leave_requests': ['group:admin'],
    'admin_daily_summary': ['group:admin'],
    'revenue_manual_changes': ['group:admin'],
    'purchase_reconcile': ['group:admin', 'group:quanly', 'group:letan'],
    'live_tour_queue': ['group:admin', 'group:quanly'],
    'leave_watch': ['group:watchers'],
}
NATIVE_SOURCES = frozenset(GROUPS) | {
    'training_completed', 'training_cycle', 'auto_penalty', 'missing_checkin',
    'attendance_break', 'birthday', 'profile_completion', 'live_tour_booking',
}


def native_audience(conn, source, payload, usernames=None, account_ids=None):
    if source not in NATIVE_SOURCES:
        return None
    recipients = list(GROUPS.get(source, []))
    names = set(usernames or [])
    if source in {'auto_penalty', 'missing_checkin'}:
        names.add(str(payload.get('employee') or ''))
        if source == 'missing_checkin':
            recipients += ['group:admin', 'group:quanly', 'group:letan']
        elif payload.get('department'):
            # The producer has already checked the department notification switch.
            from vera_web_v2_department_attendance import DEPARTMENTS
            if payload.get('department') in DEPARTMENTS:
                recipients += ['group:admin', 'group:quanly']
    if source == 'attendance_break':
        if payload.get('kind') == 'attendance-break-reminder':
            names.add(str(payload.get('employee') or ''))
        else:
            recipients += ['group:admin', 'group:quanly', 'group:letan']
    names = sorted({name.strip().lower() for name in names if str(name).strip()})
    if names:
        recipients += [str(row['id']) for row in conn.execute(text('''
            SELECT auth_user_id::text AS id FROM vera_v2_user_profile
            WHERE is_active AND lower(btrim(employee_username))=ANY(CAST(:names AS text[]))
        '''), {'names': names}).mappings()]
    recipients += list(account_ids or [])
    return sorted(set(recipients))


def public_payload(payload):
    return {key: value for key, value in payload.items() if not key.startswith('_')}


def source_sql():
    return "COALESCE(r.source_key,d.payload->>'_source_key')"


def delivery_joins():
    return f'''FROM vera_notification_delivery d
        LEFT JOIN vera_notification_route r ON r.key=d.rule_key
        JOIN vera_v2_user_profile p ON p.auth_user_id::text=d.recipient AND p.is_active
        LEFT JOIN vera_v2_notification_setting s ON s.notification_key=COALESCE(r.key,{source_sql()})
        LEFT JOIN vera_v2_notification_channel_setting cs
          ON cs.notification_key=COALESCE(r.key,{source_sql()}) AND cs.channel=d.channel'''


def delivery_access_sql():
    from vera_notification_delivery import recipient_membership_sql
    from vera_notification_periods import current_quota_sql
    native = recipient_membership_sql("d.payload->'_native_recipients'", "d.payload->>'_source_key'", "d.payload->>'watched_date'")
    configured = recipient_membership_sql(watched_date="d.payload->>'watched_date'")
    sources = ','.join("'" + key + "'" for key in sorted(NATIVE_SOURCES))
    return f'''(
        (r.key IS NOT NULL AND {configured}
          AND (r.channels ? d.channel OR (d.channel IN ('in_app','push') AND r.channels ?| ARRAY['in_app','push'])))
        OR (d.rule_key='native:' || (d.payload->>'_source_key')
          AND d.payload->>'_source_key' IN ({sources}) AND {native}
          AND NOT EXISTS(SELECT 1 FROM vera_notification_route override WHERE override.key=d.payload->>'_source_key'))
        ) AND COALESCE(s.enabled,TRUE) AND COALESCE(cs.enabled,TRUE)
        AND {current_quota_sql(source=source_sql())}
        AND ({source_sql()}<>'live_tour_booking' OR lower(btrim(p.employee_username))=lower(btrim(d.payload->>'_booking_username')))
        AND ({source_sql()}<>'attendance_break' OR d.payload->>'kind' IN ('attendance-break-cleared','attendance-break-global-disabled')
          OR NOT EXISTS(SELECT 1 FROM vera_app_setting a WHERE
            (a.category='attendance_break_alert_control' AND a.setting_key='global' AND a.value_json->>'disabled'='true')
            OR (a.category='attendance_break_alert' AND a.setting_key=split_part(d.event_key,':',1)
                AND COALESCE(a.value_json->>'globally_deleted_at','')<>'')))
        AND NOT ({source_sql()}='attendance_break' AND lower(p.role)='admin'
                 AND d.payload->>'kind'='attendance-break-reminder')'''

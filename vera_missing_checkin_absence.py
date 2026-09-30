"""Current-day absence rule, evaluated only after a complete FaceGate refresh.

All business writes and durable notifications share the caller's transaction.
No device/network calls, nested connections, historical backfill or payroll writes.
"""
import json
from datetime import datetime, time, timedelta

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

import vera_auto_check as auto_check
from vera_facegate_control_log import VN_TZ

KEY = 'missing_checkin_absence'
SOURCE = 'VERA · TỰ ĐỘNG NGHỈ KHÔNG PHÉP'
REASONS = ('Nghỉ KHÔNG phép', 'Nghỉ CUỐI TUẦN KHÔNG phép')


class PolicyUpdate(BaseModel):
    enabled: bool
    ca1_enabled: bool
    ca2_enabled: bool
    expected_revision: int = Field(ge=0)


def load_policy(conn):
    row = conn.execute(text("SELECT value_json, revision FROM vera_app_setting WHERE category='leave_rules' AND setting_key=:key"), {'key': KEY}).mappings().first()
    value = row['value_json'] if row else {}
    return {**{k: value.get(k, True) is True for k in ('enabled', 'ca1_enabled', 'ca2_enabled')},
            'revision': int(row['revision'] or 0) if row else 0,
            'ca1_cutoff': '17:00', 'ca2_cutoff': '19:00', 'delay_minutes': 120, 'reasons': list(REASONS)}


def install_routes(app, *, engine_instance, current_identity, require_feature, identity_type):
    @app.put('/v2/rules/missing-checkin-absence')
    def save_policy(body: PolicyUpdate, ident: identity_type = Depends(current_identity)):
        if str(getattr(ident, 'role', '')).strip().lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được thay đổi nội quy tự động nghỉ không phép.')
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'official_rules_edit')
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:missing-checkin-absence'))"))
            current = load_policy(conn)
            if current['revision'] != body.expected_revision:
                raise HTTPException(409, 'Nội quy đã thay đổi. Hãy làm mới trước khi lưu.')
            value = {k: getattr(body, k) for k in ('enabled', 'ca1_enabled', 'ca2_enabled')}
            conn.execute(text('''INSERT INTO vera_app_setting(category,setting_key,value_json,revision,source,updated_by,created_at,updated_at)
                VALUES('leave_rules',:key,CAST(:value AS jsonb),1,'web_v2_rules',:actor,NOW(),NOW())
                ON CONFLICT(category,setting_key) DO UPDATE SET value_json=EXCLUDED.value_json,
                revision=vera_app_setting.revision+1,source=EXCLUDED.source,updated_by=EXCLUDED.updated_by,updated_at=NOW()'''),
                {'key': KEY, 'value': json.dumps(value), 'actor': ident.employee_username})
            return {**load_policy(conn), 'message': 'Đã lưu. Áp dụng từ lượt đồng bộ kế tiếp; không xử lý lại ngày cũ.'}


def deadline_for(row, day, policy):
    shift = auto_check._norm(row.get('shift_code')).replace(' ', '')
    hour = {'ca1': 15, 'ca2': 17}.get(shift)
    if hour is None or not policy.get(shift + '_enabled'):
        return None
    return datetime.combine(day, time(hour), tzinfo=VN_TZ) + timedelta(hours=2)


def eligible_schedule(row, *, now, synced, policy, mapped, checked, leave_names):
    username = str(row.get('employee_username') or '').strip()
    cutoff = deadline_for(row, now.date(), policy)
    if not cutoff or now <= cutoff or synced <= cutoff:
        return False
    if username not in mapped or username in checked:
        return False
    # Unclear/manual leave registrations are preserved for human review. A late
    # registration alone still requires an arrival by the prescribed cutoff.
    aliases = {auto_check._norm(username), auto_check._norm(row.get('employee_name'))} - {''}
    return not bool(aliases & leave_names)



def permitted_late(reason):
    key = auto_check._norm(reason)
    return 'di tre' in key and 'co phep' in key and 'khong phep' not in key


def absence_item(catalog, day, half_day):
    if not half_day:
        return auto_check.catalog_item(catalog, REASONS[day.weekday() >= 5])
    # Operator-confirmed half-day equivalents use the existing official rules.
    reason = ('Về sớm KHÔNG phép', 'Về sớm CUỐI TUẦN KHÔNG phép')[day.weekday() >= 5]
    return auto_check.catalog_item(catalog, reason)


def replace_unpermitted(conn, rows, *, day, username, target_reason):
    if not rows:
        return
    # Archive the complete rows before removal, in the same transaction as the
    # replacement. Only today's exact employee and unpermitted rows qualify.
    conn.execute(text('CREATE TABLE IF NOT EXISTS vera_absence_replacement_audit '
                      '(id bigserial PRIMARY KEY, work_date date NOT NULL, employee_name text NOT NULL, '
                      'replaced_rows jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT NOW())'))
    conn.execute(text('INSERT INTO vera_absence_replacement_audit(work_date,employee_name,replaced_rows) '
                      'VALUES(:day,:name,CAST(:rows AS jsonb))'),
                 {'day': day, 'name': username, 'rows': json.dumps([dict(r) for r in rows], default=str, ensure_ascii=False)})
    for row in rows:
        if not row.get('record_uid'):
            raise RuntimeError('replacement_requires_record_uid')
        conn.execute(text("UPDATE vera_auto_check_event SET status=CASE WHEN reason=:reason THEN 'revoked' ELSE 'superseded' END, "
                          "leave_record_uid=NULL,employee_notify_claimed_at=NULL,employee_notified_at=NOW() "
                          "WHERE leave_record_uid=:uid"), {'uid': row['record_uid'], 'reason': target_reason})
        deleted = conn.execute(text('DELETE FROM leave_records WHERE record_uid=:uid AND leave_date=:day AND employee_name=:name'),
                               {'uid': row['record_uid'], 'day': day, 'name': username})
        if deleted.rowcount != 1:
            raise RuntimeError('replacement_row_changed')

def process(conn, *, now=None):
    from vera_attendance_source import source_for
    import vera_facegate_attendance as fg
    from vera_facegate_runtime import archive_complete
    from vera_attendance_participation import suspended
    from vera_missing_checkin_notifications import _staff_scheduled_rows, _scheduled_rows, _merge_schedules
    from vera_resource_concurrency import lock_transition
    from vera_notification_delivery import enqueue

    now = now or datetime.now(VN_TZ)
    now = now.replace(tzinfo=VN_TZ) if now.tzinfo is None else now.astimezone(VN_TZ)
    day = now.date()
    result = {'added': 0, 'skipped': 0}
    if source_for(day) != 'facegate':
        return {**result, 'reason': 'facegate_not_selected'}
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:missing-checkin-absence'))"))
    policy = load_policy(conn)
    if not policy['enabled']:
        return {**result, 'reason': 'disabled'}
    if auto_check.load_config(conn)['status'] == 'PAUSED':
        return {**result, 'reason': 'auto_penalty_paused'}
    data = fg.project_evidence(conn, day, day)
    if not data['rows'] or not archive_complete(data, day) or any(i.get('reason') != 'no_vera_shift' for i in data['issues']):
        return {**result, 'reason': 'incomplete_or_ambiguous_evidence'}
    saved = next(s for s in data['syncs'] if str(s['work_date']) == day.isoformat())
    synced = datetime.fromisoformat(str(saved['last_synced_at'])).astimezone(VN_TZ)
    if not 0 <= (now - synced).total_seconds() <= 300:
        return {**result, 'reason': 'stale_evidence'}
    mapped = {m['username'] for m in data['index'].values() if not suspended(m['username'], day)}
    # Any mapped scan is evidence of presence: do not invent an absence because
    # a scan has an unexpected status or the attendance projection is pending.
    checked = {r.get('EmployeeName') for r in data['rows']}
    schedules = _merge_schedules(_staff_scheduled_rows(conn, day), _scheduled_rows(conn, day))
    catalog = auto_check.load_catalog(conn)
    auto_check.ensure_schema(conn)
    for row in sorted(schedules, key=lambda r: str(r.get('employee_username') or '')):
        username = str(row.get('employee_username') or '').strip()
        if not username or username not in mapped or row.get('employee_role') not in {'nhanvien', 'leader', 'letan', 'locker', 'tapvu', 'support'}:
            continue
        lock_transition(conn, [('leave_employee', username)], legacy_keys=['vera:phase4:leave_primary'])
        # A reviewed/revoked event is still a completed decision for this day.
        # Never re-create a penalty that management deliberately removed.
        prior = conn.execute(text('SELECT id FROM vera_auto_check_event WHERE work_date=:day AND employee_name=:name AND source=:source LIMIT 1'),
                             {'day': day, 'name': username, 'source': SOURCE}).mappings().first()
        if prior:
            result['skipped'] += 1
            continue
        leaves = conn.execute(text('SELECT * FROM leave_records WHERE leave_date=:day AND employee_name=:name FOR UPDATE'), {'day': day, 'name': username}).mappings().all()
        leave_names = {auto_check._norm(r['employee_name']) for r in leaves
                       if 'di tre' not in auto_check._norm(r['leave_reason']) and 'khong phep' not in auto_check._norm(r['leave_reason'])}
        if not eligible_schedule(row, now=now, synced=synced, policy=policy, mapped=mapped, checked=checked, leave_names=leave_names):
            result['skipped'] += 1
            continue
        # A registered full-day absence already records the missing check-in.
        # Preserve its identity, ordinal and penalty, even alongside a late row.
        if any(auto_check._norm(r['leave_reason']) == auto_check._norm(REASONS[day.weekday() >= 5]) for r in leaves):
            result['skipped'] += 1
            continue
        half_day = any(permitted_late(r['leave_reason']) for r in leaves)
        item = absence_item(catalog, day, half_day)
        if not item:
            result['skipped'] += 1
            result.setdefault('review_required', []).append({'employee': username, 'reason': 'missing_half_day_official_reason' if half_day else 'missing_official_reason'})
            continue
        if any(auto_check._norm(r['leave_reason']) == auto_check._norm(item['name']) for r in leaves):
            result['skipped'] += 1
            continue
        # Re-read after the employee/leave lock, immediately before any deletion
        # or penalty. A newer scan or incomplete refresh cancels the operation.
        fresh = fg.project_evidence(conn, day, day)
        if (not fresh['rows'] or not archive_complete(fresh, day)
                or any(i.get('reason') != 'no_vera_shift' for i in fresh['issues'])
                or username in {r.get('EmployeeName') for r in fresh['rows']}):
            result['skipped'] += 1
            continue
        latest = next((s for s in fresh['syncs'] if str(s['work_date']) == day.isoformat()), None)
        latest_sync = datetime.fromisoformat(str(latest['last_synced_at'])).astimezone(VN_TZ) if latest else None
        cutoff = deadline_for(row, day, policy)
        if latest_sync is None or latest_sync <= cutoff or not 0 <= (now-latest_sync).total_seconds() <= 300:
            result['skipped'] += 1
            continue
        synced = latest_sync
        detail = f"{row['shift_code']} · quá {cutoff:%H:%M} chưa có check-in (đã chờ thêm 120 phút) · nguồn FaceGate đủ và mới lúc {synced:%H:%M:%S} · nội quy phiên bản {policy['revision']}"
        replacement = conn.begin_nested()
        replace_unpermitted(conn, [r for r in leaves if 'khong phep' in auto_check._norm(r['leave_reason'])],
                            day=day, username=username, target_reason=item['name'])
        ok, status = auto_check.save_violation(conn, work_date=day, employee=username, reason_item=item, detail=detail, source=SOURCE)
        if not ok:
            raise RuntimeError('absence_write_failed')
        if status != 'ADDED':
            replacement.rollback()
            result['skipped'] += 1
            continue
        replacement.commit()
        event = conn.execute(text('''SELECT e.id, e.leave_record_uid, l.penalty FROM vera_auto_check_event e
            JOIN leave_records l ON l.record_uid=e.leave_record_uid
            WHERE e.work_date=:day AND e.employee_name=:name AND e.reason=:reason AND e.status='added' '''),
            {'day': day, 'name': username, 'reason': item['name']}).mappings().one()
        tag = f"vera-absence-{event['id']}"
        enqueue(conn, KEY, {'title': 'Tự động ghi nghỉ không phép', 'employee': username,
            'kind': KEY, 'tag': tag,
            'body': f"{username} · {day:%d-%m-%Y} · {row['shift_code']} · {item['name']} · Mức phạt: {float(event['penalty'] or 0):,.0f}đ. {detail}"}, event_key=tag)
        # Delivery is now owned by the durable notification outbox. Prevent the
        # generic penalty producer from duplicating/bypassing this setting.
        conn.execute(text('UPDATE vera_auto_check_event SET employee_notified_at=NOW() WHERE id=:id'), {'id': event['id']})
        result['added'] += 1
    return result

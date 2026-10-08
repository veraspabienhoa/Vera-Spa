"""Official FaceGate reader and cache publisher, using caller-owned connections.

The immutable archive is authoritative; the separate cache is an invalidation
and freshness signal. No TimeSoft history is overwritten or used as fallback.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from vera_facegate_control_log import VN_TZ
import vera_facegate_attendance as fg
import vera_attendance_participation as participation


def archive_complete(data, day, *, after=None):
    saved = next((s for s in data['syncs'] if str(s['work_date']) == day.isoformat()), None)
    if not saved:
        return False
    try:
        synced = datetime.fromisoformat(str(saved['last_synced_at'])).astimezone(VN_TZ)
        count = sum(str(e['occurred_at'])[:10] == day.isoformat() for e in data['events'])
        return int(saved['last_observed_count']) == count and (not after or synced >= after)
    except (ValueError, TypeError):
        return False


def annotate(records, data, *, now=None):
    now = now or datetime.now(VN_TZ)
    mapped = {m['username'] for m in data['index'].values()}
    blocking = [i for i in data['issues'] if i.get('reason') != 'no_vera_shift']
    identity_reviews = defaultdict(set)
    for scan in data.get('rows', []):
        if scan.get('_vera_identity_review_id'):
            identity_reviews[(scan.get('EmployeeName'), scan.get('WorkDateStr'))].add(scan['_vera_identity_review_id'])
    participating = []
    for row in records:
        day = datetime.strptime(row['date'], '%d/%m/%Y').date()
        if participation.suspended(row['employee_name'], day):
            continue
        participating.append(row)
        reasons = []
        username = row['employee_name']
        if username not in mapped:
            reasons.append('unmapped_employee')
        if any(not i.get('username') or i['username'] == username for i in blocking):
            reasons.append('unresolved_evidence')
        interval = fg.shift_interval(day, row.get('shift_start'), row.get('shift_end'))
        if not interval and not row.get('shift') and row.get('employee_role') != 'admin':
            reasons.append('missing_vera_shift')
        if row.get('attendance_expected'):
            if not row.get('check_in'):
                reasons.append('missing_check_in')
            if not row.get('check_out'):
                reasons.append('missing_check_out')
            if not interval:
                reasons.append('missing_vera_shift')
            else:
                # A current/overnight shift remains open until its evidence
                # window closes. Never interpret a mid-shift scan as final pay.
                close_at = (interval[1] + timedelta(hours=2)).replace(tzinfo=VN_TZ)
                if now < close_at:
                    reasons.append('shift_still_open')
                if not archive_complete(data, day):
                    reasons.append('incomplete_archive')
                if not archive_complete(data, close_at.date(), after=close_at):
                    reasons.append('incomplete_archive')
        row.update(attendance_source='FaceGate · Lịch VERA', evidence_source='facegate',
                   attendance_preview=False, attendance_pending=bool(reasons),
                   attendance_pending_reasons=sorted(set(reasons)),
                   payable_minutes_verified=bool(row.get('check_in') and row.get('check_out') and not reasons),
                   identity_verified=username in mapped,
                   attendance_evidence_issues=bool(blocking))
        row['applied_identity_review_ids'] = sorted(identity_reviews[(username, row['date'])])
        if row.get('attendance_roster_only'):
            row['attendance_note'] = 'Chờ đăng ký Face ID' if username not in mapped else 'Chưa ghi nhận lượt quét phù hợp'
    return participating


def records(conn, start, end):
    import vera_web_v2_attendance_query_perf as attendance
    result = []
    left = start
    while left <= end:
        right = min(end, left + timedelta(days=6))
        data = fg.project_evidence(conn, left, right)
        rows = attendance._records_v42_fast(conn, left, right, datasets=[{'payload': data['rows']}])
        rows = fg.finish_records(rows, data['applied_reviews'])
        result.extend(annotate(rows, data))
        left = right + timedelta(days=1)
    return result


def publish(conn, start, end, *, now=None):
    """Publish raw mapped scans atomically with Live Tour invalidation.

    No nested pool or device access. The caller commits. Cache freshness never
    advances if the raw archive is stale or incomplete.
    """
    import pandas as pd
    import vera_postgres as vpg
    now = now or datetime.now(VN_TZ)
    data = fg.project_evidence(conn, start, end)
    reports = []
    day = start
    while day <= end:
        saved = next((s for s in data['syncs'] if str(s['work_date']) == day.isoformat()), None)
        if not archive_complete(data, day) or not saved:
            raise fg.EvidenceError('incomplete_archive')
        synced = datetime.fromisoformat(str(saved['last_synced_at'])).astimezone(VN_TZ)
        if not 0 <= (now - synced).total_seconds() <= 300:
            raise fg.EvidenceError('stale_archive')
        rows = [r for r in data['rows'] if r['WorkDateStr'] == day.strftime('%d/%m/%Y')]
        key = 'facegate_employee_checkin_' + day.strftime('%Y%m%d')
        vpg._write_dataset_conn(conn, key, pd.DataFrame(rows), 300, day.isoformat())
        if day == now.date():
            vpg._write_dataset_conn(conn, 'facegate_employee_checkin_today', pd.DataFrame(rows), 300, day.isoformat())
        reports.append({'date': day.isoformat(), 'mapped_scan_count': len(rows),
                        'issue_count': len(data['issues']), 'mapped_employee_count': len(data['index'])})
        day += timedelta(days=1)
    return reports


def worker_frames(conn, dates):
    """One arrival per employee/day for existing late and leave-return rules."""
    import pandas as pd
    from vera_attendance_source import health, source_for
    if not health(conn)['cache_fresh']:
        raise fg.EvidenceError('stale_facegate_source')
    output = []
    for day in dates:
        if source_for(day) != 'facegate':
            continue
        frame = []
        for row in records(conn, day, day):
            if not row.get('check_in') or not row.get('identity_verified') or row.get('attendance_evidence_issues'):
                continue
            frame.append({'WorkDateStr': day.strftime('%d/%m/%Y'),
                          'employeeInfo.Name': row['employee_name'],
                          'employeeInfo.EmployeeCode': row.get('employee_code', ''),
                          'MachineTimeCheckInStr': datetime.fromisoformat(row['check_in_at']).strftime('%d/%m/%Y %H:%M:%S'),
                          'StartWorkTime': row.get('shift_start', ''),
                          'TotalMinuteInGoLate': row.get('late_minutes', 0)})
        output.append((day, pd.DataFrame(frame)))
    return output


def _alert_eligible_users(data, day):
    if any(i.get('reason') != 'no_vera_shift' for i in data['issues']):
        return set()
    return {m['username'] for m in data['index'].values()
            if not participation.suspended(m['username'], day)}


def alert_eligible_users(conn, day):
    return _alert_eligible_users(fg.project_evidence(conn, day, day), day)


def missing_checkin_snapshot(conn, day, *, now):
    """Read popup identities and punches from one verified archive projection.

    Missing punches require a complete, recent archive. Already committed scans
    are visible before a separate attendance-cache publication. Reuse the caller
    connection; never perform device I/O here.
    """
    data = fg.project_evidence(conn, day, day)
    if not archive_complete(data, day):
        return None
    saved = next(s for s in data['syncs'] if str(s['work_date']) == day.isoformat())
    try:
        synced = datetime.fromisoformat(str(saved['last_synced_at']))
        if synced.tzinfo is None:
            return None
        synced = synced.astimezone(VN_TZ)
        if not 0 <= (now - synced).total_seconds() <= 300:
            return None
    except (TypeError, ValueError):
        return None
    return {'payload': data['rows'], 'updated_at': synced,
            'expires_at': synced + timedelta(minutes=5),
            'eligible_users': _alert_eligible_users(data, day)}

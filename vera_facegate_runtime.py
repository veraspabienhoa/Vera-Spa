"""Official FaceGate reader and cache publisher, using caller-owned connections.

The immutable archive is authoritative; the separate cache is an invalidation
and freshness signal. No TimeSoft history is overwritten or used as fallback.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from vera_facegate_control_log import VN_TZ
import vera_facegate_attendance as fg
import vera_attendance_participation as participation


def archive_sync(data, day):
    saved = next((s for s in data.get('syncs', []) if str(s['work_date']) == day.isoformat()), None)
    if not saved:
        return None
    try:
        synced = datetime.fromisoformat(str(saved['last_synced_at']))
        return synced.astimezone(VN_TZ) if synced.tzinfo is not None else None
    except (ValueError, TypeError, KeyError):
        return None


def archive_complete(data, day, *, after=None, before=None):
    saved = next((s for s in data.get('syncs', []) if str(s['work_date']) == day.isoformat()), None)
    synced = archive_sync(data, day)
    if not saved or not synced:
        return False
    try:
        count = 0
        for event in data.get('events', []):
            instant = datetime.fromisoformat(str(event['occurred_at']))
            if instant.tzinfo is None:
                return False
            instant = instant.astimezone(VN_TZ)
            if instant.date() == day:
                if before is not None and instant > before:
                    return False
                count += 1
        return int(saved['last_observed_count']) == count and (not after or synced >= after)
    except (KeyError, ValueError, TypeError):
        return False


def issue_scope(issue, data):
    """Only adapter-proven identity AND shift days can narrow a blocker."""
    if (issue.get('reason') not in {'overlapping_shifts', 'unverified_status_type'}
            or issue.get('scope') != 'employee_days'
            or issue.get('username') not in {m['username'] for m in data['index'].values()}):
        return None
    try:
        days = issue['work_dates']
        if not isinstance(days, list) or not 1 <= len(days) <= 3:
            return None
        return issue['username'], {date.fromisoformat(d) for d in days}
    except (KeyError, TypeError, ValueError):
        return None


def blocking_issues(data, day=None, username=None):
    output = []
    for issue in data.get('issues', []):
        if issue.get('reason') == 'no_vera_shift':
            continue
        scope = issue_scope(issue, data)
        if scope is not None:
            owner, days = scope
            if (day is not None and day not in days) or (username is not None and username != owner):
                continue
        output.append(issue)
    return output


def archive_fresh(data, day, now):
    synced = archive_sync(data, day)
    return bool(synced and 0 <= (now - synced).total_seconds() <= 300)


def _verified_capture(data, day, checks, *, after=None):
    if day not in checks:
        synced = archive_sync(data, day)
        checks[day] = (archive_complete(data, day, before=synced), synced)
    complete, synced = checks[day]
    return bool(complete and synced and (after is None or synced >= after))


def future_evidence(data, now):
    """Projection may include tomorrow for overnight shifts, never future scans."""
    for event in data.get('events', []):
        try:
            instant = datetime.fromisoformat(str(event['occurred_at']))
            if instant.tzinfo is None or instant.astimezone(VN_TZ) > now:
                return True
        except (KeyError, TypeError, ValueError):
            return True
    return False


def fine_evidence_reasons(data, username, day, *, now, interval=None, capture_checks=None):
    reasons = []
    checks = capture_checks if capture_checks is not None else {}
    if 'future_evidence' not in checks:
        checks['future_evidence'] = future_evidence(data, now)
    if checks['future_evidence']:
        reasons.append('future_evidence')
    if username not in {m['username'] for m in data['index'].values()}:
        reasons.append('unmapped_employee')
    if blocking_issues(data, day, username):
        reasons.append('unresolved_evidence')
    # An overnight shift needs both calendar captures once midnight has passed.
    # An already closed capture must reach its closing evidence window.
    end = min(now, (interval[1] + timedelta(hours=2)).replace(tzinfo=VN_TZ)) if interval else now
    required = ({day + timedelta(days=offset) for offset in range(max(0, (end.date()-day).days) + 1)}
                if interval else {day, end.date()})
    for capture_day in required:
        synced = archive_sync(data, capture_day)
        if synced is not None and synced > now:
            reasons.append('stale_archive')
        after = end if capture_day == end.date() else datetime.combine(capture_day + timedelta(days=1), datetime.min.time(), tzinfo=VN_TZ)
        if not _verified_capture(data, capture_day, checks):
            reasons.append('incomplete_archive')
        elif (capture_day < end.date() or end < now) and not _verified_capture(data, capture_day, checks, after=after):
            reasons.append('incomplete_archive')
    if not archive_fresh(data, end.date(), now):
        reasons.append('stale_archive')
    return sorted(set(reasons))


def evidence_diagnostics(data, start, end, *, now=None):
    """Bounded aggregate diagnostics: no names, references or raw event data."""
    now = now or datetime.now(VN_TZ)
    if future_evidence(data, now):
        data = {**data, 'issues': [*data.get('issues', []), {'reason': 'future_or_invalid_event_timestamp'}]}
    blocking = blocking_issues(data)
    global_issues = [i for i in blocking if issue_scope(i, data) is None]
    def counts(issues):
        return dict(sorted(Counter(str(i.get('reason') or 'unknown_issue') for i in issues).items()))
    days = []
    day = start
    while day <= end:
        relevant = blocking_issues(data, day)
        synced = archive_sync(data, day)
        days.append({'date': day.isoformat(), 'issue_count': len(relevant),
                     'global_issue_count': len(global_issues),
                     'scoped_issue_count': len(relevant) - len(global_issues),
                     'reason_counts': counts(relevant),
                     'archive_complete': archive_complete(data, day, before=synced),
                     'archive_fresh': archive_fresh(data, day, now),
                     'last_sync_at': synced.isoformat() if synced else None,
                     'age_seconds': (now - synced).total_seconds() if synced else None})
        day += timedelta(days=1)
    return {'issue_count': len(data.get('issues', [])), 'global_issue_count': len(global_issues),
            'scoped_issue_count': len(blocking) - len(global_issues),
            'informational_issue_count': len(data.get('issues', [])) - len(blocking),
            'reason_counts': counts(data.get('issues', [])), 'days': days}


def annotate(records, data, *, now=None):
    now = now or datetime.now(VN_TZ)
    mapped = {m['username'] for m in data['index'].values()}
    identity_reviews = defaultdict(set)
    for scan in data.get('rows', []):
        if scan.get('_vera_identity_review_id'):
            identity_reviews[(scan.get('EmployeeName'), scan.get('WorkDateStr'))].add(scan['_vera_identity_review_id'])
    participating = []
    # Validate each calendar capture once per projection, not once per employee.
    capture_checks = {}
    for row in records:
        day = datetime.strptime(row['date'], '%d/%m/%Y').date()
        if participation.suspended(row['employee_name'], day):
            continue
        participating.append(row)
        reasons = []
        username = row['employee_name']
        if username not in mapped:
            reasons.append('unmapped_employee')
        blocking = blocking_issues(data, day, username)
        if blocking:
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
                if not _verified_capture(data, day, capture_checks):
                    reasons.append('incomplete_archive')
                if not _verified_capture(data, close_at.date(), capture_checks, after=close_at):
                    reasons.append('incomplete_archive')
        row.update(attendance_source='FaceGate · Lịch VERA', evidence_source='facegate',
                   attendance_preview=False, attendance_pending=bool(reasons),
                   attendance_pending_reasons=sorted(set(reasons)),
                   payable_minutes_verified=bool(row.get('check_in') and row.get('check_out') and not reasons),
                   identity_verified=username in mapped,
                   attendance_evidence_issues=bool(blocking))
        fine_reasons = fine_evidence_reasons(data, username, day, now=now, interval=interval, capture_checks=capture_checks)
        if not interval:
            fine_reasons = sorted(set(fine_reasons + ['missing_vera_shift']))
        capture_day = min(now, (interval[1] + timedelta(hours=2)).replace(tzinfo=VN_TZ)).date() if interval else now.date()
        fine_synced = archive_sync(data, capture_day)
        row.update(attendance_fine_evidence_ready=not fine_reasons,
                   attendance_fine_evidence_reasons=fine_reasons,
                   attendance_fine_evidence_synced_at=fine_synced.isoformat() if fine_synced else None)
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
    if future_evidence(data, now):
        raise fg.EvidenceError('future_or_invalid_event_timestamp')
    reports = []
    day = start
    while day <= end:
        saved = next((s for s in data['syncs'] if str(s['work_date']) == day.isoformat()), None)
        if not archive_complete(data, day, before=archive_sync(data, day)) or not saved:
            raise fg.EvidenceError('incomplete_archive')
        synced = datetime.fromisoformat(str(saved['last_synced_at'])).astimezone(VN_TZ)
        if not 0 <= (now - synced).total_seconds() <= 300:
            raise fg.EvidenceError('stale_archive')
        rows = [r for r in data['rows'] if r['WorkDateStr'] == day.strftime('%d/%m/%Y')]
        key = 'facegate_employee_checkin_' + day.strftime('%Y%m%d')
        vpg._write_dataset_conn(conn, key, pd.DataFrame(rows), 300, day.isoformat())
        if day == now.date():
            vpg._write_dataset_conn(conn, 'facegate_employee_checkin_today', pd.DataFrame(rows), 300, day.isoformat())
        diagnostic = evidence_diagnostics(data, day, day, now=now)['days'][0]
        reports.append({**diagnostic, 'mapped_scan_count': len(rows),
                        'range_issue_count': len(data['issues']),
                        'mapped_employee_count': len(data['index'])})
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
            if (not row.get('check_in') or not row.get('identity_verified')
                    or row.get('attendance_fine_evidence_ready') is not True):
                continue
            frame.append({'WorkDateStr': day.strftime('%d/%m/%Y'),
                          'employeeInfo.Name': row['employee_name'],
                          'employeeInfo.EmployeeCode': row.get('employee_code', ''),
                          'MachineTimeCheckInStr': datetime.fromisoformat(row['check_in_at']).strftime('%d/%m/%Y %H:%M:%S'),
                          '_vera_evidence_source': 'facegate',
                          '_vera_checkin_at': row['check_in_at'],
                          'StartWorkTime': row.get('shift_start', ''),
                          'TotalMinuteInGoLate': row.get('late_minutes', 0)})
        output.append((day, pd.DataFrame(frame)))
    return output


def _alert_eligible_users(data, day):
    return {m['username'] for m in data['index'].values()
            if not participation.suspended(m['username'], day)
            and not blocking_issues(data, day, m['username'])}


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

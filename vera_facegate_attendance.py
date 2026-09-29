"""FaceGate evidence -> the existing VERA attendance calculator (shadow mode).

No device I/O, database writes, name-based identity guesses or TimeSoft-cache
replacement here. The caller owns the one connection. A successful comparison
is evidence to review, never permission to switch the production source.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
import json

from sqlalchemy import text

from vera_facegate_control_log import VN_TZ, mapping_device_id
from vera_facegate_readiness import reference
from vera_facegate_address_history import accepts_event

MAX_EVENTS = 20000
# Observed in the operator's two matching exports. This is a preview filter,
# NOT a claim that the vendor's success/direction semantics were verified.
PREVIEW_STATUS_TYPES = {('1', '0')}
COMPARE_FIELDS = ('check_in', 'check_out', 'punch_times', 'break_out', 'break_in',
                  'break_actual_minutes', 'shift', 'shift_start', 'shift_end')


class EvidenceError(ValueError):
    pass


def decoded(value, fallback):
    try:
        return json.loads(value) if isinstance(value, str) else value or fallback
    except (ValueError, TypeError):
        raise EvidenceError('invalid_saved_evidence') from None


def shift_interval(day, start, end):
    if not start or not end:
        return None
    try:
        left = datetime.combine(day, time.fromisoformat(str(start)))
        right = datetime.combine(day, time.fromisoformat(str(end)))
    except (TypeError, ValueError):
        return None
    if right <= left:
        right += timedelta(days=1)
    return left, right


def business_day(instant, intervals, *, allow_checkout=False):
    """Assign a scan to the scheduled work day, including overnight checkout.

    Normal FaceGate evidence keeps the existing four-hour early / two-hour late
    window.  Departments that actually punch out (reception, locker, cleaning)
    get a narrow overnight-checkout fallback to yesterday's shift; this never
    applies to leader/nhanvien and never creates a calendar-day fallback.
    """
    if allow_checkout:
        previous = instant.date() - timedelta(days=1)
        interval = intervals.get(previous)
        # For checkout-enabled departments, a post-midnight scan first belongs
        # to yesterday when yesterday had a real overnight scheduled shift.
        if (interval and interval[1].date() > previous
                and instant.date() != previous
                and interval[0] <= instant <= interval[1] + timedelta(hours=2)):
            return previous, ''
    candidates = []
    for day, interval in intervals.items():
        if interval and interval[0] - timedelta(hours=4) <= instant <= interval[1] + timedelta(hours=2):
            candidates.append(day)
    if len(candidates) == 1:
        return candidates[0], ''
    return None, 'overlapping_shifts' if candidates else 'no_vera_shift'


def confirmed_index(mappings, employees, address):
    from vera_web_v2_attendance_v42 import _norm
    staff = {row['username']: row for row in employees}
    owners = defaultdict(set)
    for row in employees:
        for name in (row['username'], row.get('full_name')):
            if _norm(name): owners[_norm(name)].add(row['username'])
    valid = [m for m in mappings if isinstance(m, dict) and m.get('confirmed_by')
             and m.get('username') in staff and m.get('device_address', '') == address
             and len(owners[_norm(m['username'])]) == 1
             and reference(m.get('registration_ref'))]
    refs = Counter(reference(m['registration_ref']) for m in valid)
    users = Counter(m['username'] for m in valid)
    return {reference(m['registration_ref']): m for m in valid
            if refs[reference(m['registration_ref'])] == 1 and users[m['username']] == 1}


def adapt_events(events, mappings, employees, address, start, end, resolve_shift):
    """Preserve actual dates/seconds and all distinct scans; cluster in VERA.

    Historical FaceGate rows can retain a pre-photo-change registration_ref.
    A stale ref may fall back to device_name only when that normalized name
    identifies exactly one already-confirmed mapping on the current device.
    The archived payload itself remains immutable.
    """
    index = confirmed_index(mappings, employees, address)
    profiles = {p['username']: p for p in employees}
    from vera_web_v2_attendance_v42 import _norm
    confirmed_name_owners = defaultdict(set)
    confirmed_mapping_by_user = {}
    for mapping in index.values():
        username = mapping['username']
        confirmed_mapping_by_user[username] = mapping
        profile = profiles.get(username, {})
        for value in (username, profile.get('full_name'), mapping.get('device_name')):
            token = _norm(value)
            if token:
                confirmed_name_owners[token].add(username)
    windows = {}
    for username, profile in profiles.items():
        windows[username] = {}
        day = start - timedelta(days=1)
        while day <= end + timedelta(days=1):
            _, left, right = resolve_shift(profile, day)
            windows[username][day] = shift_interval(day, left, right)
            day += timedelta(days=1)
    output, issues, seen = [], [], {}
    for event in events:
        payload = decoded(event.get('payload_json'), {})
        event_id = str(event.get('event_id', ''))
        try:
            instant = datetime.fromisoformat(str(event['occurred_at']))
            if instant.utcoffset() is None:
                raise ValueError()
            instant = instant.astimezone(VN_TZ).replace(tzinfo=None)
        except (KeyError, ValueError, TypeError):
            issues.append({'event_id': event_id, 'reason': 'invalid_timestamp'})
            continue
        if not start <= instant.date() <= end + timedelta(days=1):
            continue
        key = (event_id, instant)
        digest = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if key in seen:
            if seen[key] != digest:
                issues.append({'event_id': event_id, 'reason': 'conflicting_duplicate'})
            continue
        seen[key] = digest
        ref = reference(payload.get('registration_ref'))
        mapping = index.get(ref)
        resolution = 'registration_ref'
        reason = ''
        if not accepts_event(mapping, payload, address, event['occurred_at']):
            reason = 'device_address_changed'
        elif not ref:
            # Only a valid but stale reference may use the confirmed-name fallback.
            # Missing/malformed evidence must never be assigned by name alone.
            reason = 'unmapped_reference'
        elif not mapping:
            token = _norm(payload.get('device_name'))
            owners = confirmed_name_owners.get(token, set()) if token else set()
            if len(owners) == 1:
                username = next(iter(owners))
                mapping = confirmed_mapping_by_user.get(username)
                resolution = 'confirmed_unique_device_name'
            else:
                reason = 'unmapped_reference'
        if not reason and (str(payload.get('status_code')), str(payload.get('type_code'))) not in PREVIEW_STATUS_TYPES:
            reason = 'unverified_status_type'
        if reason:
            issues.append({'event_id': event_id, 'reason': reason,
                           'registration_ref': payload.get('registration_ref'),
                           'device_name': str(payload.get('device_name') or '')[:160]})
            continue
        username = mapping['username']
        role = str(profiles[username].get('role') or '').strip().lower()
        day, reason = business_day(instant, windows[username],
                                   allow_checkout=role in {'letan', 'locker', 'tapvu'})
        if reason:
            issues.append({'event_id': event_id, 'reason': reason, 'username': username})
            continue
        if not start <= day <= end:
            continue
        name, left, right = resolve_shift(profiles[username], day)
        output.append({'WorkDateStr': day.strftime('%d/%m/%Y'),
                       'employeeInfo.Name': username, 'EmployeeName': username,
                       'employeeInfo.EmployeeCode': str(mapping.get('employee_code') or ''),
                       'MachineTimeCheckInStr': instant.strftime('%d/%m/%Y %H:%M:%S'),
                       'WorkTimeName': name, 'StartWorkTime': left, 'EndWorkTime': right,
                       '_vera_evidence_source': 'facegate', '_vera_event_id': event_id,
                       '_vera_identity_resolution': resolution,
                       '_vera_checkin_at': instant.replace(tzinfo=VN_TZ).isoformat()})
    output.sort(key=lambda row: (row['WorkDateStr'], row['EmployeeName'], row['_vera_checkin_at']))
    return output, issues, index


def read_evidence(conn, start, end):
    """Bounded range includes next calendar day for overnight VERA shifts."""
    from vera_web_v2_devices import facegate_address
    device_id = mapping_device_id()
    address = facegate_address(conn, require_registered=True)
    mappings = decoded(conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='facegate' AND setting_key=:key"),
                                   {'key': 'mapping_' + device_id}).scalar(), [])
    if not isinstance(mappings, list):
        raise EvidenceError('invalid_mapping_data')
    # Schema is created by archive ingestion, never during a preview request.
    available = conn.execute(text("SELECT to_regclass('vera_facegate_event') IS NOT NULL AND to_regclass('vera_facegate_sync_day') IS NOT NULL")).scalar()
    if not available:
        return address, mappings, [], []
    params = {'device': device_id, 'start': start.isoformat(), 'end': (end + timedelta(days=1)).isoformat()}
    events = conn.execute(text('''SELECT event_id,occurred_at,payload_json FROM vera_facegate_event
        WHERE device_id=:device AND work_date BETWEEN :start AND :end
        ORDER BY occurred_at,event_id LIMIT 20001'''), params).mappings().all()
    if len(events) > MAX_EVENTS:
        raise EvidenceError('too_many_events')
    syncs = conn.execute(text('''SELECT work_date,last_observed_count,last_synced_at FROM vera_facegate_sync_day
        WHERE device_id=:device AND work_date BETWEEN :start AND :end'''), params).mappings().all()
    return address, mappings, events, syncs


def raw_punches(datasets, aliases, start, end):
    """Unique employee/timestamp evidence, ignoring synthetic checkout totals."""
    import vera_web_v2_attendance_v42 as v42
    result = defaultdict(set)
    for dataset in datasets:
        for raw in dataset.get('payload') or []:
            if not isinstance(raw, dict):
                continue
            username = v42._canonical_employee(raw, aliases)
            if not username:
                continue
            day = v42._explicit_work_day(raw)
            # Canonical policy normally installs this check-in-only parser.
            values = [v for k, v in raw.items() if k.startswith(('MachineTimeCheckIn', 'LocalTimeCheckIn')) and k.endswith('Str')]
            punches = [p for value in values if (p := v42._parse_datetime(value, day))]
            if not punches:
                punches = v42._generic_raw_punch(raw, day)
            for punch in punches:
                if start <= punch.date() <= end:
                    result[username].add(punch.isoformat())
    return result


def mapping_candidates(events, datasets, employees, address, start, end):
    """Only exact timestamp sets yield suggestions; never confirm identities."""
    import vera_web_v2_attendance_v42 as v42
    owners = defaultdict(set)
    for employee in employees:
        for alias in (employee['username'], employee.get('full_name')):
            if v42._norm(alias):
                owners[v42._norm(alias)].add(employee['username'])
    aliases = {key: next(iter(values)) for key, values in owners.items() if len(values) == 1}
    reference_punches = raw_punches(datasets, aliases, start, end)
    grouped, names = defaultdict(set), defaultdict(set)
    refs = {}
    for event in events:
        payload = decoded(event.get('payload_json'), {})
        ref = reference(payload.get('registration_ref'))
        if not ref or payload.get('device_address', '') != address:
            continue
        try:
            dt = datetime.fromisoformat(event['occurred_at'])
            if dt.utcoffset() is None:
                continue
            dt = dt.astimezone(VN_TZ).replace(tzinfo=None)
        except (KeyError, ValueError, TypeError):
            continue
        if start <= dt.date() <= end:
            grouped[ref].add(dt.isoformat())
            names[ref].add(str(payload.get('device_name') or ''))
            refs[ref] = payload['registration_ref']
    output = []
    for ref, punches in grouped.items():
        matches = [username for username, other in reference_punches.items() if punches == other]
        candidate = matches[0] if len(matches) == 1 else ''
        output.append({'registration_ref': refs[ref], 'device_names': sorted(names[ref]),
                       'username_candidate': candidate, 'event_count': len(punches),
                       'status': 'candidate' if candidate else 'ambiguous' if matches else 'unmatched',
                       'confirmed': False})
    # Two device profiles with the same sequence cannot both claim one employee.
    counts = Counter(row['username_candidate'] for row in output if row['username_candidate'])
    for row in output:
        if counts[row['username_candidate']] > 1:
            row.update(username_candidate='', status='ambiguous')
    return output


def compare_records(left, right):
    import vera_web_v2_attendance_v42 as v42
    def keyed(records):
        return {(r['date'], r['employee_name']): r for r in records}
    def comparable(field, value, work_day):
        if field == 'punch_times' and isinstance(value, list):
            return [comparable('check_in', item, work_day) for item in value]
        if field in {'check_in', 'check_out', 'break_out', 'break_in', 'shift_start', 'shift_end'}:
            parsed = v42._parse_datetime(value, v42._parse_date(work_day))
            return parsed.strftime('%H:%M:%S') if parsed else str(value or '').strip()
        return value
    a, b = keyed(left), keyed(right)
    differences = []
    for key in sorted(a.keys() | b.keys()):
        fields = [field for field in COMPARE_FIELDS
                  if comparable(field, a.get(key, {}).get(field), key[0]) != comparable(field, b.get(key, {}).get(field), key[0])]
        if fields:
            differences.append({'date': key[0], 'employee_name': key[1], 'fields': fields,
                                'timesoft': {f: a.get(key, {}).get(f) for f in fields},
                                'facegate': {f: b.get(key, {}).get(f) for f in fields}})
    return differences


def compare_punches(timesoft, facegate, employees, start, end):
    import vera_web_v2_attendance_v42 as v42
    owners = defaultdict(set)
    for employee in employees:
        for value in (employee['username'], employee.get('full_name')):
            if v42._norm(value): owners[v42._norm(value)].add(employee['username'])
    aliases = {key: next(iter(values)) for key, values in owners.items() if len(values) == 1}
    def selected(datasets):
        return [{'payload': [raw for raw in d.get('payload', []) if isinstance(raw, dict)
                 and start <= (v42._explicit_work_day(raw) or date.min) <= end]} for d in datasets]
    a = raw_punches(selected(timesoft), aliases, start, end + timedelta(days=1))
    b = raw_punches(selected(facegate), aliases, start, end + timedelta(days=1))
    return [{'employee_name': username, 'missing_in_facegate': sorted(a[username] - b[username]),
             'extra_in_facegate': sorted(b[username] - a[username])}
            for username in sorted(a.keys() | b.keys()) if a[username] != b[username]]


def preview(conn, start, end, *, checkout_reviews_override=None):
    import vera_web_v2_attendance_query_perf as attendance
    import vera_web_v2_attendance_v42 as v42
    if end < start or (end - start).days > 6:
        raise EvidenceError('range_must_be_1_to_7_days')
    import vera_facegate_checkout_review as checkout_review
    review_device_id = mapping_device_id()
    saved_reviews = (checkout_review.read_reviews(conn, review_device_id)
                     if checkout_reviews_override is None else checkout_reviews_override)
    reviews = checkout_review.relevant_reviews(saved_reviews, start, end)
    evidence_start = min([start] + [date.fromisoformat(r['work_date']) for r in reviews])
    address, mappings, events, syncs = read_evidence(conn, evidence_start, end)
    employees = attendance._active_roster(conn)
    definitions, _ = attendance.snapshot._shift_break_settings(conn)
    schedules = attendance._schedule_map(conn, start - timedelta(days=1), end + timedelta(days=1))
    def resolve(profile, day):
        schedule = schedules.get((day, v42._norm(profile['username'])))
        if schedule is None:
            schedule = schedules.get((day, v42._norm(profile.get('full_name'))))
        return attendance._vera_shift_fields(profile, day, definitions, schedule)
    rows, issues, index = adapt_events(events, mappings, employees, address, start, end, resolve)
    rows, issues, applied_reviews = checkout_review.overlay_rows(
        rows, issues, reviews, events, index, employees, address,
        review_device_id, start, end, resolve)
    raw_rows = list(rows)
    from vera_facegate_test_scans import exclude_reviewed_test_scans
    rows, test_scan_issues, test_scan_reviews = exclude_reviewed_test_scans(
        rows, events, index, address)
    issues.extend(test_scan_issues)
    datasets = attendance._datasets(conn, start, end + timedelta(days=1))
    facegate = attendance._records_v42_fast(conn, start, end, datasets=[{'payload': rows}])
    # Only departments whose operating policy requires a final face punch may
    # expose the last clustered scan as checkout.  Leaders and therapists keep
    # checkout blank; their later scans are mid-shift break evidence only.
    checkout_roles = {'letan', 'locker', 'tapvu'}
    for row in facegate:
        role = str(row.get('employee_role') or '').strip().lower()
        if role in checkout_roles:
            punches = row.get('punch_datetimes') or []
            if len(punches) >= 2:
                try:
                    last = datetime.fromisoformat(str(punches[-1]))
                    work_day = datetime.strptime(row['date'], '%d/%m/%Y').date()
                    shift = shift_interval(work_day, row.get('shift_start'), row.get('shift_end'))
                except (ValueError, TypeError, KeyError):
                    shift = None
                    last = None
                if shift and last and last >= shift[0] and last <= shift[1] + timedelta(hours=2):
                    row['check_out'] = last.strftime('%H:%M:%S')
                    row['faceid_check_out'] = row['check_out']
                    row['check_out_at'] = last.replace(tzinfo=VN_TZ).isoformat()
                    row['departure_status'] = 'Đã chấm ra'
        else:
            row['check_out'] = ''
            row['faceid_check_out'] = ''
            row.pop('check_out_at', None)
        if row.get('attendance_roster_only'):
            row['attendance_note'] = str(row.get('attendance_note') or '').replace('TimeSoft', 'FaceGate đã ánh xạ')
    facegate = checkout_review.overlay_records(facegate, applied_reviews)
    timesoft = attendance._records_v42_fast(conn, start, end, datasets=datasets)
    differences = compare_records(timesoft, facegate)
    evidence_differences = compare_punches(datasets, [{'payload': raw_rows}], employees, start, end)
    candidates = mapping_candidates(events, datasets, employees, address, start, end)
    mapped_users = {m['username'] for m in index.values()}
    required = {r['employee_name'] for r in facegate if r.get('attendance_expected') and r.get('employee_role') != 'admin'}
    missing = sorted(required - mapped_users)
    # The counts must cover every requested calendar day and any following
    # overnight period. Historical snapshots taken mid-day aren't complete.
    archived = {str(s['work_date']): s for s in syncs}
    counts = Counter(str(e['occurred_at'])[:10] for e in events)
    incomplete = []
    day = start
    final_day = end + timedelta(days=1) if any(r.get('overnight_shift') for r in facegate) else end
    while day <= final_day:
        saved = archived.get(day.isoformat())
        try:
            synced = datetime.fromisoformat(saved['last_synced_at']).astimezone(VN_TZ) if saved else None
        except (ValueError, TypeError):
            synced = None
        if not saved or int(saved['last_observed_count']) != counts[day.isoformat()] or not synced or synced.date() <= day:
            incomplete.append(day.isoformat())
        day += timedelta(days=1)
    # Keep every issue in the audit output, but an otherwise valid scan made
    # outside any scheduled shift is informational for departments that punch
    # both in/out. It must not by itself block cutover. Identity, duplicate,
    # address and status problems remain blocking.
    nonblocking_issue_reasons = {'no_vera_shift'}
    blocking_issues = [issue for issue in issues
                       if issue.get('reason') not in nonblocking_issue_reasons]
    blockers = []
    if not rows: blockers.append('no_mapped_evidence')
    if missing: blockers.append('unmapped_employees')
    if blocking_issues: blockers.append('unresolved_events')
    if differences: blockers.append('attendance_differences')
    if evidence_differences: blockers.append('raw_evidence_differences')
    if incomplete: blockers.append('incomplete_archive_days')
    if not raw_punches(datasets, {v42._norm(p['username']): p['username'] for p in employees}, start, end):
        blockers.append('no_timesoft_reference')
    # These remain explicit because raw status 1/0 is not documented as IN/OUT
    # and a sample match does not validate payroll/leave/penalty cutover.
    blockers += ['device_status_semantics_unverified', 'production_cutover_review_required']
    return {'mode': 'shadow', 'source': 'timesoft', 'attendance_calculation_enabled': False,
            'attendance_cutover_ready': False, 'start': start.isoformat(), 'end': end.isoformat(),
            'facegate_event_count': len(rows), 'employee_count': len(mapped_users),
            'records': facegate, 'differences': differences, 'issues': issues[:200],
            'issue_count': len(issues), 'blocking_issue_count': len(blocking_issues),
            'informational_issue_count': len(issues) - len(blocking_issues),
            'issues_truncated': len(issues) > 200,
            'evidence_differences': evidence_differences,
            'applied_checkout_review_ids': [r['id'] for r in applied_reviews],
            'applied_test_scan_reviews': test_scan_reviews,
            'unmapped_employees': missing, 'mapping_candidates': candidates,
            'incomplete_days': incomplete, 'blockers': blockers,
            'last_sync_at': max((str(s['last_synced_at']) for s in syncs), default=''),
            'payroll_and_penalties_written': False}

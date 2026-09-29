"""Event-bound, operator-reviewed extended checkout; shadow projection only.

Reviews live in PostgreSQL, separately from schedules, mappings and raw events.
No device calls or writes occur on the preview path. A deployment creates no
review: the local administrator must explicitly run the bounded --apply case.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from vera_facegate_address_history import accepts_address, accepts_event

VN = timezone(timedelta(hours=7))
MAX_REVIEWS = 100
CHECKOUT_ROLES = {'letan', 'locker', 'tapvu'}
CASE = {
    'id': 'yen-linh-2026-09-27', 'username': 'Yến Linh', 'role': 'letan',
    'work_date': '2026-09-27', 'device_address': '192.168.1.26',
    'check_in_event_id': '79011', 'check_out_event_id': '79107',
    'events': [
        {'event_id': '79010', 'occurred_at': '2026-09-27T10:08:04+07:00'},
        {'event_id': '79011', 'occurred_at': '2026-09-27T10:08:07+07:00'},
        {'event_id': '79012', 'occurred_at': '2026-09-27T10:08:09+07:00'},
        {'event_id': '79106', 'occurred_at': '2026-09-28T00:33:56+07:00'},
        {'event_id': '79107', 'occurred_at': '2026-09-28T00:33:58+07:00'},
    ],
    'reason': 'Operator confirmed morning arrival and extended shift checkout on the following calendar day.',
    'operator_confirmation_at': '2026-09-28T15:48:42+00:00',
}


class ReviewError(ValueError):
    """Only controlled error codes; never database parameters or credentials."""


def require(condition, reason):
    if not condition:
        raise ReviewError(reason)


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    require(result.utcoffset() is not None, 'review_timestamp_requires_timezone')
    return result.astimezone(VN)


def payload(event):
    raw = event.get('payload_json')
    raw = json.loads(raw) if isinstance(raw, str) else raw
    require(isinstance(raw, dict), 'review_invalid_event_payload')
    return raw


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def ref(value):
    if not isinstance(value, dict):
        return None
    try:
        parts = tuple(int(value[k]) for k in ('file_type', 'file_index', 'file_position'))
        return parts if parts[0] == 0 and parts[1] >= 0 and parts[2] > 0 else None
    except (ValueError, TypeError, KeyError):
        return None


def setting_key(device_id):
    return 'checkout_reviews_' + device_id


def read_reviews(conn, device_id):
    from sqlalchemy import text
    raw = conn.execute(text("""SELECT value_json FROM vera_app_setting
        WHERE category='facegate' AND setting_key=:key"""),
        {'key': setting_key(device_id)}).scalar()
    if raw is None:
        return []
    raw = json.loads(raw) if isinstance(raw, str) else raw
    require(isinstance(raw, dict) and raw.get('version') == 1
            and raw.get('device_id') == device_id, 'review_invalid_document')
    reviews = raw.get('reviews')
    require(isinstance(reviews, list) and len(reviews) <= MAX_REVIEWS
            and all(isinstance(r, dict) for r in reviews), 'review_invalid_list')
    return reviews


def relevant_reviews(reviews, start, end):
    return [r for r in reviews
            if start - timedelta(days=1) <= date.fromisoformat(r['work_date']) <= end]


def validate_review(review, events, index, employees, address, device_id):
    """Require all exact original events and their current confirmed owner."""
    require(review.get('version') == 1 and review.get('confirmed_by')
            and review.get('reason') and review.get('id'), 'review_unconfirmed')
    stamp(review['confirmed_at'])
    mapping = index.get(ref(review.get('registration_ref')))
    require(review.get('device_id') == device_id
            and accepts_address(mapping, review.get('device_address'), address,
                                str(review.get('work_date')) + 'T00:00:00+07:00'),
            'review_device_changed')
    people = [p for p in employees if p.get('username') == review.get('username')]
    require(len(people) == 1 and people[0].get('role') == review.get('role')
            and review.get('role') in CHECKOUT_ROLES, 'review_employee_or_role_changed')
    mapping = index.get(ref(review.get('registration_ref')))
    require(isinstance(mapping, dict) and mapping.get('username') == review['username']
            and str(mapping.get('profile_id')) == str(review.get('profile_id')),
            'review_mapping_changed')
    expected = review.get('events')
    require(isinstance(expected, list) and 2 <= len(expected) <= 20,
            'review_invalid_event_count')
    expected_ids = {e['event_id'] for e in expected}
    require(len(expected_ids) == len(expected), 'review_duplicate_event_ids')
    by_id = defaultdict(list)
    for event in events:
        if str(event.get('event_id')) in expected_ids:
            by_id[str(event['event_id'])].append(event)
    found = []
    for expected_event in expected:
        matches = by_id[expected_event['event_id']]
        require(len(matches) == 1, 'review_missing_or_reused_event_id')
        event = matches[0]
        p = payload(event)
        require(stamp(event['occurred_at']) == stamp(expected_event['occurred_at'])
                and fingerprint(p) == expected_event.get('payload_sha256'),
                'review_evidence_changed')
        require(p.get('device_address') == review.get('device_address')
                and accepts_event(mapping, p, address, event['occurred_at'])
                and index.get(ref(p.get('registration_ref'))) == mapping,
                'review_event_owner_changed')
        require((str(p.get('status_code')), str(p.get('type_code'))) == ('1', '0'),
                'review_event_status_changed')
        found.append(event)
    found.sort(key=lambda e: stamp(e['occurred_at']))
    anchors = {str(e['event_id']): stamp(e['occurred_at']) for e in found}
    first = anchors.get(review.get('check_in_event_id'))
    last = anchors.get(review.get('check_out_event_id'))
    work_day = date.fromisoformat(review['work_date'])
    require(first is not None and last is not None and first.date() == work_day
            and last.date() <= work_day + timedelta(days=1)
            and timedelta(minutes=5) < last - first < timedelta(days=1),
            'review_invalid_anchor_pair')
    # Review covers two boundary clusters, not an arbitrary interval/shift rule.
    earliest, latest = stamp(found[0]['occurred_at']), stamp(found[-1]['occurred_at'])
    require(first - earliest <= timedelta(minutes=5)
            and latest - last <= timedelta(minutes=5), 'review_anchor_outside_cluster')
    for event in found:
        instant = stamp(event['occurred_at'])
        require(abs(instant - first) <= timedelta(minutes=5)
                or abs(instant - last) <= timedelta(minutes=5),
                'review_unreviewed_middle_cluster')
    for event in events:
        if str(event.get('event_id')) in expected_ids:
            continue
        instant = stamp(event['occurred_at'])
        if earliest <= instant <= latest:
            p = payload(event)
            other = index.get(ref(p.get('registration_ref')))
            if other and other.get('username') == review['username']:
                raise ReviewError('review_additional_employee_evidence')
    return found


def overlay_rows(rows, issues, reviews, events, index, employees, address,
                 device_id, start, end, resolve_shift):
    """Reassign only reviewed IDs; never mutate rows, issues or raw evidence."""
    output, remaining, accepted, rejected = list(rows), list(issues), [], []
    claims = Counter((r.get('username'), r.get('work_date')) for r in reviews)
    event_claims = Counter(e.get('event_id') for r in reviews for e in r.get('events', []))
    for review in reviews:
        try:
            require(claims[(review.get('username'), review.get('work_date'))] == 1
                    and all(event_claims[e['event_id']] == 1 for e in review['events']),
                    'review_overlapping_claims')
            found = validate_review(review, events, index, employees, address, device_id)
            ids = {str(e['event_id']) for e in found}
            require(not any(str(i.get('event_id')) in ids and i.get('reason') != 'no_vera_shift'
                            for i in remaining), 'review_blocking_event_issue')
            person = next(p for p in employees if p['username'] == review['username'])
            day = date.fromisoformat(review['work_date'])
            name, left, right = resolve_shift(person, day)
            require(bool(left and right), 'review_missing_vera_schedule')
            mapping = index[ref(review['registration_ref'])]
            replacement = []
            if start <= day <= end:
                for event in found:
                    instant = stamp(event['occurred_at'])
                    replacement.append({
                        'WorkDateStr': day.strftime('%d/%m/%Y'),
                        'employeeInfo.Name': review['username'], 'EmployeeName': review['username'],
                        'employeeInfo.EmployeeCode': str(mapping.get('employee_code') or ''),
                        'MachineTimeCheckInStr': instant.strftime('%d/%m/%Y %H:%M:%S'),
                        'WorkTimeName': name, 'StartWorkTime': left, 'EndWorkTime': right,
                        '_vera_evidence_source': 'facegate', '_vera_event_id': str(event['event_id']),
                        '_vera_checkin_at': instant.isoformat(),
                        '_vera_identity_resolution': 'registration_ref',
                        '_vera_checkout_review_id': review['id'],
                    })
            output = [r for r in output if str(r.get('_vera_event_id')) not in ids] + replacement
            remaining = [i for i in remaining if str(i.get('event_id')) not in ids]
            accepted.append(review)
        except (ReviewError, ValueError, KeyError, TypeError, StopIteration) as exc:
            reason = str(exc) if isinstance(exc, ReviewError) else 'review_invalid_data'
            rejected.append({'review_id': review.get('id'), 'username': review.get('username'),
                             'reason': 'reviewed_checkout_invalid', 'detail': reason})
    output.sort(key=lambda r: (r['WorkDateStr'], r['EmployeeName'], r['_vera_checkin_at']))
    return output, remaining + rejected, accepted


def overlay_records(records, reviews):
    result = deepcopy(records)
    for review in reviews:
        day = date.fromisoformat(review['work_date']).strftime('%d/%m/%Y')
        matches = [r for r in result if r.get('employee_name') == review['username'] and r.get('date') == day]
        if not matches:
            continue  # The reviewed day can be outside a one-day report.
        require(len(matches) == 1 and matches[0].get('employee_role') == review['role']
                and not matches[0].get('attendance_roster_only'), 'review_projection_mismatch')
        row = matches[0]
        times = {e['event_id']: stamp(e['occurred_at']) for e in review['events']}
        first, last = times[review['check_in_event_id']], times[review['check_out_event_id']]
        row.update({
            'check_in': first.strftime('%H:%M:%S'), 'faceid_check_in': first.strftime('%H:%M:%S'),
            'check_in_at': first.isoformat(), 'check_out': last.strftime('%H:%M:%S'),
            'faceid_check_out': last.strftime('%H:%M:%S'), 'check_out_at': last.isoformat(),
            'punch_times': [t.strftime('%H:%M:%S') for t in (first, last)],
            'punch_datetimes': [t.replace(tzinfo=None).isoformat() for t in (first, last)],
            'raw_faceid_count': 2, 'faceid_last': last.strftime('%H:%M:%S'),
            'scheduled_overnight_shift': bool(row.get('overnight_shift')),
            'overnight_shift': first.date() != last.date(),
            'observed_span_seconds': int((last - first).total_seconds()),
            'departure_status': 'Đã chấm ra (ngoại lệ đã xác nhận)',
            'checkout_review_id': review['id'], 'checkout_reviewed_by': review['confirmed_by'],
            'checkout_reviewed_at': review['confirmed_at'],
            'reviewed_raw_events': [
                {'event_id': e['event_id'], 'occurred_at': e['occurred_at']}
                for e in review['events']],
            'payable_minutes_verified': False, 'attendance_preview': True,
        })
        # Do not infer wages/overtime/deductions or rewrite the planned schedule.
        row['attendance_note'] = 'Ca kéo dài qua ngày đã được quản trị xác nhận; chưa xác nhận giờ tính lương.'
    return result


def prepare_case(events, index, employees, address, device_id, actor, now):
    review = deepcopy(CASE)
    owners = [m for m in index.values() if m.get('username') == review['username']]
    require(len(owners) == 1, 'case_mapping_not_unique')
    # Check the original evidence time, not the time of this read-only rerun.
    require(accepts_address(owners[0], review['device_address'], address,
                           review['events'][-1]['occurred_at']), 'case_device_address_changed')
    review.update(version=1, device_id=device_id, profile_id=owners[0]['profile_id'],
                  registration_ref=deepcopy(owners[0]['registration_ref']),
                  confirmed_by=actor, confirmed_at=now)
    for expected in review['events']:
        found = [e for e in events if str(e.get('event_id')) == expected['event_id']]
        require(len(found) == 1 and stamp(found[0]['occurred_at']) == stamp(expected['occurred_at']),
                'case_event_missing_or_changed')
        expected['payload_sha256'] = fingerprint(payload(found[0]))
    validate_review(review, events, index, employees, address, device_id)
    return review


def stage_review(existing, proposed):
    """Idempotent append; never overwrite another or a changed review."""
    same = [r for r in existing if r.get('id') == proposed['id']]
    if same:
        require(len(same) == 1, 'case_duplicate_review')
        ignored = {'confirmed_by', 'confirmed_at'}
        require({k: v for k, v in same[0].items() if k not in ignored}
                == {k: v for k, v in proposed.items() if k not in ignored},
                'case_existing_review_changed')
        return existing, False
    require(len(existing) < MAX_REVIEWS, 'review_limit_reached')
    require(not any(r.get('username') == proposed['username'] and r.get('work_date') == proposed['work_date']
                    for r in existing), 'case_workday_already_reviewed')
    return existing + [proposed], True


def run_case(args, state):
    import os
    import tempfile
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from vera_facegate_readiness import runtime_device_environment
    from vera_vps_data_check import _database_url, _running_api_environment
    from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
    import vera_facegate_attendance as fg
    import vera_web_v2_attendance_query_perf as attendance

    require(os.name == 'posix' and os.geteuid() == 0, 'run_on_vera_vps_as_local_admin')
    runtime_device_environment()
    env = ({k: os.environ.get(k, '') for k in RUNTIME_ENV_KEYS}
           if load_managed_runtime_environment() else _running_api_environment())
    sslmode = env.get('DB_SSLMODE', 'require')
    if sslmode not in {'require', 'verify-ca', 'verify-full'}:
        sslmode = 'require'
    engine = create_engine(_database_url(env), poolclass=NullPool, hide_parameters=True,
        connect_args={'connect_timeout': 5, 'sslmode': sslmode,
                      'options': '-c statement_timeout=8000 -c lock_timeout=2000'})
    start = date.fromisoformat(CASE['work_date'])
    end = start + timedelta(days=1)
    device_id = fg.mapping_device_id()
    key = setting_key(device_id)
    backup_path = None
    try:
        with engine.begin() as conn:
            conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ' + ('' if args.apply else ', READ ONLY')))
            if args.apply:
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {'key': 'vera:' + key})
                # Pin registry/mapping during verification; no network while held.
                for category, locked_key in [('devices', 'registry'), ('facegate', 'mapping_' + device_id)]:
                    present = conn.execute(text("""SELECT revision FROM vera_app_setting
                        WHERE category=:category AND setting_key=:key FOR SHARE"""),
                        {'category': category, 'key': locked_key}).first()
                    require(present is not None, 'case_missing_registry_or_mapping')
            address, mappings, events, _ = fg.read_evidence(conn, start, end)
            employees = attendance._active_roster(conn)
            index = fg.confirmed_index(mappings, employees, address)
            proposed = prepare_case(events, index, employees, address, device_id,
                                    'vps-admin:uid=' + str(os.geteuid()), datetime.now(timezone.utc).isoformat())
            before = read_reviews(conn, device_id)
            after, changed = stage_review(before, proposed)
            # Validate the same projection that the API will use before any write.
            check = fg.preview(conn, start, end, checkout_reviews_override=after)
            target = [r for r in check['records'] if r.get('employee_name') == CASE['username']
                      and r.get('date') == start.strftime('%d/%m/%Y')]
            require(len(target) == 1 and target[0].get('checkout_review_id') == CASE['id']
                    and target[0].get('check_in') == '10:08:07'
                    and target[0].get('check_out') == '00:33:58', 'case_projection_not_verified')
            if args.apply and changed:
                fd, backup_path = tempfile.mkstemp(prefix='vera-facegate-checkout-before-', suffix='.json', dir='/root')
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump({'setting_key': key, 'reviews_before': before}, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                directory_fd = os.open('/root', os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                document = json.dumps({'version': 1, 'device_id': device_id, 'reviews': after}, ensure_ascii=False)
                conn.execute(text("""INSERT INTO vera_app_setting
                    (category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
                    VALUES ('facegate',:key,CAST(:value AS jsonb),'vps_admin_review',:actor,1,NOW(),NOW())
                    ON CONFLICT(category,setting_key) DO UPDATE
                    SET value_json=EXCLUDED.value_json,updated_by=EXCLUDED.updated_by,
                        revision=vera_app_setting.revision+1,updated_at=NOW()"""),
                    {'key': key, 'value': document, 'actor': proposed['confirmed_by']})
                require(read_reviews(conn, device_id) == after, 'case_saved_review_mismatch')
        state['committed'] = bool(args.apply and changed)
        result = {'ok': True, 'mode': 'apply' if args.apply else 'preview',
                  'applied': state['committed'], 'already_applied': not changed,
                  'review_id': CASE['id'], 'verified_event_count': 5,
                  'backup_path': backup_path, 'archive_written': False,
                  'schedules_written': False, 'payroll_and_penalties_written': False}
        if args.apply:
            with engine.begin() as conn:
                conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
                check = fg.preview(conn, start, end)
            require(CASE['id'] in check.get('applied_checkout_review_ids', []), 'case_readback_failed')
            result['verification'] = 'database_readback_and_shadow'
        else:
            result['verification'] = 'proposed_shadow_only'
        fields = ('date', 'employee_name', 'check_in', 'check_out', 'check_in_at', 'check_out_at',
                  'shift_start', 'shift_end', 'punch_times', 'checkout_review_id',
                  'reviewed_raw_events', 'observed_span_seconds', 'payable_minutes_verified')
        result['yen_linh'] = [{k: r.get(k) for k in fields} for r in check['records']
                             if r.get('employee_name') == CASE['username']]
        result['yen_linh_issues'] = [i for i in check['issues'] if i.get('username') == CASE['username']]
        result['blockers'] = check['blockers']
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


def main():
    import argparse
    import signal
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=[CASE['id']])
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    state = {'committed': False}
    def deadline(*_):
        raise ReviewError('case_deadline')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(90)
    try:
        run_case(args, state)
    except Exception as exc:
        print(json.dumps({'ok': False, 'committed': state['committed'],
                          'reason': str(exc) if isinstance(exc, ReviewError) else type(exc).__name__}))
        raise SystemExit(1) from None
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    main()

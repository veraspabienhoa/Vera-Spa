"""Preview or restore existing FaceGate bindings after a verified IP move.

Never guesses identities, adds profiles, rewrites scans or triggers penalties.
Run on the verified VPS release. Default is read-only; applying requires the
preview digest, exact address, expected binding count and deployed commit.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json


class RepairError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def ref(value):
    if not isinstance(value, dict):
        raise RepairError('invalid_reference')
    try:
        result = tuple(int(value[key]) for key in ('file_type', 'file_index', 'file_position'))
    except (KeyError, TypeError, ValueError):
        raise RepairError('invalid_reference') from None
    if result[0] != 0 or not 0 <= result[1] <= 65535 or not 0 < result[2] <= 2**63 - 1:
        raise RepairError('invalid_reference')
    return result


def prepare(mappings, profiles, employees, address, actor, now):
    """All-or-nothing plan using existing owners and exact device evidence."""
    from ipaddress import IPv4Address, IPv4Network
    if IPv4Address(address) not in IPv4Network('192.168.1.0/24') or not actor:
        raise RepairError('invalid_target_or_actor')
    instant = datetime.fromisoformat(now)
    if instant.utcoffset() is None:
        raise RepairError('invalid_verification_time')
    if not isinstance(mappings, list) or not mappings or len(mappings) > 200:
        raise RepairError('invalid_mapping_snapshot')
    if any(not isinstance(row, dict) for row in mappings + profiles + employees):
        raise RepairError('invalid_snapshot_row')
    live = {}
    live_references = {}
    for row in profiles:
        uid = row.get('profile_id')
        if uid in live:
            raise RepairError('duplicate_live_profile')
        live[uid] = row
        try:
            live_key = ref(row.get('registration_ref'))
        except RepairError:
            continue
        live_references[live_key] = live_references.get(live_key, 0) + 1
    staff = {}
    for row in employees:
        username = row.get('username')
        if username in staff:
            raise RepairError('duplicate_employee')
        staff[username] = row
    owners, uids, references = set(), set(), set()
    output, changed = [], 0
    for old in mappings:
        username, uid = old.get('username'), old.get('profile_id')
        key = ref(old.get('registration_ref'))
        if username in owners or uid in uids or key in references:
            raise RepairError('duplicate_saved_binding')
        owners.add(username); uids.add(uid); references.add(key)
        person = staff.get(username)
        if not person or person.get('role') == 'admin' or person.get('deleted'):
            raise RepairError('employee_not_eligible')
        profile = live.get(uid)
        if (not old.get('confirmed_by') or not old.get('confirmed_at')
                or not old.get('device_address') or not profile
                or ref(profile.get('registration_ref')) != key
                or profile.get('device_name') != old.get('device_name')):
            raise RepairError('profile_evidence_changed')
        if live_references.get(key) != 1:
            raise RepairError('duplicate_live_reference')
        prior_time = datetime.fromisoformat(old['confirmed_at'])
        if prior_time.utcoffset() is None or prior_time > instant:
            raise RepairError('invalid_previous_confirmation')
        entry = deepcopy(old)
        if old['device_address'] != address:
            entry.update(device_address=address,
                         confirmed_by='vps-admin:ip-reconfirmation', confirmed_at=now)
            entry['ip_reconfirmation'] = {
                'previous_address': old['device_address'], 'current_address': address,
                'previous_confirmed_by': old['confirmed_by'],
                'previous_confirmed_at': old['confirmed_at'], 'verified_at': now,
                'verified_by': actor, 'method': 'exact_profile_reference_and_name',
                'previous_mapping': deepcopy(old),
            }
            changed += 1
        output.append(entry)
    return output, changed


def refresh_today(engine, day):
    """Rebuild today's selected source from the immutable archive, without rules."""
    from datetime import date
    from vera_attendance_source import VN_TZ, health, source_for
    from vera_facegate_sync import sync_day
    from vera_facegate_runtime import publish
    target = date.fromisoformat(day)
    if target != datetime.now(VN_TZ).date() or source_for(target) != 'facegate':
        raise RepairError('refresh_requires_today_and_active_facegate')
    archived = sync_day(engine, day, apply=True)
    with engine.begin() as conn:
        reports = publish(conn, target, target)
        if archived['fetched_count'] and not any(row['mapped_scan_count'] for row in reports):
            raise RepairError('refresh_has_no_mapped_scans')
    with engine.connect() as conn:
        state = health(conn)
    return {'archive': archived, 'published': reports, 'source_health': state}


def main():
    import argparse
    from sqlalchemy import text
    from vera_facegate_cutover import runtime_engine, verify_runtime
    from vera_facegate_control_log import fetch_registered_profiles, mapping_device_id
    from vera_web_v2_devices import facegate_address, use_registered_facegate
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address', required=True)
    parser.add_argument('--operator', required=True)
    parser.add_argument('--expected-count', required=True, type=int)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--preview-digest')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--refresh-date', help='After apply, rebuild this Vietnam day; must be today.')
    args = parser.parse_args()
    engine = None
    mappings_applied = False
    try:
        if args.refresh_date:
            from datetime import date
            from vera_attendance_source import VN_TZ, source_for
            day = date.fromisoformat(args.refresh_date)
            if not args.apply or day != datetime.now(VN_TZ).date() or source_for(day) != 'facegate':
                raise RepairError('refresh_requires_apply_today_and_active_facegate')
        verify_runtime(args.expected_commit)
        engine = runtime_engine(readonly=not args.apply)
        key = 'mapping_' + mapping_device_id()
        query = "SELECT value_json FROM vera_app_setting WHERE category='facegate' AND setting_key=:key"
        with engine.connect() as conn:
            address = facegate_address(conn, require_registered=True)
            saved = conn.execute(text(query), {'key': key}).scalar_one()
            saved = json.loads(saved) if isinstance(saved, str) else saved
            staff = [dict(row) for row in conn.execute(text("""SELECT username,role,
                COALESCE(payload->>'__deleted','false')='true' AS deleted FROM employees""")).mappings()]
        if address != args.address or len(saved) != args.expected_count:
            raise RepairError('unexpected_address_or_count')
        if not any(row['username'] == args.operator and row['role'] == 'admin'
                   and not row['deleted'] for row in staff):
            raise RepairError('operator_not_admin')
        # No held business connection or transaction during device I/O.
        with use_registered_facegate(engine) as observed:
            if observed != address:
                raise RepairError('address_changed')
            profiles = fetch_registered_profiles()
        preview_digest = digest({'mappings': saved,
                                 'profiles': sorted(profiles, key=lambda p:p['profile_id']),
                                 'employees': sorted(staff, key=lambda p:p['username']),
                                 'address': address, 'operator': args.operator})
        updated, count = prepare(saved, profiles, staff, address, args.operator,
                                 datetime.now(timezone.utc).isoformat())
        if args.apply:
            if args.preview_digest != preview_digest:
                raise RepairError('preview_changed_or_missing')
            with engine.begin() as conn:
                # Registry updates and mapping changes cannot race this write.
                conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='devices' AND setting_key='registry' FOR SHARE")).scalar_one()
                current = conn.execute(text(query + ' FOR UPDATE'), {'key': key}).scalar_one()
                current = json.loads(current) if isinstance(current, str) else current
                people = [dict(row) for row in conn.execute(text("""SELECT username,role,
                    COALESCE(payload->>'__deleted','false')='true' AS deleted FROM employees
                    ORDER BY username FOR SHARE""")).mappings()]
                if (facegate_address(conn) != address or digest(current) != digest(saved)
                        or digest(sorted(people, key=lambda p:p['username'])) != digest(sorted(staff, key=lambda p:p['username']))):
                    raise RepairError('snapshot_changed')
                if count:
                    conn.execute(text("""UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb),
                        updated_by=:actor,updated_at=NOW(),revision=revision+1
                        WHERE category='facegate' AND setting_key=:key"""),
                        {'key': key, 'value': json.dumps(updated, ensure_ascii=False), 'actor': args.operator})
                    check = conn.execute(text(query), {'key': key}).scalar_one()
                    check = json.loads(check) if isinstance(check, str) else check
                    if digest(check) != digest(updated):
                        raise RepairError('readback_failed')
            mappings_applied = True
        refresh = refresh_today(engine, args.refresh_date) if args.refresh_date else None
        print(json.dumps({'ok': True, 'applied': args.apply, 'mapping_count': len(saved),
                          'reconfirmed_count': count, 'preview_digest': preview_digest,
                          'existing_raw_scans_rewritten': False,
                          'attendance_published': refresh is not None, 'refresh': refresh,
                          'payroll_or_penalties_written': False}))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'mappings_applied': mappings_applied,
                          'reason': str(exc) if isinstance(exc, RepairError)
                          else type(exc).__name__}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())

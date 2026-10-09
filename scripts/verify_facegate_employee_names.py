"""Run on the deployed VPS via stdin; report counts only, no employee/device data."""
import json
import os
from sqlalchemy import text
from vera_facegate_cutover import runtime_engine, verify_runtime
from vera_facegate_enrollment import FaceGateEnrollmentClient
from vera_facegate_control_log import facegate_endpoint, mapping_device_id, registration_ref
from vera_web_v2_facegate_enrollment import mappings, target
from vera_employee_rename_sync import sync_device_names


def main():
    verify_runtime(os.environ['VERA_EXPECTED_RELEASE'])
    engine = runtime_engine()
    client = None
    try:
        with engine.begin() as conn:
            exists = bool(conn.execute(text("SELECT to_regclass('vera_facegate_rename_job')")).scalar())
            pending = conn.execute(text("SELECT count(*) FROM vera_facegate_rename_job WHERE status='pending'")).scalar() if exists else 0
        if pending:
            sync_device_names(engine)
        with engine.begin() as conn:
            address = target(conn)
            device_id = mapping_device_id()
            entries = mappings(conn, device_id)
            jobs = conn.execute(text('''SELECT DISTINCT ON (device_id,profile_id) * FROM vera_facegate_rename_job
                WHERE device_id=:device ORDER BY device_id,profile_id,id DESC'''), {'device': device_id}).mappings().all() if exists else []
        verified = 0
        mismatches = 0
        unresolved = 0
        with facegate_endpoint('http://' + address):
            client = FaceGateEnrollmentClient()
            client.login()
            profiles = client.profiles()
            for job in jobs:
                owners = [e for e in entries if e.get('profile_id') == job['profile_id']
                          and e.get('username') == job['employee_username']
                          and e.get('registration_ref') == job['registration_ref']]
                if len(owners) != 1:
                    unresolved += 1
                    continue
                actual = client.profile_details(int(job['profile_id']))
                if (actual.get('uname') == job['new_name']
                        and registration_ref(actual) == job['registration_ref']
                        and owners[0].get('device_name') == job['new_name']
                        and job['status'] == 'verified'):
                    verified += 1
                else:
                    mismatches += 1
        result = {'ok': not (mismatches or unresolved), 'device_read_verified': True,
                  'device_profile_count': len(profiles), 'rename_job_count': len(jobs),
                  'renamed_profiles_verified': verified, 'rename_mismatches': mismatches,
                  'mapping_conflicts': unresolved, 'end_to_end_rename_exercised': bool(verified)}
        print(json.dumps(result, sort_keys=True))
        return 0 if result['ok'] else 1
    finally:
        if client:
            client.close()
        engine.dispose()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__, 'device_read_verified': False}))
        raise SystemExit(1)

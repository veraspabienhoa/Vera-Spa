"""Archive today's and yesterday's FaceGate evidence; publish the selected FaceGate source."""
from datetime import datetime, timedelta
import fcntl
import json
import os
import subprocess
import sys

from vera_facegate_control_log import VN_TZ


def sync_employee_names():
    """Use the active minute schedule even after TimeSoft has been retired."""
    from vera_facegate_cutover import runtime_engine
    from vera_employee_rename_sync import sync_device_names
    engine = None
    try:
        engine = runtime_engine()
        result = sync_device_names(engine)
        print(json.dumps({'employee_name_sync': result['status']}))
    except Exception as exc:
        # A name retry failure must not stop archiving attendance evidence.
        print(json.dumps({'employee_name_sync': 'pending', 'error_type': type(exc).__name__}))
    finally:
        if engine is not None:
            engine.dispose()


def sync_employee_deletions():
    from vera_facegate_cutover import runtime_engine
    from vera_employee_facegate_delete import sync_employee_deletions as sync
    engine = None
    try:
        engine = runtime_engine()
        result = sync(engine)
        print(json.dumps({'employee_delete_sync': result['status']}))
    except Exception as exc:
        print(json.dumps({'employee_delete_sync': 'pending', 'error_type': type(exc).__name__}))
    finally:
        if engine is not None:
            engine.dispose()


def process_arrival_penalties(engine, today):
    """Use the canonical arrival writer immediately after archive publication."""
    import io
    from contextlib import redirect_stdout
    import timesoft_sync_job as ts
    from vera_facegate_runtime import worker_frames
    with engine.begin() as conn:
        cfg = ts.auto_check.load_config(conn)
        frames = worker_frames(conn, [today])
        catalog = ts.auto_check.load_catalog(conn)
    employees = {ts._employee_key(name): name for _, frame in frames
                 for name in frame.get('employeeInfo.Name', [])}
    # The minute job reports aggregate counts only, never employee/device data.
    with redirect_stdout(io.StringIO()):
        return ts.process_timesoft_penalties(engine, cfg, employees, catalog, frames, include_synced_history=True)


def process_break_penalties(engine, day):
    import io
    from contextlib import redirect_stdout
    import timesoft_sync_job as ts
    with engine.begin() as conn:
        catalog = ts.auto_check.load_catalog(conn)
    with redirect_stdout(io.StringIO()):
        return ts.process_break_return_penalties(engine, catalog, work_date=day)


def reconcile_day(day, engine=None):
    """Commit one successful archive projection before its canonical writers."""
    from vera_attendance_source import enabled
    if not enabled():
        return []
    from vera_facegate_runtime import publish
    from vera_facegate_cutover import runtime_engine
    from vera_missing_checkin_absence import process as process_absences
    from vera_hc_rules import process as process_hc_rules
    owns_engine = engine is None
    engine = engine or runtime_engine()
    failures = []
    try:
        # These own separate transactions. A failed rule cannot roll back or
        # suppress the independently committed arrival/HC work.
        def publication():
            with engine.begin() as conn:
                return publish(conn, day, day)
        def transactional(rule):
            with engine.begin() as conn:
                return rule(conn)
        for name, operation in (
            ('published', publication),
            ('arrival_rule', lambda: process_arrival_penalties(engine, day)),
            ('break_rule', lambda: process_break_penalties(engine, day)),
            ('hc_rules', lambda: transactional(process_hc_rules)),
            ('absence_rule', lambda: transactional(process_absences)),
        ):
            try:
                result = operation()
                print(json.dumps({'date': day.isoformat(), name: result}))
                if isinstance(result, dict) and result.get('errors', 0):
                    failures.append({'date': day.isoformat(), 'stage': name, 'reason': 'rule_errors'})
            except Exception as exc:
                failures.append({'date': day.isoformat(), 'stage': name, 'reason': type(exc).__name__})
    finally:
        if owns_engine:
            engine.dispose()
    return failures


def archive_days():
    today = datetime.now(VN_TZ).date()
    failures = []
    # Publish today's arrivals before potentially slow historical device reads.
    # Yesterday still runs every pass for overnight shifts and delayed scans.
    for day in (today, today - timedelta(days=1)):
        try:
            result = subprocess.run([sys.executable, 'vera_facegate_sync.py',
                                     '--date', day.isoformat(), '--apply'],
                                    capture_output=True, text=True, timeout=210, check=False)
        except subprocess.TimeoutExpired:
            failures.append({'date': day.isoformat(), 'reason': 'sync_timeout'})
            continue
        try:
            summary = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            summary = {'ok': False, 'reason': 'invalid_sync_response'}
        if result.returncode or not summary.get('ok'):
            failures.append({'date': day.isoformat(), 'reason': summary.get('reason', 'sync_failed')})
            continue
        print(json.dumps({'date': day.isoformat(), 'inserted_count': summary['inserted_count'],
                          'stored_day_count': summary['stored_day_count']}))
        failures.extend(summary.get('reconciliation_failures', []))
    print(json.dumps({'ok': not failures, 'source': 'facegate', 'failures': failures}))
    return int(bool(failures))


def main():
    # The hourly fallback and the VPS timer can coincide. A local nonblocking
    # lock prevents duplicate device fetches, without occupying a DB connection.
    lock_path = '/opt/vera-spa/.facegate-sync.lock'
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'ok': True, 'skipped': 'sync_running'}))
            return 0
        sync_employee_deletions()
        sync_employee_names()
        return archive_days()
    finally:
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(main())

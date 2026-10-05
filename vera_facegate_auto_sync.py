"""Archive today's and yesterday's FaceGate evidence; publish the selected FaceGate source."""
from datetime import datetime, timedelta
import fcntl
import json
import os
import subprocess
import sys

from vera_facegate_control_log import VN_TZ


def archive_days():
    today = datetime.now(VN_TZ).date()
    failures = []
    for day in (today - timedelta(days=1), today):
        # Each invocation has its own bounded deadline and database connection.
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
        else:
            print(json.dumps({'date': day.isoformat(), 'inserted_count': summary['inserted_count'],
                              'stored_day_count': summary['stored_day_count']}))
    if failures:
        print(json.dumps({'ok': False, 'failures': failures}))
        return 1
    from vera_attendance_source import enabled
    if enabled():
        from vera_facegate_runtime import publish
        from vera_facegate_cutover import runtime_engine
        engine = runtime_engine()
        try:
            with engine.begin() as conn:
                reports = publish(conn, today - timedelta(days=1), today)
            from vera_missing_checkin_absence import process as process_absences
            with engine.begin() as conn:
                absence_result = process_absences(conn)
            print(json.dumps({'absence_rule': absence_result}))
            from vera_hc_rules import process as process_hc_rules
            with engine.begin() as conn:
                hc_result = process_hc_rules(conn)
            print(json.dumps({'hc_rules': hc_result}))
        finally:
            engine.dispose()
        print(json.dumps({'ok': True, 'source': 'facegate', 'published': reports}))
    return 0


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
        return archive_days()
    finally:
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(main())

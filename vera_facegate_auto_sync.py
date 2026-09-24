"""Archive today's and yesterday's FaceGate evidence; never project attendance."""
from datetime import datetime, timedelta
import json
import subprocess
import sys

from vera_facegate_control_log import VN_TZ


def main():
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
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Inspect, prepare or activate the explicit FaceGate production source.

Default is read-only. --apply archives current device evidence, publishes a
separate cache and atomically selects FaceGate. It never edits payroll, photos,
employee mappings, reviewed exceptions, old caches or service configuration.
"""
import argparse
from datetime import date, datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
from urllib.request import urlopen

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import vera_attendance_source as source
from vera_facegate_control_log import VN_TZ


class CutoverError(RuntimeError):
    pass


def runtime_engine(*, readonly=False):
    from vera_facegate_readiness import runtime_device_environment
    from vera_vps_data_check import _database_url, _running_api_environment
    from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
    runtime_device_environment()
    env = ({key: os.environ.get(key, '') for key in RUNTIME_ENV_KEYS}
           if load_managed_runtime_environment() else _running_api_environment())
    sslmode = env.get('DB_SSLMODE', 'require')
    if sslmode not in {'require', 'verify-ca', 'verify-full'}:
        sslmode = 'require'
    return create_engine(_database_url(env), poolclass=NullPool, connect_args={
        'connect_timeout': 5, 'sslmode': sslmode,
        'options': '-c statement_timeout=15000 -c lock_timeout=2000' +
                   (' -c default_transaction_read_only=on' if readonly else '')})


def verify_runtime(expected_commit):
    root = Path(__file__).resolve().parent
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != expected_commit:
        raise CutoverError('unexpected_deployed_commit')
    active_roots = set()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if b'vera_web_v2_api_v38:app' in (proc/'cmdline').read_bytes():
                active_roots.add((proc/'cwd').resolve())
        except (OSError, PermissionError):
            continue
    if active_roots != {root}:
        raise CutoverError('api_release_not_verified')
    for endpoint in ('/v2/auth/health', '/v2/health'):
        with urlopen('http://127.0.0.1:8000'+endpoint, timeout=10) as response:
            if response.status != 200 or json.load(response).get('ok') is not True:
                raise CutoverError('production_health_failed')
    return commit


def atomic_write(path, value):
    fd, name = tempfile.mkstemp(prefix='.attendance-source-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=True, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # No secrets; API, cron and the deployment account must read one policy.
        os.chmod(name, 0o644)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def inspect(conn, day):
    from collections import Counter
    from vera_facegate_runtime import records
    rows = records(conn, day, day)
    return {**source.health(conn), 'date': day.isoformat(),
            'employee_count': len(rows),
            'checked_in_count': sum(bool(r.get('check_in')) for r in rows),
            'pending_employee_count': sum(bool(r.get('attendance_pending')) for r in rows),
            'applied_identity_review_ids': sorted({review for r in rows
                for review in r.get('applied_identity_review_ids', [])}),
            'pending_reasons': dict(Counter(reason for row in rows for reason in row.get('attendance_pending_reasons', [])))}


def activate(engine, day, commit, *, apply=False):
    from vera_facegate_sync import sync_day
    from vera_facegate_runtime import publish
    from vera_live_tour_checkin_signal import QUEUE, JOB_KEY
    today = datetime.now(VN_TZ).date()
    if day != today and not (source.enabled() and source.effective_date() == day):
        raise CutoverError('initial_cutover_must_be_today')
    previous = source.configuration()
    if previous['source'] == 'facegate' and previous['effective_date'] != day.isoformat():
        raise CutoverError('existing_cutover_date_must_not_change')
    # The device fetch owns/releases its own connections before network I/O.
    for archive_day in (today-timedelta(days=1), today):
        result = sync_day(engine, archive_day.isoformat(), apply=True)
        if not result.get('ok'):
            raise CutoverError('archive_sync_failed')
    with engine.begin() as conn:
        published = publish(conn, today-timedelta(days=1), today)
    if not apply:
        return {'ok': True, 'mode': 'prepare', 'published': published, 'source_changed': False}
    path = Path(os.environ.get('VERA_ATTENDANCE_SOURCE_FILE', source.CONFIG_PATH))
    policy = {'version': 1, 'source': 'facegate', 'effective_date': day.isoformat(),
              'activated_at': datetime.now(VN_TZ).isoformat(), 'release_commit': commit,
              'authorization': 'operator_requested_timesoft_retirement',
              'comparison_blockers_waived': True,
              'missing_evidence_policy': 'pending_per_employee_no_guessed_payroll'}
    # Serialize against the existing background job. No device/network I/O
    # while this connection is held; committed notifications remain untouched.
    with engine.connect() as conn:
        locked = conn.execute(text('SELECT pg_try_advisory_lock(hashtext(:key))'),
                              {'key': 'vera-timesoft-background-sync-v84'}).scalar()
        conn.commit()
        if not locked:
            raise CutoverError('attendance_worker_running_retry_later')
        changed = False
        try:
            if previous['source'] != 'facegate':
                atomic_write(path, policy)
                changed = True
            with conn.begin():
                # Invalidate even if prepare already published identical scans.
                conn.execute(text('''UPDATE vera_background_job SET
                    payload=payload || jsonb_build_object('fingerprints','{}'::jsonb)
                    WHERE queue_name=:queue AND job_key=:job'''), {'queue': QUEUE, 'job': JOB_KEY})
                published = publish(conn, today-timedelta(days=1), today)
                status = inspect(conn, today)
                if not status['cache_fresh'] or not status['checked_in_count']:
                    raise CutoverError('facegate_business_verification_failed')
            return {'ok': True, 'mode': 'apply', 'already_applied': not changed,
                    'source_changed': changed, 'published': published, **status,
                    'payroll_written': False, 'penalties_written': False}
        except BaseException:
            if changed:
                path.unlink()
            raise
        finally:
            conn.execute(text('SELECT pg_advisory_unlock(hashtext(:key))'),
                         {'key': 'vera-timesoft-background-sync-v84'})
            conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date')
    parser.add_argument('--expected-commit')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    engine, fd = None, None
    def deadline(*_):
        raise TimeoutError('cutover_deadline')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(450)
    try:
        writing = args.prepare or args.apply
        day = (date.fromisoformat(args.date) if args.date else
               source.effective_date() if writing and source.enabled() else datetime.now(VN_TZ).date())
        if writing:
            if not args.expected_commit:
                raise CutoverError('expected_commit_required')
            commit = verify_runtime(args.expected_commit)
            fd = os.open('/opt/vera-spa/.facegate-sync.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        engine = runtime_engine(readonly=not writing)
        if writing:
            result = activate(engine, day, commit, apply=args.apply)
        else:
            with engine.connect() as conn:
                status = inspect(conn, day)
                result = {'ok': status['cache_fresh'] if source.enabled() else True,
                          'mode': 'inspect', **status, 'database_writes': False}
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result['ok'] else 1
    except Exception as exc:
        # No exception strings: database/device errors can contain credentials.
        reason = str(exc) if type(exc) is CutoverError else type(exc).__name__
        print(json.dumps({'ok': False, 'reason': reason}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        if fd is not None:
            os.close(fd)
        signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())

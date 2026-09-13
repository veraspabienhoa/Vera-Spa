"""Read bounded runtime diagnostics; never print SQL, parameters or log bodies."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess


def safe_log_summary(message: str) -> list[str]:
    """Allow only stack locations and exception types, not exception values."""
    output = []
    for line in message.splitlines():
        frame = re.search(r'File "[^"\n]*/([A-Za-z0-9_]+\.py)", line ([0-9]+), in ([A-Za-z0-9_<>]+)', line)
        if frame:
            output.append(f"frame={frame[1]}:{frame[2]}:{frame[3]}")
        exception = re.match(r'\s*((?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Timeout)):', line)
        if exception:
            output.append(f"exception={exception[1]}")
        pool = re.search(r'QueuePool limit of size ([0-9]+) overflow ([0-9]+) reached, connection timed out, timeout ([0-9.]+)', line)
        if pool:
            output.append(f"pool_exhausted size={pool[1]} overflow={pool[2]} timeout={pool[3]}")
    return output


def report_journal() -> None:
    pid_result = subprocess.run(
        ['pgrep', '-n', '-f', '[v]era_web_v2_api_v38:app'],
        capture_output=True, text=True, timeout=5,
    )
    pid = pid_result.stdout.strip()
    if not pid.isdigit():
        print('RUNTIME: API process not found')
        return
    cgroup = Path(f'/proc/{pid}/cgroup').read_text()
    unit = re.search(r'/system\.slice/([A-Za-z0-9_.@-]+\.service)', cgroup)
    if not unit:
        print('RUNTIME: API systemd unit not found')
        return
    result = subprocess.run(
        ['journalctl', '-q', '-u', unit[1], '--since', '20 minutes ago',
         '--no-pager', '--reverse', '-o', 'json', '-n', '1800'],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode:
        print('RUNTIME: journal unavailable')
        return
    counts = Counter()
    last_seen = {}
    records = 0
    for line in result.stdout.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        records += 1
        for summary in safe_log_summary(str(entry.get('MESSAGE', ''))):
            counts[summary] += 1
            stamp = str(entry.get('__REALTIME_TIMESTAMP', ''))
            if stamp.isdigit():
                observed = datetime.fromtimestamp(int(stamp) / 1_000_000, timezone.utc).isoformat()
                last_seen[summary] = max(last_seen.get(summary, ''), observed)
    print(f'RUNTIME: journal_records={records} (last 20 minutes, at most 1800 records)')
    for summary, count in counts.items():
        print(f'RUNTIME: count={count} last_utc={last_seen.get(summary, "unknown")} {summary}')


def report_database() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from vera_vps_data_check import _database_url, _running_api_environment
    from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment

    environment = (
        {key: os.environ.get(key, '') for key in RUNTIME_ENV_KEYS}
        if load_managed_runtime_environment() else _running_api_environment()
    )
    sslmode = environment.get('DB_SSLMODE', 'require')
    if sslmode not in {'require', 'verify-ca', 'verify-full'}:
        sslmode = 'require'
    engine = create_engine(_database_url(environment), poolclass=NullPool, connect_args={
        'connect_timeout': 5, 'sslmode': sslmode,
        'application_name': 'vera-runtime-diagnostics',
        'options': '-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000',
    })
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT state, wait_event_type, wait_event,
                       CASE WHEN application_name='vera-web-v2-auth' THEN 'auth' ELSE 'other' END AS pool,
                       CASE WHEN query ILIKE '%pg_advisory_xact_lock%' THEN 'advisory_lock'
                            WHEN query ILIKE '%vera_auto_check_event%' THEN 'auto_check'
                            WHEN query ILIKE '%leave_records%' THEN 'leave'
                            WHEN query ILIKE '%vera_app_setting%' THEN 'app_setting'
                            ELSE 'other' END AS operation,
                       COUNT(*) AS connections,
                       COALESCE(MAX(EXTRACT(EPOCH FROM now()-xact_start))::int, 0) AS oldest_transaction_seconds,
                       MAX(cardinality(pg_blocking_pids(pid))) AS blockers
                FROM pg_stat_activity
                WHERE datname=current_database() AND usename=current_user AND pid<>pg_backend_pid()
                GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5
            """)).mappings().all()
        print('RUNTIME: database_read_only_check=OK')
        for row in rows:
            print('RUNTIME: ' + json.dumps(dict(row), sort_keys=True))
    finally:
        engine.dispose()


def main() -> None:
    for report in (report_journal, report_database):
        try:
            report()
        except Exception as exc:
            # Never stringify database exceptions: they can include credentials,
            # bound values and customer data in a public workflow log.
            print(f'RUNTIME: {report.__name__} failed type={type(exc).__name__}')


if __name__ == '__main__':
    main()

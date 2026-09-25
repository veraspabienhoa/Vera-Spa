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
        auth = re.search(
            r'Web V2 local auth: identity lookup unavailable: ([A-Za-z_][A-Za-z0-9_]*); '
            r'cause=([A-Za-z_][A-Za-z0-9_]*); sqlstate=([A-Z0-9]{5}|unknown)(?:;|$)', line)
        if auth:
            output.append(f'auth_lookup_error type={auth[1]} cause={auth[2]} sqlstate={auth[3]}')
        pool = re.search(r'QueuePool limit of size ([0-9]+) overflow ([0-9]+) reached, connection timed out, timeout ([0-9.]+)', line)
        if pool:
            output.append(f"pool_exhausted size={pool[1]} overflow={pool[2]} timeout={pool[3]}")
        timing = re.search(
            r'LIVE_TOUR_TIMING action=(booking|multi_booking|start|start_room|finish_to_pending|finish_room|complete|checkout|quick_checkout) '
            r'outcome=(ok|error) total_ms=([0-9.]{1,20}) sql_count=([0-9]{1,10}) sql_ms=([0-9.]{1,20}) phases_ms=', line)
        if timing:
            phases = re.findall(
                r"'(authorize|lock_read|apply|write|commit|response_read|render)': ([0-9.]{1,20})(?=[,}])",
                line[timing.end():timing.end()+1000])
            output.append(
                f'live_tour_timing action={timing[1]} outcome={timing[2]} total_ms={timing[3]} '
                f'sql_count={timing[4]} sql_ms={timing[5]}'
                + ''.join(f' {name}_ms={value}' for name, value in phases))
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


ACTIVITY_DETAIL_SQL = """
    SELECT pid AS backend_pid, state, wait_event_type, wait_event,
           client_addr IS NOT DISTINCT FROM inet_client_addr() AS same_client_as_diagnostic,
           CASE WHEN application_name='vera-web-v2-auth' THEN 'auth' ELSE 'other' END AS pool,
           CASE WHEN query ~* '^\\s*BEGIN' THEN 'begin'
                WHEN query ~* '^\\s*COMMIT' THEN 'commit'
                WHEN query ~* '^\\s*ROLLBACK' THEN 'rollback'
                WHEN query ~* '^\\s*SELECT' THEN 'select'
                WHEN query ~* '^\\s*(INSERT|UPDATE|DELETE)' THEN 'write'
                WHEN query ~* '^\\s*(CREATE|ALTER|DROP)' THEN 'ddl'
                WHEN query ~* '^\\s*(SET|SHOW)' THEN 'session_setting'
                ELSE 'other' END AS statement_kind,
           CASE WHEN query ILIKE '%pg_advisory%' THEN 'advisory_lock'
                WHEN query ILIKE '%vera_training%' OR query ILIKE '%vera_evaluation%'
                     OR query ILIKE '%vera_employee_evaluation%' THEN 'training'
                WHEN query ILIKE '%vera_live_tour%' THEN 'live_tour'
                WHEN query ILIKE '%vera_auto_check%' THEN 'auto_check'
                WHEN query ILIKE '%leave_records%' THEN 'leave'
                WHEN query ILIKE '%vera_app_setting%' THEN 'app_setting'
                WHEN query ILIKE '%vera_dataset_cache%' THEN 'dataset_cache'
                WHEN query ILIKE '%employees%' THEN 'employees'
                ELSE 'other' END AS operation,
           COALESCE(EXTRACT(EPOCH FROM clock_timestamp()-xact_start)::int,0) AS transaction_seconds,
           COALESCE(EXTRACT(EPOCH FROM clock_timestamp()-query_start)::int,0) AS query_seconds,
           COALESCE(EXTRACT(EPOCH FROM clock_timestamp()-state_change)::int,0) AS state_seconds,
           cardinality(pg_blocking_pids(pid)) AS blockers
    FROM pg_stat_activity
    WHERE datname=current_database() AND usename=current_user AND pid<>pg_backend_pid()
      AND state IS DISTINCT FROM 'idle'
    ORDER BY xact_start NULLS LAST, pid LIMIT 20
"""


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
            # Only fixed categories and numeric ages leave PostgreSQL. Do not fetch
            # query text, usernames, addresses, parameters or arbitrary application names.
            details = conn.execute(text(ACTIVITY_DETAIL_SQL)).mappings().all()
        print('RUNTIME: database_read_only_check=OK')
        for row in rows:
            print('RUNTIME: ' + json.dumps(dict(row), sort_keys=True))
        for row in details:
            print('RUNTIME_DETAIL: ' + json.dumps(dict(row), sort_keys=True))
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

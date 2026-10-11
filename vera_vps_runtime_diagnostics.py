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
        pool_metrics = re.search(r'VERA_POOL_METRICS (\{.{1,4000}\})$', line)
        if pool_metrics:
            try:
                metrics = json.loads(pool_metrics[1])
            except (TypeError, ValueError):
                continue
            if not isinstance(metrics, dict) or metrics.get('pool') not in {'api_business', 'background', 'auth'}:
                continue
            values = []
            for key in ('size', 'overflow_limit', 'checked_in', 'checked_out', 'overflow',
                        'acquiring', 'acquired', 'timeouts', 'errors'):
                value = metrics.get(key)
                if type(value) is int and 0 <= value <= 10**15:
                    values.append(f'{key}={value}')
            for key in ('acquire_ms', 'max_acquire_ms'):
                value = metrics.get(key)
                if type(value) in {int, float} and 0 <= value <= 10**15:
                    values.append(f'{key}={value:.2f}')
            if values:
                output.append('pool_metrics pool=' + metrics['pool'] + ' ' + ' '.join(values))
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
           CASE WHEN application_name='vera-web-v2-auth' THEN 'auth'
                WHEN application_name='vera-web-v2-business' THEN 'business'
                WHEN application_name='vera-background' THEN 'background' ELSE 'other' END AS pool,
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


# These describe the server and explicit database/role overrides, not the
# diagnostic session's own short read-only deadlines or live app-pool settings.
CAPACITY_SQL = """
    SELECT current_setting('max_connections')::int AS max_connections,
           current_setting('superuser_reserved_connections')::int AS superuser_reserved,
           COALESCE(current_setting('reserved_connections', true), '0')::int AS reserved,
           (SELECT rolconnlimit FROM pg_roles WHERE rolname=current_user) AS role_connection_limit,
           (SELECT COUNT(*) FROM pg_stat_activity WHERE backend_type='client backend') AS client_connections,
           (SELECT COUNT(*) FROM pg_stat_activity WHERE usename=current_user) AS role_connections
"""
ROLE_DEADLINE_SQL = """
    SELECT CASE WHEN setdatabase=0 THEN 'role'
                WHEN setrole=0 THEN 'database' ELSE 'database_role' END AS source,
           split_part(value, '=', 1) AS setting,
           CASE WHEN split_part(value, '=', 2) ~ '^[0-9]{1,9}(ms|s|min|h|d)?$'
                THEN split_part(value, '=', 2) ELSE 'configured' END AS value
    FROM pg_db_role_setting CROSS JOIN LATERAL unnest(setconfig) AS value
    WHERE setdatabase IN (0, (SELECT oid FROM pg_database WHERE datname=current_database()))
      AND setrole IN (0, (SELECT oid FROM pg_roles WHERE rolname=current_user))
      AND split_part(value, '=', 1) IN
          ('statement_timeout', 'lock_timeout', 'idle_in_transaction_session_timeout')
    ORDER BY 1,2 LIMIT 9
"""


def report_database() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from vera_vps_data_check import _database_url, _running_api_environment
    from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment

    environment = (
        {key: os.environ[key] for key in RUNTIME_ENV_KEYS if key in os.environ}
        if load_managed_runtime_environment() else _running_api_environment()
    )
    from vera_database_runtime import connection_budget
    print('RUNTIME_BUDGET: ' + json.dumps(connection_budget(environment), sort_keys=True))
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
            capacity = conn.execute(text(CAPACITY_SQL)).mappings().one()
            deadlines = conn.execute(text(ROLE_DEADLINE_SQL)).mappings().all()
            rows = conn.execute(text("""
                SELECT state, wait_event_type, wait_event,
                       CASE WHEN application_name='vera-web-v2-auth' THEN 'auth'
                WHEN application_name='vera-web-v2-business' THEN 'business'
                WHEN application_name='vera-background' THEN 'background' ELSE 'other' END AS pool,
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
        print('RUNTIME_CAPACITY: ' + json.dumps(dict(capacity), sort_keys=True))
        for row in deadlines:
            print('RUNTIME_ROLE_DEADLINE: ' + json.dumps(dict(row), sort_keys=True))
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

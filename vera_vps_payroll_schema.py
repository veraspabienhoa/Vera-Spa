"""Explicit, non-destructive payroll schema installation for the VPS."""
import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool
from vera_vps_data_check import (
    RUNTIME_ENV_KEYS, _database_url, _running_api_environment,
    load_managed_runtime_environment,
)


def statements():
    source = Path(__file__).with_name('schema.sql').read_text()
    start = source.index('CREATE TABLE IF NOT EXISTS payroll_history_rows (')
    end_marker = 'ALTER TABLE payroll_history_rows ENABLE ROW LEVEL SECURITY;'
    end = source.index(end_marker, start) + len(end_marker)
    return [part.strip() for part in source[start:end].split(';') if part.strip()]


def verify(conn):
    columns = {c['name']: str(c['type']).upper() for c in inspect(conn).get_columns('payroll_history_rows', schema='public')}
    expected = {'id': 'BIGINT', 'batch_id': 'TEXT', 'employee_name': 'TEXT',
                'period_start': 'DATE', 'period_end': 'DATE', 'payload': 'JSONB', 'saved_at': 'TIMESTAMP'}
    if any(columns.get(key) != value for key, value in expected.items()):
        raise RuntimeError('payroll_history_rows schema mismatch; manual review required')
    conn.execute(text('SELECT id, batch_id, employee_name, period_start, period_end, payload, saved_at FROM public.payroll_history_rows LIMIT 0'))


def migrate(conn):
    conn.execute(text("SET LOCAL lock_timeout = '5s'"))
    conn.execute(text("SET LOCAL statement_timeout = '30s'"))
    conn.execute(text('SET LOCAL search_path TO public'))
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera_payroll_schema_v1'))"))
    # Existing tables are validated, never silently reshaped or backfilled.
    if inspect(conn).has_table('payroll_history_rows', schema='public'):
        verify(conn)
        return
    for sql in statements():
        conn.execute(text(sql))
    verify(conn)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Create missing table; otherwise verify only')
    args = parser.parse_args()
    loaded = load_managed_runtime_environment()
    env = {k: os.environ.get(k, '') for k in RUNTIME_ENV_KEYS} if loaded else _running_api_environment()
    if not env:
        raise SystemExit('PAYROLL SCHEMA: runtime environment unavailable')
    sslmode = env.get('DB_SSLMODE', 'require') or 'require'
    if sslmode not in {'require', 'verify-ca', 'verify-full'}:
        sslmode = 'require'
    engine = create_engine(_database_url(env), poolclass=NullPool,
                           connect_args={'sslmode': sslmode, 'connect_timeout': 10})
    try:
        with engine.begin() as conn:
            if args.apply:
                migrate(conn)
            else:
                verify(conn)
        print('PAYROLL SCHEMA: verified')
    except Exception as exc:
        # Do not print connection strings, SQL parameters or payroll contents.
        raise SystemExit(f'PAYROLL SCHEMA FAILED: {type(exc).__name__}; no migration committed') from None
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()

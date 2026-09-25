"""Dry-run by default. Prune only completed Live Tour projection jobs."""
import argparse
import json
import os
from time import monotonic
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

QUEUE = 'live_tour_projection'
ELIGIBLE = "queue_name=:queue AND status='done' AND completed_at < NOW()-make_interval(days=>:days) AND locked_at IS NULL"
SETTING_TABLE = 'vera_technical_retention_setting'
DEFAULT_DAYS = 3
MAX_INTERVAL_HOURS = 168
# A dedicated session lock spans short batches; it never locks Live Tour itself.
CLEANUP_LOCK = 724190631


def ensure_setting(conn):
    conn.execute(text("SET LOCAL statement_timeout='3s'"))
    conn.execute(text("SET LOCAL lock_timeout='200ms'"))
    columns = set(conn.execute(text('''SELECT attname FROM pg_attribute
        WHERE attrelid=to_regclass(:table) AND attnum>0 AND NOT attisdropped'''),
        {'table': SETTING_TABLE}).scalars())
    if {'cleanup_interval_hours', 'last_cleanup_at', 'last_cleanup_removed'} <= columns:
        return
    conn.execute(text(f"""CREATE TABLE IF NOT EXISTS {SETTING_TABLE} (
        singleton SMALLINT PRIMARY KEY DEFAULT 1 CHECK (singleton=1),
        retention_days SMALLINT NOT NULL DEFAULT 3 CHECK (retention_days BETWEEN 1 AND 3),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by TEXT NOT NULL DEFAULT 'system'
    )"""))
    conn.execute(text(f'''ALTER TABLE {SETTING_TABLE}
        ADD COLUMN IF NOT EXISTS cleanup_interval_hours SMALLINT NOT NULL DEFAULT 1
            CHECK (cleanup_interval_hours BETWEEN 1 AND {MAX_INTERVAL_HOURS}),
        ADD COLUMN IF NOT EXISTS last_cleanup_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS last_cleanup_removed INTEGER NOT NULL DEFAULT 0'''))
    conn.execute(text(f"INSERT INTO {SETTING_TABLE}(singleton) VALUES(1) ON CONFLICT DO NOTHING"))


def ensure_cleanup_index(conn):
    # Restrict the index to the one queue/status that this job scans hourly.
    if conn.execute(text("SELECT to_regclass('idx_vera_background_job_projection_retention')")).scalar_one():
        return
    conn.execute(text("""CREATE INDEX IF NOT EXISTS idx_vera_background_job_projection_retention
        ON vera_background_job (completed_at,id)
        WHERE queue_name='live_tour_projection' AND status='done' AND locked_at IS NULL"""))


def retention_days(conn):
    value = conn.execute(text(f'SELECT retention_days FROM {SETTING_TABLE} WHERE singleton=1')).scalar_one_or_none()
    return int(value) if value is not None else DEFAULT_DAYS


def read_setting(conn):
    row = conn.execute(text(f'''SELECT retention_days AS days, cleanup_interval_hours,
        last_cleanup_at, last_cleanup_removed,
        last_cleanup_at + make_interval(hours=>cleanup_interval_hours) AS next_cleanup_at,
        last_cleanup_at IS NULL OR
            NOW() >= last_cleanup_at + make_interval(hours=>cleanup_interval_hours) AS due
        FROM {SETTING_TABLE} WHERE singleton=1''')).mappings().one()
    return dict(row)


def public_setting(conn):
    value = read_setting(conn)
    value.pop('due')
    return {**value, 'scope': 'completed_live_tour_projection_jobs'}
PRUNE = text(f"""
    WITH expired AS (
        SELECT id FROM vera_background_job WHERE {ELIGIBLE}
        ORDER BY completed_at,id LIMIT :batch FOR UPDATE SKIP LOCKED
    )
    DELETE FROM vera_background_job AS job USING expired
    WHERE job.id=expired.id AND job.status='done' AND job.locked_at IS NULL
    RETURNING job.id
""")


def run(engine, apply=False, *, scheduled=False):
    with engine.connect() as conn:
        locked = False
        try:
            with conn.begin():
                ensure_setting(conn)
                if apply:
                    locked = bool(conn.execute(text('SELECT pg_try_advisory_lock(:key)'),
                        {'key': CLEANUP_LOCK}).scalar_one())
                    if not locked:
                        return {'dry_run': False, 'removed': 0, 'skipped': 'already_running'}
                setting = read_setting(conn)
                if scheduled and not setting['due']:
                    return {'dry_run': not apply, 'removed': 0, 'skipped': 'not_due',
                        'cleanup_interval_hours': setting['cleanup_interval_hours']}
                ensure_cleanup_index(conn)
                days = setting['days']
                eligible = conn.execute(text(f'SELECT count(*) FROM vera_background_job WHERE {ELIGIBLE}'),
                    {'queue': QUEUE, 'days': days}).scalar_one()
            result = {'dry_run': not apply, 'eligible': eligible, 'removed': 0, 'retention_hours': days*24}
            if not apply:
                return result
            started = monotonic()
            completed = False
            # No Live Tour lock or nested connection. Release row locks per batch.
            for _ in range(20):
                if monotonic()-started > 20:
                    break
                with conn.begin():
                    conn.execute(text("SET LOCAL statement_timeout='3s'"))
                    conn.execute(text("SET LOCAL lock_timeout='200ms'"))
                    days = retention_days(conn)
                    count = len(conn.execute(PRUNE, {'queue': QUEUE, 'days': days, 'batch': 500}).all())
                result['removed'] += count
                if count < 500:
                    completed = True
                    break
            if completed:
                with conn.begin():
                    conn.execute(text("SET LOCAL statement_timeout='3s'"))
                    conn.execute(text("SET LOCAL lock_timeout='200ms'"))
                    conn.execute(text(f'''UPDATE {SETTING_TABLE}
                        SET last_cleanup_at=clock_timestamp(),last_cleanup_removed=:removed
                        WHERE singleton=1'''), {'removed': result['removed']})
            # A timeout, failed or incomplete pass does not postpone the next retry.
            return {**result, 'completed': completed}
        finally:
            if locked:
                conn.rollback()
                try:
                    with conn.begin():
                        conn.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': CLEANUP_LOCK})
                except Exception:
                    conn.invalidate()  # Never return a session lock to a pool.


def runtime_engine():
    from vera_vps_data_check import _database_url, _running_api_environment
    from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
    env = {k:os.environ.get(k,'') for k in RUNTIME_ENV_KEYS} if load_managed_runtime_environment() else _running_api_environment()
    return create_engine(_database_url(env),poolclass=NullPool,
        connect_args={'connect_timeout':5,'sslmode':env.get('DB_SSLMODE','require')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--scheduled', action='store_true', help='Respect the Admin cleanup interval')
    args = parser.parse_args()
    engine = runtime_engine()
    try:
        print(json.dumps(run(engine, args.apply, scheduled=args.scheduled)))
    except Exception as error:
        print(json.dumps({'ok':False,'error_type':type(error).__name__}))
        raise SystemExit(1) from None
    finally:
        engine.dispose()

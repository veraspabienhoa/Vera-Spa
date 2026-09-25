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


def ensure_setting(conn):
    conn.execute(text(f"""CREATE TABLE IF NOT EXISTS {SETTING_TABLE} (
        singleton SMALLINT PRIMARY KEY DEFAULT 1 CHECK (singleton=1),
        retention_days SMALLINT NOT NULL DEFAULT 3 CHECK (retention_days BETWEEN 1 AND 3),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by TEXT NOT NULL DEFAULT 'system'
    )"""))
    conn.execute(text(f"INSERT INTO {SETTING_TABLE}(singleton) VALUES(1) ON CONFLICT DO NOTHING"))


def ensure_cleanup_index(conn):
    # Restrict the index to the one queue/status that this job scans hourly.
    conn.execute(text("""CREATE INDEX IF NOT EXISTS idx_vera_background_job_projection_retention
        ON vera_background_job (completed_at,id)
        WHERE queue_name='live_tour_projection' AND status='done' AND locked_at IS NULL"""))


def retention_days(conn):
    value = conn.execute(text(f'SELECT retention_days FROM {SETTING_TABLE} WHERE singleton=1')).scalar_one_or_none()
    return int(value) if value is not None else DEFAULT_DAYS
PRUNE = text(f"""
    WITH expired AS (
        SELECT id FROM vera_background_job WHERE {ELIGIBLE}
        ORDER BY completed_at,id LIMIT :batch FOR UPDATE SKIP LOCKED
    )
    DELETE FROM vera_background_job AS job USING expired
    WHERE job.id=expired.id AND job.status='done' AND job.locked_at IS NULL
    RETURNING job.id
""")


def run(engine, apply=False):
    with engine.begin() as conn:
        ensure_setting(conn)
        ensure_cleanup_index(conn)
        conn.execute(text("SET LOCAL statement_timeout='3s'"))
        days = retention_days(conn)
        eligible = conn.execute(text(f'SELECT count(*) FROM vera_background_job WHERE {ELIGIBLE}'), {'queue':QUEUE,'days':days}).scalar_one()
    removed = 0
    if apply:
        started = monotonic()
        # Short transactions release row locks between batches. No TRUNCATE,
        # VACUUM FULL, financial tables, failed jobs, retries or active leases.
        for _ in range(20):
            if monotonic()-started > 20:
                break
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL statement_timeout='3s'"))
                conn.execute(text("SET LOCAL lock_timeout='200ms'"))
                count = len(conn.execute(PRUNE, {'queue':QUEUE,'days':days,'batch':500}).all())
            removed += count
            if count < 500:
                break
    return {'dry_run':not apply,'eligible':eligible,'removed':removed,'retention_hours':days*24}


def runtime_engine():
    from vera_vps_data_check import _database_url, _running_api_environment
    from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
    env = {k:os.environ.get(k,'') for k in RUNTIME_ENV_KEYS} if load_managed_runtime_environment() else _running_api_environment()
    return create_engine(_database_url(env),poolclass=NullPool,
        connect_args={'connect_timeout':5,'sslmode':env.get('DB_SSLMODE','require')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    engine = runtime_engine()
    try:
        print(json.dumps(run(engine, args.apply)))
    except Exception as error:
        print(json.dumps({'ok':False,'error_type':type(error).__name__}))
        raise SystemExit(1) from None
    finally:
        engine.dispose()

"""Dry-run by default. Only completed Live Tour projection jobs, older than 72h."""
import argparse
import json
import os
from time import monotonic
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

QUEUE = 'live_tour_projection'
ELIGIBLE = "queue_name=:queue AND status='done' AND completed_at < NOW()-INTERVAL '3 days' AND locked_at IS NULL"
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
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL statement_timeout='3s'"))
        eligible = conn.execute(text(f'SELECT count(*) FROM vera_background_job WHERE {ELIGIBLE}'), {'queue':QUEUE}).scalar_one()
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
                count = len(conn.execute(PRUNE, {'queue':QUEUE,'batch':500}).all())
            removed += count
            if count < 500:
                break
    return {'dry_run':not apply,'eligible':eligible,'removed':removed,'retention_hours':72}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    # Reuse the existing managed runtime environment; never put DB secrets in cron.
    from vera_vps_data_check import _database_url, _running_api_environment
    from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
    env = {k:os.environ.get(k,'') for k in RUNTIME_ENV_KEYS} if load_managed_runtime_environment() else _running_api_environment()
    engine = create_engine(_database_url(env),poolclass=NullPool,
        connect_args={'connect_timeout':5,'sslmode':env.get('DB_SSLMODE','require')})
    try:
        print(json.dumps(run(engine, args.apply)))
    except Exception as error:
        print(json.dumps({'ok':False,'error_type':type(error).__name__}))
        raise SystemExit(1) from None
    finally:
        engine.dispose()

"""Explicit bounded migration; never called by an API request."""
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text

from vera_web_v2_leave_month import MonthReader, revision

REVISION_DDL = '''CREATE TABLE IF NOT EXISTS vera_leave_month_revision (
    month_start date PRIMARY KEY, version bigint NOT NULL DEFAULT 1
)'''
FUNCTION_DDL = '''CREATE OR REPLACE FUNCTION vera_bump_leave_month()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE affected date[]; month_value date;
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        UPDATE vera_leave_month_revision SET version=version+1;
        RETURN NULL;
    ELSIF TG_OP = 'INSERT' THEN
        SELECT array_agg(DISTINCT date_trunc('month',leave_date)::date)
            INTO affected FROM new_leave_rows;
    ELSIF TG_OP = 'DELETE' THEN
        SELECT array_agg(DISTINCT date_trunc('month',leave_date)::date)
            INTO affected FROM old_leave_rows;
    ELSE
        SELECT array_agg(DISTINCT month_start) INTO affected FROM (
            SELECT date_trunc('month',leave_date)::date AS month_start FROM new_leave_rows
            UNION SELECT date_trunc('month',leave_date)::date FROM old_leave_rows
        ) months;
    END IF;
    -- One increment per affected month per SQL statement, including bulk imports.
    -- Consistent order avoids opposite-direction month-move lock inversion.
    FOR month_value IN SELECT DISTINCT x FROM unnest(affected) x WHERE x IS NOT NULL ORDER BY x LOOP
        INSERT INTO vera_leave_month_revision(month_start,version) VALUES(month_value,1)
        ON CONFLICT(month_start) DO UPDATE SET version=vera_leave_month_revision.version+1;
    END LOOP;
    RETURN NULL;
END $$'''
TRIGGERS = {
    'insert': 'INSERT REFERENCING NEW TABLE AS new_leave_rows',
    'update': 'UPDATE REFERENCING OLD TABLE AS old_leave_rows NEW TABLE AS new_leave_rows',
    'delete': 'DELETE REFERENCING OLD TABLE AS old_leave_rows',
    'truncate': 'TRUNCATE',
}
INDEX_DDL = '''CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_background_projection_retention
    ON vera_background_job(completed_at,id)
    WHERE queue_name='live_tour_projection' AND status='done' AND locked_at IS NULL'''


def migrate(engine):
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout='500ms'"))
        conn.execute(text("SET LOCAL statement_timeout='5s'"))
        if revision(conn, datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().replace(day=1)) is None:
            conn.execute(text(REVISION_DDL))
            conn.execute(text(FUNCTION_DDL))
            for operation, clause in TRIGGERS.items():
                name = 'vera_leave_month_' + operation
                conn.execute(text(f'DROP TRIGGER IF EXISTS {name} ON leave_records'))
                event, _, referencing = clause.partition(' REFERENCING ')
                reference = ' REFERENCING ' + referencing if referencing else ''
                conn.execute(text(f'CREATE TRIGGER {name} AFTER {event} ON leave_records{reference} '
                                  'FOR EACH STATEMENT EXECUTE FUNCTION vera_bump_leave_month()'))
            # Invalidate any cache left over from a partially disabled installation.
            conn.execute(text('UPDATE vera_leave_month_revision SET version=version+1'))
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.execute(text("SET lock_timeout='500ms'"))
        conn.execute(text("SET statement_timeout='20s'"))
        conn.execute(text(INDEX_DDL))
        valid = conn.execute(text('''SELECT indisvalid FROM pg_index
            WHERE indexrelid=to_regclass('idx_background_projection_retention')''')).scalar()
        if not valid:
            raise RuntimeError('retention_index_invalid')


def verify(engine):
    month = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m')
    reader = MonthReader(lambda: engine)
    first = reader.read(month, ('deployment_read_check',))
    second = reader.read(month, ('deployment_read_check',))
    # Only counts and coherence state are logged, never personnel records.
    if first['revision'] is None:
        raise RuntimeError('month_revision_not_enabled')
    return {'ok': True, 'month': month, 'records': len(second['records']),
            'revision_enabled': True, 'cache_entries': len(reader.cache._entries),
            'same_revision': first['revision'] == second['revision']}


if __name__ == '__main__':
    from vera_technical_retention import runtime_engine
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    engine = runtime_engine()
    try:
        if args.apply:
            migrate(engine)
        print(json.dumps(verify(engine)))
    except Exception as error:
        print(json.dumps({'ok': False, 'error_type': type(error).__name__}))
        raise SystemExit(1) from None
    finally:
        engine.dispose()

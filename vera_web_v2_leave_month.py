"""Month-scoped leave reads. Permissions are checked for every request."""
from datetime import date
import re
import json

from fastapi import Depends, HTTPException, Response
from sqlalchemy import text

from vera_read_cache import ReadCache, json_default

MONTH_ROWS = text('''
    SELECT record_uid,leave_date,weekday_label,employee_name,leave_reason,
           leave_type,detail,penalty,updated_by,updated_at
    FROM leave_records
    WHERE leave_date >= :start AND leave_date < :stop
    ORDER BY leave_date,employee_name,record_uid
''')


def month_bounds(month):
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month or ''):
        raise ValueError('Tháng phải có dạng YYYY-MM.')
    start = date.fromisoformat(month + '-01')
    return start, date(start.year + (start.month == 12), start.month % 12 + 1, 1)


def revision(conn, start):
    # Deployments can serve bounded uncached reads before the migration finishes.
    # No schema creation or writes on the HTTP read path.
    ready = conn.execute(text('''
        SELECT to_regclass('vera_leave_month_revision') IS NOT NULL
          AND (SELECT count(*) FROM pg_trigger
               WHERE tgrelid=to_regclass('leave_records') AND NOT tgisinternal
                 AND tgname IN ('vera_leave_month_insert','vera_leave_month_update',
                                'vera_leave_month_delete','vera_leave_month_truncate')
                 AND tgenabled IN ('O','A')) = 4
    ''')).scalar_one()
    if not ready:
        return None
    return conn.execute(text('''SELECT COALESCE(
        (SELECT version FROM vera_leave_month_revision WHERE month_start=:month),0)
    '''), {'month': start}).scalar_one()


class RevisionChanged(Exception):
    pass


class MonthReader:
    def __init__(self, engine_instance):
        self.engine_instance = engine_instance
        self.cache = ReadCache(ttl_seconds=15, max_entries=128, max_bytes=8*1024*1024)

    def read(self, month, scope, *, fresh=False):
        start, stop = month_bounds(month)
        def snapshot(expected=None):
            with self.engine_instance().connect().execution_options(isolation_level='REPEATABLE READ') as conn:
                conn.execute(text("SET LOCAL statement_timeout='5s'"))
                actual = revision(conn, start)
                if expected is not None and actual != expected:
                    raise RevisionChanged()
                result = {'month': month, 'revision': actual, 'records': [dict(row) for row in
                    conn.execute(MONTH_ROWS, {'start': start, 'stop': stop}).mappings()]}
                return json.loads(json.dumps(result, default=json_default))
        if fresh:
            return snapshot()
        for _ in range(3):
            with self.engine_instance().connect() as conn:
                version = revision(conn, start)
            if version is None:
                return snapshot()
            try:
                # Cache waits happen AFTER releasing the revision connection.
                # Transactional revisions cover every writer and every API process.
                return self.cache.get_or_load((scope, month, version), lambda: snapshot(version))
            except RevisionChanged:
                continue
        return snapshot()


def install_month_api(app, *, engine_instance, current_identity, require_feature, feature_allowed):
    if getattr(app.state, 'leave_month_installed', False):
        return
    reader = MonthReader(engine_instance)

    @app.get('/v2/leave/month-records')
    def month_records(response: Response, month: str,
                      start: date | None = None, end: date | None = None,
                      fresh: bool = False,
                      ident=Depends(current_identity)):
        try:
            first, stop = month_bounds(month)
        except (ValueError, OverflowError):
            raise HTTPException(400, 'Tháng không hợp lệ.') from None
        if ((start is not None and not first <= start < stop)
                or (end is not None and not first <= end < stop)
                or (start is not None and end is not None and end < start)):
            raise HTTPException(400, 'Bộ lọc phải nằm trong tháng đang xem.')
        with engine_instance().connect() as conn:
            require_feature(conn, ident, 'leave')
            can_penalty = bool(feature_allowed(conn, ident, 'employee_penalty_view'))
        response.headers['Cache-Control'] = 'private, no-store'
        scope = (ident.employee_username, ident.role, can_penalty)
        result = reader.read(month, scope, fresh=fresh)
        # A private copy from ReadCache: redaction never mutates another reader.
        records = [row for row in result['records']
                   if (start is None or row['leave_date'] >= start.isoformat())
                   and (end is None or row['leave_date'] <= end.isoformat())]
        if not can_penalty:
            for row in records:
                row.pop('penalty', None)
        return {**result, 'records': records}

    app.state.leave_month_reader = reader
    app.state.leave_month_installed = True

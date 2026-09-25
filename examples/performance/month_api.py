"""Opt-in example: install explicitly; existing production routes are unchanged."""
from datetime import date
import re
from fastapi import Depends, HTTPException, Query, Response
from sqlalchemy import text
from examples.performance.read_cache import ReadCache

MONTH_ROWS = text("""
    SELECT record_uid,leave_date,weekday_label,employee_name,leave_reason,
           leave_type,detail,penalty,updated_by,updated_at
    FROM leave_records
    WHERE leave_date >= :start AND leave_date < :stop
      AND (:employee = '' OR employee_name = :employee)
    ORDER BY leave_date,employee_name,record_uid
    LIMIT :limit OFFSET :offset
""")


def month_bounds(month):
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month or ''):
        raise ValueError('Tháng phải có dạng YYYY-MM')
    start = date.fromisoformat(month+'-01')
    stop = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, stop


def install_month_api(app, *, engine_instance, current_identity, require_feature, feature_allowed):
    cache = ReadCache(ttl_seconds=5)

    @app.get('/v2/leave/month-records')
    def month_records(response: Response, month: str,
                      employee: str = Query(default='', max_length=200),
                      page: int = Query(default=1, ge=1),
                      page_size: int = Query(default=50, ge=1, le=100),
                      fresh: bool = False, ident=Depends(current_identity)):
        try:
            start, stop = month_bounds(month)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        # Authenticate on EVERY request; do not reuse a cached session or role.
        with engine_instance().connect() as conn:
            require_feature(conn, ident, 'leave')
            can_penalty = feature_allowed(conn, ident, 'employee_penalty_view')
        response.headers['Cache-Control'] = 'private, no-store'
        if fresh:
            cache.invalidate()
        def load():
            with engine_instance().connect() as conn:
                rows = conn.execute(MONTH_ROWS, {'start':start,'stop':stop,'employee':employee,
                    'limit':page_size+1,'offset':(page-1)*page_size}).mappings().all()
            records = [dict(row) for row in rows[:page_size]]
            if not can_penalty:
                for record in records:
                    record.pop('penalty', None)
            return {'month':month,'records':records,'page':page,'has_more':len(rows)>page_size}
        # Scope caches by caller and current effective visibility grants.
        key = (ident.employee_username, ident.role, bool(can_penalty),month,employee,page,page_size)
        return cache.get_or_load(key, load)

    # Integrate into EVERY create/update/delete/import success path after commit:
    # with engine_instance().begin() as conn: ... canonical write ...
    # cache.invalidate()
    # Do not invalidate before commit or cache quota/payment decisions.
    return cache.invalidate

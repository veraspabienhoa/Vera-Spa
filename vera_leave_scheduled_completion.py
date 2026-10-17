"""Complete approved requests at their scheduled Vietnam boundary, without a punch."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import json
import logging
from sqlalchemy import text

VN = ZoneInfo('Asia/Ho_Chi_Minh')


def completion_payload(row, now):
    from vera_web_v2_long_leave import (REQUEST_TYPE_ANNUAL, REQUEST_TYPE_RESIGNATION,
        STATUS_APPROVED, _parse_vn_date, _payload_value)
    payload = _payload_value(row.get('payload'))
    kind = row.get('record_type') or payload.get('Loại đơn')
    if row.get('record_status') != STATUS_APPROVED or kind not in {REQUEST_TYPE_ANNUAL, REQUEST_TYPE_RESIGNATION}:
        return None
    if payload.get('Trạng thái kỳ nghỉ') == 'Đã kết thúc':
        return None
    first = _parse_vn_date(row.get('date_from') or payload.get('Từ ngày'))
    last = _parse_vn_date(row.get('date_to') or payload.get('Đến ngày'))
    if not first or not last or last < first:
        return None
    day = last + timedelta(days=1) if kind == REQUEST_TYPE_ANNUAL else first
    boundary = datetime.combine(day, time.min, tzinfo=VN)
    if now.astimezone(VN) < boundary:
        return None
    payload.update({'Trạng thái kỳ nghỉ': 'Đã kết thúc', 'Nguồn kết thúc kỳ nghỉ': 'scheduled',
                    'Kết thúc lúc': boundary.isoformat(), 'Người cập nhật': 'Hệ thống',
                    'Cập nhật lúc': now.astimezone(VN).strftime('%d/%m/%Y %H:%M:%S')})
    # Do not fabricate a return-to-work punch or reactivate a resigned employee.
    return payload


def complete_due(conn, now=None):
    from vera_web_v2_long_leave import LONG_LEAVE_DATASET, REQUEST_TYPE_ANNUAL, REQUEST_TYPE_RESIGNATION, STATUS_APPROVED
    now = now or datetime.now(VN)
    conn.execute(text("SET LOCAL lock_timeout = '5s'"))
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase14:long_leave'))"))
    rows = conn.execute(text('''SELECT logical_id,record_type,record_status,date_from,date_to,payload
        FROM vera_phase14_record WHERE dataset=:dataset AND record_status=:approved
        AND record_type IN (:annual,:resignation)
        AND COALESCE(payload->>'Trạng thái kỳ nghỉ','') <> 'Đã kết thúc'
        ORDER BY logical_id FOR UPDATE'''), {'dataset': LONG_LEAVE_DATASET, 'approved': STATUS_APPROVED,
        'annual': REQUEST_TYPE_ANNUAL, 'resignation': REQUEST_TYPE_RESIGNATION}).mappings().all()
    changed = 0
    for row in rows:
        payload = completion_payload(row, now)
        if payload is None:
            continue
        conn.execute(text('''UPDATE vera_phase14_record SET payload=CAST(:payload AS jsonb),
            updated_by='Hệ thống',revision=revision+1,updated_at=NOW()
            WHERE dataset=:dataset AND logical_id=:id'''),
            {'payload': json.dumps(payload, ensure_ascii=False), 'dataset': LONG_LEAVE_DATASET, 'id': row['logical_id']})
        changed += 1
    return changed


def monitor(engine_instance, stop, *, initial_delay=5, interval=60):
    if stop.wait(initial_delay):
        return
    while not stop.is_set():
        try:
            with engine_instance().begin() as conn:
                complete_due(conn)
        except Exception as error:
            logging.getLogger(__name__).warning('Scheduled leave completion deferred: %s', type(error).__name__)
        if stop.wait(interval):
            return


def install(app, engine_instance):
    from vera_worker_runtime import register_worker
    if getattr(app.state, 'leave_completion_installed', False):
        return
    register_worker(app, engine_instance=engine_instance, name='leave-completion-monitor',
                    target=lambda stop: monitor(engine_instance, stop), stale_after=180)
    app.state.leave_completion_installed = True

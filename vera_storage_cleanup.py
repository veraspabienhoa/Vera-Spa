"""Explicit retention targets. Never infer deletable tables from the schema.

Counts describe physical records, including independent payroll/cache copies.
All selected targets are checked and deleted on the caller's transaction.
"""
from datetime import date, datetime
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import text

LABELS = {'leave': 'Lịch nghỉ', 'payroll': 'Bảng lương',
          'attendance': 'Chấm công / Face ID', 'purchases': 'Nhập mua',
          'revenue': 'Thu Chi nhập thủ công'}
# Names and SQL expressions are constants, never supplied by a client.
TABLES = {
    'leave': [('leave_records', 'leave_date')],
    'payroll': [('payroll_history_rows', 'COALESCE(period_end, period_start)')],
    'attendance': [('vera_facegate_event', 'work_date'),
                   ('vera_facegate_event_conflict', 'work_date'),
                   ('vera_facegate_sync_day', 'work_date'),
                   ('vera_mobile_station_event', "(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")],
    'purchases': [('vera_purchase_entry', 'purchase_date')],
    'revenue': [('vera_revenue_entry', 'transaction_date')],
}


def selected(dataset):
    if dataset == 'all':
        return sorted(LABELS)
    if dataset not in LABELS:
        raise HTTPException(400, 'Nhóm dữ liệu không hợp lệ.')
    return [dataset]


def validate_scope(scope, start, end):
    if scope not in {'range', 'all_time'}:
        raise HTTPException(400, 'Phạm vi không hợp lệ.')
    if scope == 'range' and (not start or not end or end < start):
        raise HTTPException(400, 'Chọn đủ khoảng ngày hợp lệ.')


def parsed_day(value):
    raw = str(value or '').strip()[:10]
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def matches(item, dataset, scope, start, end):
    if scope == 'all_time':
        return True
    keys = ('Đến ngày', 'Ngày lưu', 'Từ ngày') if dataset == 'payroll' else ('WorkDateStr',)
    day = next((day for key in keys if (day := parsed_day(item.get(key)))), None) if isinstance(item, dict) else None
    return day is not None and start <= day <= end


def exists(conn, table):
    return conn.execute(text('SELECT to_regclass(:name)'), {'name': table}).scalar_one_or_none() is not None


def predicate(expression, scope):
    if scope == 'all_time':
        return 'TRUE'
    # FaceGate work_date is an ISO text column; do not cast malformed rows.
    if expression == 'work_date':
        return 'work_date BETWEEN CAST(:start AS text) AND CAST(:end AS text)'
    return f'{expression} BETWEEN :start AND :end'


def cache_filter(dataset):
    return ("dataset_key='payroll_history'" if dataset == 'payroll' else
            "(dataset_key='timesoft_employee_checkin_today' OR dataset_key LIKE 'timesoft_employee_checkin_20%')")


def snapshot(conn, dataset, scope, start=None, end=None, *, lock=False):
    validate_scope(scope, start, end)
    wanted = selected(dataset)
    tables = [(group, table, expr) for group in wanted for table, expr in TABLES[group] if exists(conn, table)]
    cache = exists(conn, 'vera_dataset_cache') and any(g in wanted for g in ('payroll', 'attendance'))
    # Table locks also exclude concurrent INSERTs, unlike row locks alone.
    if lock:
        targets = sorted({t for _, t, _ in tables} | ({'vera_dataset_cache'} if cache else set()))
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        for table in targets:
            conn.execute(text(f'LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE'))
    counts = {group: 0 for group in wanted}
    parts = []
    params = {'start': start, 'end': end}
    for group, table, expr in tables:
        encoded = list(conn.execute(text(f'SELECT md5(row_to_json(t)::text) AS fingerprint FROM {table} t WHERE {predicate(expr, scope)} ORDER BY fingerprint'), params).scalars())
        counts[group] += len(encoded)
        parts.append((table, encoded))
    if cache:
        for group in ('payroll', 'attendance'):
            if group not in wanted:
                continue
            rows = conn.execute(text(f'SELECT dataset_key,payload FROM vera_dataset_cache WHERE {cache_filter(group)} ORDER BY dataset_key')).mappings().all()
            for row in rows:
                payload = row['payload']
                if not isinstance(payload, list):
                    raise HTTPException(409, 'Dữ liệu lưu trữ không đúng định dạng; chưa thể xóa an toàn.')
                items = [item for item in payload if matches(item, group, scope, start, end)]
                counts[group] += len(items)
                parts.append((row['dataset_key'], items))
    digest = hashlib.sha256(json.dumps([dataset, scope, str(start), str(end), parts], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return {'counts': counts, 'total': sum(counts.values()), 'fingerprint': digest,
            'dataset': dataset, 'scope': scope, 'start': start, 'end': end,
            'tables': [table for _, table, _ in tables], 'has_cache': cache}


def delete_checked(conn, dataset, scope, start, end, expected_count, fingerprint):
    current = snapshot(conn, dataset, scope, start, end, lock=True)
    if current['total'] != expected_count or current['fingerprint'] != fingerprint:
        raise HTTPException(409, 'Dữ liệu đã thay đổi. Hãy xem trước lại trước khi xóa.')
    params = {'start': start, 'end': end}
    for group in selected(dataset):
        for table, expr in TABLES[group]:
            if table in current['tables']:
                conn.execute(text(f'DELETE FROM {table} WHERE {predicate(expr, scope)}'), params)
        if group not in {'payroll', 'attendance'} or not current['has_cache']:
            continue
        rows = conn.execute(text(f'SELECT dataset_key,payload FROM vera_dataset_cache WHERE {cache_filter(group)}')).mappings().all()
        for row in rows:
            retained = [item for item in row['payload'] if not matches(item, group, scope, start, end)]
            encoded = json.dumps(retained, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
            conn.execute(text('''UPDATE vera_dataset_cache SET payload=CAST(:payload AS jsonb),
                row_count=:count,checksum=:checksum,source_version='web-v2-retention',updated_at=NOW()
                WHERE dataset_key=:key'''), {'key': row['dataset_key'], 'payload': encoded,
                'count': len(retained), 'checksum': hashlib.sha256(encoded.encode()).hexdigest()})
    return current

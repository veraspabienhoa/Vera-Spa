"""One dated report shared by Manual and Auto, without copying financial rows."""
from datetime import date
import json

from fastapi import HTTPException
from sqlalchemy import text
import vera_revenue_auto as source

VERSION = 1
PERIOD_KEY = 'shared_report_period'


def resolve_period(conn, start=None, end=None):
    today = source.datetime.now(source.VN_TZ).date()
    if (start is None) != (end is None):
        raise HTTPException(400, 'Chọn đủ Từ ngày tính TIP và Đến ngày.')
    if start is None:
        saved = conn.execute(text("""SELECT value_json FROM vera_app_setting
            WHERE category='revenue' AND setting_key IN
              ('shared_report_period','current_period_tip','current_period_tip_auto')
            ORDER BY CASE WHEN setting_key='shared_report_period' THEN 0 ELSE 1 END,
              updated_at DESC NULLS LAST LIMIT 1""")).scalar_one_or_none() or {}
        try:
            start = date.fromisoformat(str(saved.get('period_start', '')))
            end = date.fromisoformat(str(saved.get('period_end', '')))
        except (ValueError, TypeError, AttributeError):
            start, end = today.replace(day=1 if today.day <= 15 else 16), today
        start, end = max(start, source.START_DATE), min(end, today)
    if not source.START_DATE <= start <= end <= today:
        raise HTTPException(400, 'Kỳ báo cáo/TIP phải từ 05-09-2025 đến hôm nay và Từ ngày không sau Đến ngày.')
    return start, end


def snapshot(conn, start=None, end=None):
    """Caller owns one REPEATABLE READ connection for settings, money and TIP."""
    start, end = resolve_period(conn, start, end)
    shared = source.mode(conn)
    totals = source.totals(source.daily(conn, source.START_DATE, end, include_entries=False))
    tip = round(source.tip_total(conn, start, end, auto=True), 2)
    today = source.datetime.now(source.VN_TZ).date()
    return {
        'ok': True, 'report_version': VERSION, 'report_basis': 'shared_history_and_system',
        'source': shared['source'], 'source_revision': shared['revision'],
        **totals, 'period_tip': tip, 'balance': round(totals['net_income'] - tip, 2),
        'period_tip_start': start.isoformat(), 'period_tip_end': end.isoformat(),
        'start_date': source.START_DATE.isoformat(), 'start_date_label': source.START_DATE.strftime('%d-%m-%Y'),
        'end_date': end.isoformat(), 'end_date_label': end.strftime('%d-%m-%Y'),
        'current_date': today.isoformat(), 'current_date_label': today.strftime('%d-%m-%Y'),
        'business_date': today.isoformat(), 'storage': 'postgresql',
    }


def save_period(conn, result, actor):
    value = json.dumps({'period_start': result['period_tip_start'], 'period_end': result['period_tip_end']})
    conn.execute(text("""INSERT INTO vera_app_setting
        (category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
        VALUES ('revenue',:key,CAST(:value AS jsonb),'web_v2',:actor,1,NOW(),NOW())
        ON CONFLICT(category,setting_key) DO UPDATE SET value_json=EXCLUDED.value_json,
        updated_by=EXCLUDED.updated_by,updated_at=NOW(),revision=vera_app_setting.revision+1"""),
        {'key': PERIOD_KEY, 'value': value, 'actor': actor})


def ledger_rows(conn, start, end, *, editable_history=False):
    rows = source.ledger_rows(source.daily(conn, start, end))
    if editable_history:
        for row in rows:
            if row.get('source') == 'manual_history':
                row['id'] = row['source_entry_id']
                row['read_only'] = False
    return rows

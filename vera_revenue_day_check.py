"""Read-only daily revenue reconciliation, run locally on the VPS by an operator.

Print only dates, counts and money totals. Never import the API, change source
rows, send notifications or expose credentials/customer details.
"""
import argparse
from datetime import date
import json
import os
import signal

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import vera_revenue_auto as revenue


def summarize_day(conn, day):
    # Caller owns a single read-only REPEATABLE READ snapshot.
    days = revenue.daily(conn, day, day, include_entries=False)
    auto = revenue.totals(days)
    manual = conn.execute(text("""SELECT
        COUNT(*) AS rows,
        COALESCE(SUM(amount) FILTER (WHERE transaction_type='Thu'),0) AS income,
        COALESCE(SUM(amount) FILTER (WHERE transaction_type='Chi'),0) AS expense
        FROM vera_revenue_entry WHERE NOT is_deleted
        AND COALESCE(transaction_date,(entered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)=:day
    """), {'day': day}).mappings().one()
    invoices = conn.execute(text("""SELECT COUNT(*) AS count,
        COALESCE(SUM(total),0) AS total, COALESCE(SUM(tip),0) AS tip
        FROM (SELECT
            (CASE WHEN event_at ~ '(Z|[+-][0-9]{2}:?[0-9]{2})$'
              THEN event_at::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh'
              ELSE event_at::timestamp END)::date AS invoice_day,
            COALESCE(NULLIF(payload->>'total','')::numeric,0) AS total,
            COALESCE(NULLIF(payload->>'tip','')::numeric,0) AS tip
          FROM (SELECT payload,
              COALESCE(NULLIF(payload->>'effective_at',''),NULLIF(payload->>'business_date','')) AS event_at
            FROM vera_live_tour_invoice WHERE deleted_at IS NULL) active
        ) dated WHERE invoice_day=:day
    """), {'day': day}).mappings().one()
    return {
        'ok': True, 'date': day.strftime('%d-%m-%Y'),
        'date_basis': 'Ngay gio hoa don (Asia/Ho_Chi_Minh)',
        'manual': {'rows': manual['rows'], 'income': float(manual['income']), 'expense': float(manual['expense'])},
        'auto': {'income': auto['total_income'], 'expense': auto['total_expense'],
                 'service': auto['service_revenue'], 'tip': auto['tip_revenue'],
                 'report_rows': sum(row['payments'] for row in days),
                 'purchase_rows': sum(row['purchases'] for row in days)},
        'paid_invoices': {'count': invoices['count'], 'total': float(invoices['total']), 'tip': float(invoices['tip'])},
        'invoice_report_difference': round(float(invoices['total']) - auto['total_income'], 2),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if not revenue.START_DATE <= args.date <= revenue.datetime.now(revenue.VN_TZ).date():
        parser.error('Date must be between 2025-09-05 and today in Vietnam.')
    engine = None

    def deadline(*_):
        raise TimeoutError('deadline')

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(25)
    try:
        from vera_vps_data_check import _database_url, _running_api_environment
        from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
        environment = ({key: os.environ.get(key, '') for key in RUNTIME_ENV_KEYS}
                       if load_managed_runtime_environment() else _running_api_environment())
        sslmode = environment.get('DB_SSLMODE', 'require')
        if sslmode not in {'require', 'verify-ca', 'verify-full'}:
            sslmode = 'require'
        engine = create_engine(_database_url(environment), poolclass=NullPool,
            isolation_level='REPEATABLE READ', connect_args={
                'connect_timeout': 5, 'sslmode': sslmode, 'application_name': 'vera-revenue-day-check',
                'options': '-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000'})
        with engine.connect() as conn:
            result = summarize_day(conn, args.date)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__}))
        raise SystemExit(1) from None
    finally:
        signal.alarm(0)
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    main()

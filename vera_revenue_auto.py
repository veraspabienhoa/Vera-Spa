"""Shared Revenue mode and read-only daily cash ledger; never rewrite source money."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import hashlib

from fastapi import HTTPException
from sqlalchemy import text

START_DATE = date(2025, 9, 5)
VN_TZ = timezone(timedelta(hours=7))
MODE_KEY = "shared_source"
MODES = {"manual", "auto", "manual_tip_auto"}


def mode(conn):
    row = conn.execute(text("""SELECT value_json, revision FROM vera_app_setting
        WHERE category='revenue' AND setting_key=:key"""), {"key": MODE_KEY}).mappings().first()
    value = (row["value_json"] or {}).get("source", "manual") if row else "manual"
    if value not in MODES:
        raise HTTPException(503, "Cấu hình Doanh thu không hợp lệ. Admin cần kiểm tra lại.")
    return {"source": value, "revision": int(row["revision"]) if row else 0}


def lock_mode(conn):
    # All mode changes and Manual writes share this short transaction lock.
    # A failed try does not hold a pool connection waiting behind an import.
    if not conn.execute(text("SELECT pg_try_advisory_xact_lock(726401, 92601)")).scalar():
        raise HTTPException(409, "Doanh thu đang được lưu. Vui lòng thử lại sau khi tác vụ hoàn tất.")


def require_manual(conn):
    lock_mode(conn)
    if mode(conn)["source"] == "auto":
        raise HTTPException(409, "Auto đang bật cho toàn hệ thống. Chức năng nhập, sửa, xóa và import Manual đã khóa.")


def set_mode(conn, source, expected_revision, actor):
    lock_mode(conn)
    current = mode(conn)
    if current["revision"] != expected_revision:
        raise HTTPException(409, "Chế độ Doanh thu đã thay đổi. Hãy tải lại trước khi chọn lại.")
    if source == "auto":
        if not conn.execute(text("SELECT to_regclass('vera_live_tour_report')")).scalar():
            raise HTTPException(409, "Dữ liệu thanh toán Live Tour chưa sẵn sàng trên server.")
        from vera_purchase_store import ensure_schema
        ensure_schema(conn)
    if current["source"] == source:
        return current
    conn.execute(text("""INSERT INTO vera_app_setting
        (category, setting_key, value_json, source, updated_by, revision, created_at, updated_at)
        VALUES ('revenue', :key, CAST(:value AS jsonb), 'web_v2', :actor, 1, NOW(), NOW())
        ON CONFLICT(category, setting_key) DO UPDATE SET value_json=EXCLUDED.value_json,
        updated_by=EXCLUDED.updated_by, source='web_v2',
        revision=vera_app_setting.revision+1, updated_at=NOW()"""),
        {"key": MODE_KEY, "value": json.dumps({"source": source}), "actor": actor})
    return mode(conn)


def bounds(start=None, end=None):
    return max(start or START_DATE, START_DATE), min(end or datetime.now(VN_TZ).date(), datetime.now(VN_TZ).date())


# Report rows allocate actual invoice total and TIP once across employees.
# Using subtotal would omit discounts and double-count prepaid combo services.
# Match the displayed Invoice date/time column exactly: effective_at or business_date.
# Zone-less legacy timestamps are Vietnam local time, independent of DB timezone.
REPORT_DAILY_SQL = """
    SELECT report_day AS day, SUM(total - tip) AS service, SUM(tip) AS tip,
           SUM(total) AS income, COUNT(*) AS payments
    FROM (
      SELECT (CASE WHEN event_at ~ '(Z|[+-][0-9]{2}:?[0-9]{2})$'
                   THEN event_at::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh'
                   ELSE event_at::timestamp END)::date AS report_day, total, tip
      FROM (
        SELECT COALESCE(NULLIF(payload->>'effective_at',''), NULLIF(payload->>'business_date','')) AS event_at,
        COALESCE(NULLIF(payload->>'total','')::numeric,
          GREATEST(0, COALESCE(NULLIF(payload->>'subtotal','')::numeric,
                              NULLIF(payload->>'service_money','')::numeric, 0)
                      - COALESCE(NULLIF(payload->>'discount','')::numeric, 0))
          + COALESCE(NULLIF(payload->>'tip','')::numeric, 0)) AS total,
        COALESCE(NULLIF(payload->>'tip','')::numeric, 0) AS tip
      FROM vera_live_tour_report
      WHERE deleted_at IS NULL
      ) events
    ) reports
    WHERE report_day BETWEEN :start AND :end
    GROUP BY report_day
"""


def _params(start, end):
    return {"start": start, "end": end, "start_text": start.isoformat(), "end_text": end.isoformat()}


def daily(conn, start=None, end=None, *, include_entries=True):
    """Auto is independent: paid Live Tour income and authoritative purchases only."""
    start, end = bounds(start, end)
    if start > end:
        return []
    return conn.execute(text(f"""WITH receipts AS ({REPORT_DAILY_SQL}), purchases AS (
        SELECT purchase_date AS day, SUM(amount) AS expense, COUNT(*) AS purchases
        FROM vera_purchase_entry WHERE NOT deleted AND purchase_date BETWEEN :start AND :end
        GROUP BY purchase_date
      ) SELECT COALESCE(r.day, p.day) AS day,
        COALESCE(service,0) AS service, COALESCE(tip,0) AS tip,
        COALESCE(income,0) AS income, COALESCE(expense,0) AS expense,
        COALESCE(payments,0) AS payments, COALESCE(purchases,0) AS purchases,
        0::numeric AS historical_income, NULL::jsonb AS history_entries
      FROM receipts r FULL JOIN purchases p ON p.day=r.day ORDER BY day DESC
    """), _params(start,end)).mappings().all()


def tip_total(conn, start, end, *, auto=False):
    if auto:
        start, end = bounds(start, end)
    if start > end:
        return 0.0
    return float(conn.execute(text(f"SELECT COALESCE(SUM(tip), 0) FROM ({REPORT_DAILY_SQL}) days"),
                              _params(start, end)).scalar())


def ledger_rows(days):
    rows = []
    for day in days:
        date_value = day["day"]
        if day.get("history_entries") is not None:
            for item in day["history_entries"]:
                entered = datetime.fromisoformat(item["entered_at"]).astimezone(VN_TZ) if item.get("entered_at") else None
                rows.append({"id": f"history:{item['id']}", "source": "manual_history",
                    "source_entry_id": item["id"], "date": date_value.isoformat(),
                    "date_label": date_value.strftime("%d-%m-%Y"), "type": item["type"],
                    "amount": float(item["amount"]), "note": item["note"],
                    "entered_date": entered.date().isoformat() if entered else "",
                    "entered_date_label": entered.strftime("%d-%m-%Y") if entered else "",
                    "entered_time": entered.strftime("%H:%M:%S") if entered else "",
                    "entered_by": item["entered_by"], "read_only": True})
            continue
        for kind, amount, count, note in (
            ("Thu", day["income"], day["payments"], "Doanh thu dịch vụ + TIP"),
            ("Chi", day["expense"], day["purchases"], "Mua hàng · Nhập mua"),
        ):
            if not count:
                continue
            rows.append({"id": f"auto:{date_value.isoformat()}:{kind}",
                "date": date_value.isoformat(), "date_label": date_value.strftime("%d-%m-%Y"),
                "type": kind, "amount": float(amount), "note": note,
                "entered_date": "", "entered_date_label": "", "entered_time": "",
                "entered_by": "Tự động hệ thống", "is_purchase": kind == "Chi", "read_only": True})
    return rows


def totals(days):
    def total(key):
        return float(sum((Decimal(str(day[key])) for day in days), Decimal(0)))
    income, expense = total("income"), total("expense")
    return {"service_revenue": total("service"), "tip_revenue": total("tip"),
            "historical_income": float(sum(Decimal(str(day.get("historical_income", 0))) for day in days)),
            "total_revenue": income, "total_income": income, "total_expense": expense,
            "net_income": round(income - expense, 2)}


def change_revision(conn):
    # Read counters only; a poll never reloads the historical ledger or JSON bills.
    row = conn.execute(text("""SELECT
        (SELECT concat(COUNT(*),':',COALESCE(MAX(aggregate_revision),0),':',COUNT(deleted_at))
         FROM vera_live_tour_report) AS reports,
        (SELECT concat(COUNT(*),':',COALESCE(MAX(id),0),':',COALESCE(SUM(revision),0),':',COUNT(*) FILTER (WHERE deleted))
         FROM vera_purchase_entry) AS purchases,
        (SELECT concat(COUNT(*),':',COALESCE(MAX(id),0),':',COALESCE(SUM(edit_revision),0),':',COUNT(*) FILTER (WHERE is_deleted))
         FROM vera_revenue_entry) AS history,
        (SELECT COALESCE(SUM(revision),0) FROM vera_app_setting WHERE category='revenue') AS settings
    """)).mappings().one()
    value = json.dumps([dict(row), datetime.now(VN_TZ).date().isoformat()], sort_keys=True, default=str)
    return hashlib.sha256(value.encode()).hexdigest()


def purchase_rows(conn, start, end):
    from vera_purchase_store import report_rows
    return report_rows(conn, start, end)

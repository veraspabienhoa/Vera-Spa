from contextlib import contextmanager
from datetime import date, datetime, timezone
import json

import pytest
from sqlalchemy import text

import vera_leave_quota_alerts as alerts
import vera_notification_delivery as delivery
import vera_notification_periods as periods
from test_leave_month_postgres import database


def test_vietnam_month_rollover(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(periods, 'datetime', Clock)
    assert periods.current_month() == '2026-10'


@pytest.mark.parametrize('payload', [
    {'quota_month': '2026-08'}, {'month': '2026-10'},
    {'body': 'Synthetic · 2026-08: vượt hạn mức đăng ký nghỉ.'}, {},
])
def test_expired_unknown_or_future_quota_never_enters_any_channel(monkeypatch, payload):
    monkeypatch.setattr(delivery, 'current_month', lambda: '2026-09')
    class NoDatabase:
        def execute(self, *args, **kwargs):
            raise AssertionError('Expired notice must not enqueue or fall back')
    assert delivery.enqueue(NoDatabase(), 'leave_quota_exceeded', payload)


def test_scan_activates_only_current_month_but_preserves_manual_historical_report(database, monkeypatch):
    monkeypatch.setattr(alerts, 'current_month', lambda: '2026-09')
    monkeypatch.setattr(alerts.settings, 'is_enabled', lambda *args: False)
    with database.begin() as conn:
        conn.execute(text('ALTER TABLE leave_records ADD COLUMN calculated_days numeric'))
        for month in ['08', '09', '10']:
            conn.execute(text('''INSERT INTO leave_records(record_uid,employee_name,leave_date,leave_reason,leave_type,calculated_days)
                VALUES(:uid,'Synthetic',:day,'Nghỉ CÓ phép','Có phép',6)'''),
                {'uid': month, 'day': date.fromisoformat(f'2026-{month}-01')})
        alerts.ensure_schema(conn)
        conn.execute(text("INSERT INTO vera_leave_quota_alert(fingerprint,payload) VALUES('legacy',CAST(:payload AS jsonb))"),
            {'payload': json.dumps({'month': '2026-08'})})
    alerts.scan(database)
    with database.begin() as conn:
        months = list(conn.execute(text("SELECT payload->>'month' FROM vera_leave_quota_alert WHERE active")).scalars())
        assert months == ['2026-09']
        manual = alerts.read_report(conn, date(2026, 8, 1), date(2026, 8, 31))
        assert [item['month'] for item in manual] == ['2026-08']


def test_sql_scope_hides_legacy_and_future_quota_for_all_feed_and_push_paths(database):
    # Use PostgreSQL's own Vietnam month to cover production SQL timezone rules.
    with database.begin() as conn:
        month = conn.execute(text("SELECT to_char(NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh','YYYY-MM')")).scalar_one()
        cases = [
            ('leave_quota_exceeded', {'quota_month': month}, True),
            ('leave_quota_exceeded', {'body': f'Synthetic · {month}: vượt hạn mức'}, True),
            ('leave_quota_exceeded', {'quota_month': '2000-01'}, False),
            ('leave_quota_exceeded', {'body': 'Synthetic · 2000-01: vượt hạn mức'}, False),
            ('leave_quota_exceeded', {'quota_month': '2099-12'}, False),
            ('birthday', {}, True),
        ]
        for source, payload, expected in cases:
            value = conn.execute(text('SELECT '+periods.current_quota_sql(':source', 'CAST(:payload AS jsonb)')),
                {'source': source, 'payload': json.dumps(payload)}).scalar_one()
            assert value is expected


def test_queued_push_rechecks_period_before_contacting_device(database, monkeypatch):
    from test_notification_routing import Result
    payload = {'kind': 'leave_quota_exceeded', 'body': 'Synthetic · 2000-01: vượt hạn mức'}
    checked = []
    class Engine:
        @contextmanager
        def begin(self): yield self
        @contextmanager
        def connect(self): yield self
        def execute(self, sql, params=None):
            sql = str(sql)
            if 'WITH pending AS' in sql:
                return Result([{'id': 1, 'rule_key': 'quota', 'recipient': 'test', 'payload': payload}])
            if 'SELECT 1 FROM vera_notification_route' in sql:
                assert "Asia/Ho_Chi_Minh" in sql and "quota_month" in sql
                with database.begin() as conn:
                    allowed = conn.execute(text('SELECT '+periods.current_quota_sql(':source', 'CAST(:payload AS jsonb)')),
                        {'source': 'leave_quota_exceeded', 'payload': params['payload']}).scalar_one()
                checked.append(allowed)
                return Result(scalar=1 if allowed else None)
            if 'UPDATE vera_notification_delivery SET claimed_at=NULL' in sql:
                assert params['complete'] is True
            return Result()
    def forbidden(*args): raise AssertionError('Expired quota must never reach Web Push')
    monkeypatch.setattr(delivery, 'ensure_schema', lambda conn: None)
    delivery.dispatch_pending(Engine(), forbidden, forbidden)
    assert checked == [False]

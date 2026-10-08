"""Archived punches remove popup alerts before the cache is published."""
from datetime import datetime, time, timedelta
from types import SimpleNamespace

from sqlalchemy import event as sql_event, text

import vera_attendance_source as source
import vera_facegate_sync as sync
import vera_missing_checkin_notifications as alerts
from vera_facegate_control_log import VN_TZ
from test_facegate_attendance import DAY, ADDRESS, REF
from test_facegate_attendance_postgres import database


def test_popup_reads_committed_archive_with_one_readonly_connection(database, monkeypatch):
    monkeypatch.setattr(source, 'source_for', lambda day: 'facegate')
    monkeypatch.setattr(alerts, '_manual_shift_overrides', lambda conn, day: {})
    now = datetime.combine(DAY, time(15, 0, 10), tzinfo=VN_TZ)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE leave_records(employee_name text, leave_date date, source_sheet_id text, leave_reason text)'))
        conn.execute(text("INSERT INTO leave_records VALUES ('Ánh Thử',:day,'manual','Đi trễ CÓ phép')"), {'day': DAY})
        sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), [])
        conn.execute(text('UPDATE vera_facegate_sync_day SET last_synced_at=:at'),
                     {'at': (now-timedelta(seconds=20)).isoformat()})

    ident = SimpleNamespace(role='admin', employee_username='Admin')
    def read():
        with database.begin() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            def no_checkout(*args): raise AssertionError('nested connection')
            sql_event.listen(database, 'checkout', no_checkout)
            try:
                return alerts.current_missing_checkins(conn, ident, now)
            finally:
                sql_event.remove(database, 'checkout', no_checkout)

    # A pre-15:00 sync cannot prove absence after the permitted late arrival.
    assert read() == []
    with database.begin() as conn:
        conn.execute(text('UPDATE vera_facegate_sync_day SET last_synced_at=:at'), {'at': now.isoformat()})
    assert len(read()) == 1
    batch = sync.prepare_batch({'source': 'facegate_control_log', 'total_count': 2, 'truncated': False,
        'records': [{'event_id': i, 'occurred_at': f'{DAY}T14:59:{second}+07:00',
                     'device_name': 'ANH THU', 'status_code': '1', 'type_code': '0',
                     'registration_ref': REF} for i, second in [(1, 40), (2, 42)]]}, DAY.isoformat(), ADDRESS)
    with database.begin() as conn:
        sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), batch)
        conn.execute(text('UPDATE vera_facegate_sync_day SET last_synced_at=:at'), {'at': now.isoformat()})
        assert conn.execute(text('SELECT COUNT(*) FROM vera_dataset_cache')).scalar_one() == 0
    assert read() == []

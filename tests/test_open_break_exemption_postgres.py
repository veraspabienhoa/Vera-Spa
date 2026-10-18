"""Real transaction coverage; CI supplies isolated PostgreSQL."""
from datetime import date, datetime
from types import SimpleNamespace
from sqlalchemy import text
from test_live_tour_resource_postgres import database
import vera_open_break_exemption as rule
import vera_postgres_job_queue as queue


def test_manual_registration_revokes_only_matching_auto_fine_atomically(database, monkeypatch):
    import vera_facegate_runtime as runtime
    import vera_holiday_leave as holiday
    day = date(2026, 10, 18)
    monkeypatch.setattr(rule, '_now', lambda: datetime(2026, 10, 18, 16, tzinfo=rule.VN_TZ))
    monkeypatch.setattr(runtime, 'records', lambda conn, *a: [{
        'employee_name': 'Synthetic', 'shift': 'Ca 2', 'break_out': '15:00:00', 'break_in': '',
        'punch_datetimes': ['2026-10-18T13:00:00', '2026-10-18T15:00:00'],
        'evidence_source': 'facegate', 'attendance_fine_evidence_ready': True}])
    monkeypatch.setattr(holiday, 'approved_day', lambda *a: False)
    with database.begin() as conn:
        queue.ensure_schema_conn(conn)
        conn.execute(text('''CREATE TABLE leave_records(record_uid text,employee_name text,leave_date date,
            leave_reason text,source_sheet_id text,detail text,updated_by text,payload jsonb,created_at timestamptz)'''))
        conn.execute(text('''CREATE TABLE vera_auto_check_event(id int,work_date date,employee_name text,
            reason text,source text,status text,detail text,leave_record_uid text,employee_notify_claimed_at timestamptz)'''))
        for uid, reason, source, detail in [
            ('manual', 'Về sớm KHÔNG phép', 'sheet', ''),
            ('outside', 'Ra ngoài chỉ có dữ liệu một lần', 'postgres:auto_check', 'Giờ ra 15:00:00'),
            ('other', 'Ra ngoài vào muộn dưới 30 phút', 'postgres:auto_check', 'Giờ ra 14:00:00'),
        ]:
            conn.execute(text("INSERT INTO leave_records VALUES(:uid,'Synthetic',:day,:reason,:source,:detail,'AUTO','{}','2026-10-18 15:59:00+07')"),
                dict(uid=uid,day=day,reason=reason,source=source,detail=detail))
        conn.execute(text("INSERT INTO vera_auto_check_event SELECT CASE WHEN record_uid='outside' THEN 1 ELSE 2 END,leave_date,employee_name,leave_reason,'AUTO','added',detail,record_uid,NULL FROM leave_records WHERE source_sheet_id='postgres:auto_check'"))
    record = dict(record_uid='manual',employee_name='Synthetic',leave_date=day,leave_reason='Về sớm KHÔNG phép')
    # A rolled-back registration must roll back both the correction and retry.
    with database.connect() as conn:
        tx = conn.begin()
        rule.register(conn, record, SimpleNamespace(role='letan'))
        assert conn.execute(text("SELECT count(*) FROM leave_records WHERE record_uid='outside'")).scalar_one() == 0
        tx.rollback()
    with database.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM leave_records WHERE record_uid='outside'")).scalar_one() == 1
        rule.register(conn, record, SimpleNamespace(role='letan'))
    with database.begin() as conn:
        assert conn.execute(text('SELECT record_uid FROM leave_records ORDER BY record_uid')).scalars().all() == ['manual','other']
        assert conn.execute(text('SELECT status FROM vera_auto_check_event WHERE id=1')).scalar_one() == 'revoked'
        assert conn.execute(text('SELECT status FROM vera_auto_check_event WHERE id=2')).scalar_one() == 'added'
        assert conn.execute(text('SELECT count(*) FROM vera_background_job')).scalar_one() == 1
        assert rule.reconcile(conn,'Synthetic',day) == 0

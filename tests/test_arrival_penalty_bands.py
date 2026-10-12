from datetime import date
import pytest
import vera_auto_check as auto
import vera_holiday_leave as holiday
from test_live_tour_resource_postgres import database
from sqlalchemy import text


@pytest.mark.parametrize('minutes,index', [(0.01,0),(1,0),(30,0),(30.01,1),(60,1),(60.01,2),(120,2),(120.01,3),(300,3)])
def test_boundary_uses_exact_official_catalog_row(minutes, index):
    catalog = {auto._norm(name): {'name': name, 'penalty': 123 + i, 'days': 0}
               for i, name in enumerate(auto.ARRIVAL_BAND_REASONS)}
    assert auto.arrival_reason(catalog, minutes) is catalog[auto._norm(auto.ARRIVAL_BAND_REASONS[index])]
    assert auto.automatic_late_penalty_eligible(auto.ARRIVAL_BAND_REASONS[index], minutes)


@pytest.mark.parametrize('minutes', [0,-1,None,'bad',float('nan'),float('inf')])
def test_invalid_delay_has_no_band(minutes):
    assert auto.arrival_reason({}, minutes) is None


def test_missing_official_band_never_falls_back_to_flat_or_other_amount():
    catalog = {auto._norm('Đi trễ không phép'): {'name': 'Đi trễ không phép', 'penalty': 300000},
               auto._norm(auto.ARRIVAL_BAND_REASONS[1]): {'name': auto.ARRIVAL_BAND_REASONS[1], 'penalty': 100000}}
    assert auto.arrival_reason(catalog, 10) is None


@pytest.mark.parametrize('reason', auto.ARRIVAL_BAND_REASONS)
def test_band_retains_legacy_event_identity_and_does_not_write_twice(monkeypatch, reason):
    monkeypatch.setattr(auto, 'automatic_penalty_employee_eligible', lambda *_: True)
    monkeypatch.setattr(auto, 'ensure_schema', lambda *_: None)
    monkeypatch.setattr(holiday, 'intervals', lambda *_: {})
    monkeypatch.setattr(holiday, 'approved_day', lambda *_: False)
    class Connection:
        def execute(self, query, params):
            assert params['key'] == '2026-10-12|test|di tre khong phep'
            assert params['reason'] == reason
            return self
        def scalar(self): return None
    assert auto.save_violation(Connection(), work_date=date(2026,10,12), employee='Test',
        reason_item={'name': reason, 'penalty': 50000}, detail='test', source='test', minutes=10) == (True, 'SKIP_DUPLICATE')


def test_real_postgres_legacy_event_blocks_all_new_bands(database, monkeypatch):
    monkeypatch.setattr(auto, 'automatic_penalty_employee_eligible', lambda *_: True)
    monkeypatch.setattr(auto, 'ensure_schema', lambda *_: None)
    with database.begin() as conn:
        conn.execute(text("""CREATE TABLE vera_auto_check_event(
            id bigserial PRIMARY KEY, event_key text UNIQUE, work_date date,
            employee_name text, reason text, source text, minutes numeric, status text,
            detail text, employee_notified_at timestamptz, created_at timestamptz,
            employee_notify_claimed_at timestamptz, employee_notify_attempted_at timestamptz,
            employee_notify_error text)"""))
        conn.execute(text("""INSERT INTO vera_auto_check_event(event_key,work_date,employee_name,reason,status)
            VALUES('2026-10-12|test|di tre khong phep','2026-10-12','Test','Đi trễ không phép','added')"""))
        for reason in auto.ARRIVAL_BAND_REASONS:
            assert auto.save_violation(conn, work_date=date(2026,10,12), employee='Test',
                reason_item={'name': reason, 'penalty': 50000}, detail='test', source='test', minutes=10) == (True, 'SKIP_DUPLICATE')
        assert conn.execute(text('SELECT count(*) FROM vera_auto_check_event')).scalar_one() == 1


def test_real_postgres_support_revokes_bands_but_preserves_manual_and_other_fines(database, monkeypatch):
    with database.begin() as conn:
        conn.execute(text("""CREATE TABLE leave_records(record_uid text, source_sheet_id text,
            leave_date date,employee_name text,leave_reason text)"""))
        conn.execute(text("""CREATE TABLE vera_auto_check_event(work_date date,employee_name text,
            reason text,status text,leave_record_uid text,detail text)"""))
        reasons = ['Đi trễ không phép', *auto.ARRIVAL_BAND_REASONS, 'Ra ngoài vào muộn dưới 30 phút']
        for i, reason in enumerate(reasons):
            conn.execute(text("""INSERT INTO leave_records VALUES(:uid,'postgres:auto_check','2026-10-12','Test',:reason)"""),
                         {'uid':str(i),'reason':reason})
            conn.execute(text("""INSERT INTO vera_auto_check_event VALUES('2026-10-12','Test',:reason,'added',:uid,'test')"""),
                         {'uid':str(i),'reason':reason})
        conn.execute(text("""INSERT INTO leave_records VALUES('manual','postgres:web_v2','2026-10-12','Test','Đi trễ không phép')"""))
        assert auto.revoke_auto_late_penalty(conn, work_date=date(2026,10,12), employee='Test', basis='Hỗ trợ') == 5
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar_one() == 2
        assert conn.execute(text("SELECT count(*) FROM vera_auto_check_event WHERE status='revoked'")).scalar_one() == 5

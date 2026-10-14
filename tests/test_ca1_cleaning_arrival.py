"""A verified late Ca 1 arrival has two independent, idempotent fines."""
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import text

import timesoft_sync_job as job
import vera_auto_check as auto
import vera_facegate_runtime as runtime
import vera_attendance_source as source
from test_facegate_arrival_write_recheck import Clock, DAY, frame, current
from test_live_tour_resource_postgres import database


def catalog():
    rows = [dict(name=name, type='Vi phạm', days=0, penalty=25000*(i+1))
            for i, name in enumerate(auto.ARRIVAL_BAND_REASONS)]
    rows.append(dict(name='Đi trễ KHÔNG phép', type='Không phép', days=0, penalty=300000))
    rows.append(dict(name=auto.CLEANING_CA1_REASON, type='Vi phạm', days=0, penalty=100000))
    return {auto._norm(row['name']): row for row in rows}


@pytest.mark.parametrize('minutes', [0.1, 30, 60, 120, 121])
@pytest.mark.parametrize('shift', ['Ca 1', 'Ca 2', ''])
def test_worker_adds_cleaning_only_from_verified_ca1_and_replays_once(monkeypatch, minutes, shift):
    conn = object(); writes = []; events = set()
    @contextmanager
    def begin():
        yield conn
    monkeypatch.setattr(job, 'datetime', Clock)
    monkeypatch.setattr(source, 'source_for', lambda _: 'facegate')
    monkeypatch.setattr(auto, 'penalties_paused', lambda _: False)
    monkeypatch.setattr(job.department_attendance, 'employee_role', lambda *_: 'nhanvien')
    monkeypatch.setattr(auto, 'registered_late_for_day', lambda *_: ([], 0, ''))
    monkeypatch.setattr(auto, 'late_support_for_day', lambda *_: ([], 0, ''))
    monkeypatch.setattr(job, '_log', lambda *_: None)
    row = frame(); row['TotalMinuteInGoLate'] = minutes
    evidence = current(); evidence.update(late_minutes=minutes, shift=shift)
    monkeypatch.setattr(runtime, 'records', lambda c, *_: [evidence] if c is conn else [])
    def save(c, **kw):
        assert c is conn
        key = (kw['employee'], kw['work_date'], kw['reason_item']['name'])
        if key in events:
            return True, 'SKIP_DUPLICATE'
        events.add(key); writes.append(kw)
        return True, 'ADDED'
    monkeypatch.setattr(auto, 'save_violation', save)
    def run():
        return job.process_timesoft_penalties(SimpleNamespace(begin=begin), {},
            {job._employee_key('Synthetic Employee'): 'Synthetic Employee'}, catalog(),
            [(DAY, pd.DataFrame([row]))])
    assert run()['added'] == 1 + (shift == 'Ca 1')
    assert run()['added'] == 0
    assert len(writes) == 1 + (shift == 'Ca 1')
    if shift == 'Ca 1':
        cleaning = writes[-1]
        assert cleaning['reason_item'] == catalog()[auto._norm(auto.CLEANING_CA1_REASON)]
        assert cleaning['source'] == auto.CLEANING_CA1_SOURCE
    evidence['attendance_fine_evidence_ready'] = False
    events.clear(); writes.clear()
    assert run()['added'] == 0 and not writes


@pytest.mark.parametrize('shift,minutes', [('Ca 2', 10), ('', 10), ('Ca 1', 0), ('Ca 1', -1)])
def test_not_eligible_never_writes(monkeypatch, shift, minutes):
    monkeypatch.setattr(auto, 'save_violation', lambda *a, **kw: pytest.fail('unexpected fine'))
    assert auto.save_arrival_cleaning_violation(None, work_date=DAY, employee='Test',
        catalog=catalog(), shift=shift, detail='test', minutes=minutes) == 'SKIP_NOT_CA1_LATE'


def test_custom_shift_uses_vera_definition_and_missing_catalog_never_guesses(monkeypatch):
    import vera_web_v2_snapshot as snapshot
    conn = object()
    def definitions(c):
        assert c is conn
        return [{'Tên ca': 'Buổi sáng', 'Ca chính': 'Ca 1'}], {}
    monkeypatch.setattr(snapshot, '_shift_break_settings', definitions)
    monkeypatch.setattr(auto, 'save_violation', lambda *a, **kw: pytest.fail('missing catalog'))
    assert auto.save_arrival_cleaning_violation(conn, work_date=DAY, employee='Test',
        catalog={}, shift='Buổi sáng', detail='test', minutes=10) == 'MISSING_CLEANING_RULE'


def test_postgres_two_events_zero_days_retry_delete_and_rollback(database, monkeypatch):
    monkeypatch.setattr(auto, 'automatic_penalty_employee_eligible', lambda *_: True)
    monkeypatch.setattr(auto.progressive_penalty, 'load_weekend_unpaid_enabled', lambda *_: True)
    with database.begin() as conn:
        conn.execute(text('''CREATE TABLE leave_records (
            source_sheet_id text,source_row bigint,leave_date date,employee_name text,
            leave_reason text,leave_type text,detail text,calculated_days numeric,
            accumulated_leave numeric,penalty numeric,update_date text,update_time text,
            updated_by text,weekday_label text,payload jsonb,record_uid text,
            created_at timestamptz,updated_at timestamptz)'''))
        auto.ensure_schema(conn)
    def write(conn, employee='Test'):
        primary = auto.save_violation(conn, work_date=DAY, employee=employee,
            reason_item=auto.arrival_reason(catalog(), 30), detail='test', source='test', minutes=30)
        extra = auto.save_arrival_cleaning_violation(conn, work_date=DAY, employee=employee,
            catalog=catalog(), shift='Ca 1', detail='test', minutes=30)
        return primary[1], extra
    with database.begin() as conn:
        assert write(conn) == ('ADDED', 'ADDED')
        assert write(conn) == ('SKIP_DUPLICATE', 'SKIP_DUPLICATE')
        assert conn.execute(text('SELECT SUM(penalty) FROM leave_records')).scalar_one() == 125000
        assert conn.execute(text('SELECT SUM(calculated_days) FROM leave_records')).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM vera_auto_check_event WHERE status='added' AND employee_notified_at IS NULL")).scalar_one() == 2
        conn.execute(text('DELETE FROM leave_records'))
        assert write(conn) == ('SKIP_DUPLICATE', 'SKIP_DUPLICATE')
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar_one() == 0
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            assert write(conn, 'Rollback') == ('ADDED', 'ADDED')
            raise RuntimeError('rollback')
    with database.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_auto_check_event')).scalar_one() == 2


@pytest.mark.parametrize('day,expected', [(date(2026, 10, 9), 'Ca 2'), (date(2026, 10, 10), 'Ca 1'), (date(2026, 10, 17), 'Ca 2')])
def test_weekly_vera_rotation_not_base_shift_decides_cleaning(monkeypatch, day, expected):
    from vera_web_v2_attendance_query_perf import _vera_shift_fields
    profile = dict(role='nhanvien', work_shift='Ca 2', shift_start_date='03/10/2026', rotation_cycle='Theo chu kỳ tuần')
    shift, _, _ = _vera_shift_fields(profile, day, [])
    assert shift == expected
    writes = []
    monkeypatch.setattr(auto, 'save_violation', lambda *a, **kw: writes.append(kw) or (True, 'ADDED'))
    auto.save_arrival_cleaning_violation(None, work_date=day, employee='Test', catalog=catalog(),
        shift=shift, detail='weekly', minutes=10)
    assert len(writes) == int(expected == 'Ca 1')

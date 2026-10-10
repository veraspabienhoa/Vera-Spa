from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

import timesoft_sync_job as job
import vera_facegate_runtime as runtime
import vera_attendance_source as source
from vera_facegate_control_log import VN_TZ

DAY = date(2026, 10, 10)

class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 10, 12, tzinfo=VN_TZ)


def frame():
    return {'WorkDateStr': '10/10/2026', 'employeeInfo.Name': 'Synthetic Employee',
        'MachineTimeCheckInStr': '10/10/2026 10:10:00', 'StartWorkTime': '10:00',
        'TotalMinuteInGoLate': 10, '_vera_evidence_source': 'facegate',
        '_vera_checkin_at': '2026-10-10T10:10:00+07:00'}


def current():
    return {'employee_name': 'Synthetic Employee', 'attendance_fine_evidence_ready': True,
        'identity_verified': True, 'check_in': '10:10:00', 'check_in_at': '2026-10-10T10:10:00+07:00',
        'shift_start': '10:00', 'late_minutes': 10}


@pytest.mark.parametrize('change', ['none', 'stale', 'conflict', 'earlier_arrival', 'shift', 'identity', 'missing', 'duplicate', 'pause', 'source_marker'])
def test_arrival_rechecks_same_write_connection_and_defers_changed_basis(monkeypatch, change):
    conn = object(); calls = []; writes = []; reads = []
    @contextmanager
    def begin():
        calls.append('transaction')
        yield conn
    monkeypatch.setattr(job, 'datetime', Clock)
    monkeypatch.setattr(source, 'source_for', lambda _: 'facegate')
    monkeypatch.setattr(job.auto_check, 'penalties_paused', lambda c: change == 'pause' and len(calls) > 1)
    monkeypatch.setattr(job.department_attendance, 'employee_role', lambda *_: 'nhanvien')
    monkeypatch.setattr(job.auto_check, 'registered_late_for_day', lambda *_: ([], 0, ''))
    monkeypatch.setattr(job.auto_check, 'late_support_for_day', lambda *_: ([], 0, ''))
    monkeypatch.setattr(job, '_log', lambda *_: None)
    saved = current(); row = frame()
    if change in {'stale', 'conflict'}: saved['attendance_fine_evidence_ready'] = False
    if change == 'earlier_arrival': saved['check_in_at'] = '2026-10-10T09:50:00+07:00'
    if change == 'shift': saved['shift_start'] = '11:00'
    if change == 'identity': saved['identity_verified'] = False
    if change == 'source_marker': row.pop('_vera_evidence_source')
    def records(c, start, end):
        assert c is conn and start == end == DAY
        reads.append(c)
        return [] if change == 'missing' else [saved, saved] if change == 'duplicate' else [saved]
    monkeypatch.setattr(runtime, 'records', records)
    monkeypatch.setattr(job.auto_check, 'save_violation', lambda c, **kw: writes.append((c, kw)) or (True, 'ADDED'))
    name = 'Đi trễ không phép'
    result = job.process_timesoft_penalties(SimpleNamespace(begin=begin), {'threshold_minutes': 5}, {job._employee_key('Synthetic Employee'): 'Synthetic Employee'},
        {job._norm(name): {'name': name, 'penalty': 100}}, [(DAY, pd.DataFrame([row]))])
    assert len(writes) == result['added'] == int(change == 'none')
    assert all(c is conn for c, _ in writes)
    assert result['errors'] == 0
    assert len(calls) == 2

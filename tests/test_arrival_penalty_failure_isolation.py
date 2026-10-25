"""Synthetic arrivals: one failed transaction must not starve the next employee."""
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

import timesoft_sync_job as job


@pytest.mark.parametrize('stage', ['read', 'write', 'commit', 'cleaning'])
def test_failed_employee_retries_without_blocking_or_duplicating_other_arrivals(monkeypatch, stage):
    day = datetime.now(job.VN_TZ).date()
    state = {'fail': True, 'employee': None, 'active': 0, 'committed': set(), 'pending': set()}
    logs = []

    @contextmanager
    def begin():
        assert state['active'] == 0
        state['active'] = 1
        state['pending'] = set()
        try:
            yield object()
            if stage == 'commit' and state['fail'] and 'Broken' in state['pending']:
                raise RuntimeError('PRIVATE_DATABASE_PARAMETERS')
            state['committed'].update(state['pending'])
        finally:
            state['pending'] = set()
            state['active'] = 0

    def role(conn, employee):
        state['employee'] = employee
        if stage == 'read' and state['fail'] and employee == 'Broken':
            raise RuntimeError('PRIVATE_DATABASE_PARAMETERS')
        return 'nhanvien'

    def save(conn, **kw):
        name = kw['employee']
        assert state['active'] == 1
        if stage == 'write' and state['fail'] and name == 'Broken':
            raise RuntimeError('PRIVATE_DATABASE_PARAMETERS')
        if name in state['committed']:
            return True, 'SKIP_DUPLICATE'
        state['pending'].add(name)
        return True, 'ADDED'

    def current(conn, row, work_date, employee, *, basis):
        basis['shift'] = 'Ca 1'
        return True

    def cleaning(conn, **kw):
        if stage == 'cleaning' and state['fail'] and kw['employee'] == 'Broken':
            raise RuntimeError('PRIVATE_DATABASE_PARAMETERS')
        return 'SKIP_NOT_CA1_LATE'

    monkeypatch.setattr(job.department_attendance, 'employee_role', role)
    monkeypatch.setattr(job.auto_check, 'registered_late_for_day', lambda *a: ([], 0, ''))
    monkeypatch.setattr(job.auto_check, 'late_support_for_day', lambda *a: ([], 0, ''))
    monkeypatch.setattr(job, '_facegate_arrival_current', current)
    monkeypatch.setattr(job.auto_check, 'save_violation', save)
    monkeypatch.setattr(job.auto_check, 'save_arrival_cleaning_violation', cleaning)
    monkeypatch.setattr(job, '_log', logs.append)
    names = {job._employee_key(n): n for n in ('Broken', 'Healthy')}
    frame = pd.DataFrame([{'employeeInfo.Name': n, 'TotalMinuteInGoLate': 10} for n in names.values()])
    reason = 'Đi trễ nhỏ hơn hoặc bằng 30 phút'
    args = (SimpleNamespace(begin=begin), {'threshold_minutes': 5}, names,
            {job._norm(reason): {'name': reason, 'penalty': 100}}, [(day, frame)])

    # The original loop exits at Broken on every pass and never reaches Healthy.
    with pytest.raises(RuntimeError):
        job._process_timesoft_penalty_rows(*args)
    assert state['committed'] == set()

    first = job.process_timesoft_penalties(*args)
    assert first['added'] == first['errors'] == 1
    assert first['error_counts'] == {'unexpected_error': 1}
    assert state['committed'] == {'Healthy'}
    second = job.process_timesoft_penalties(*args)
    assert second['added'] == 0 and second['errors'] == second['skipped'] == 1
    state['fail'] = False
    final = job.process_timesoft_penalties(*args)
    assert final == {'eligible': 2, 'added': 1, 'skipped': 1, 'errors': 0}
    assert state['committed'] == {'Broken', 'Healthy'}
    assert 'PRIVATE_DATABASE_PARAMETERS' not in '\n'.join(logs)
    assert state['active'] == 0

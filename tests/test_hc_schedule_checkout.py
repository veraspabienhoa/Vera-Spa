from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import vera_facegate_attendance as fg
import vera_hc_attendance as hc
import vera_web_v2_work_schedule as schedule
from vera_web_v2_attendance_query_perf import _placeholder_record


@pytest.mark.parametrize('role', ['quanly', 'support', 'thungan', 'giamdoc', 'letan', 'locker', 'tapvu', 'warehouse'])
def test_all_eligible_hc_keep_checkout(role):
    row = {'date': '01/10/2026', 'employee_name': 'synthetic', 'employee_role': role,
           'hc_checkout_eligible': True, 'shift_start': '17:00', 'shift_end': '01:00',
           'punch_datetimes': ['2026-10-01T17:00:00', '2026-10-02T01:00:00']}
    result = fg.finish_records([row], [])[0]
    assert result['check_out'] == '01:00:00'
    assert result['check_out_at'] == '2026-10-02T01:00:00+07:00'


@pytest.mark.parametrize('role', ['nhanvien', 'leader', 'admin'])
def test_hr_reassignment_cannot_change_technician_or_admin_checkout_policy(role):
    row = {'employee_role': role, 'hc_checkout_eligible': True,
           'check_out': '17:00:00', 'faceid_check_out': '17:00:00', 'check_out_at': 'stale'}
    result = fg.finish_records([row], [])[0]
    assert result['check_out'] == result['faceid_check_out'] == ''
    assert 'check_out_at' not in result


def test_explicit_ineligible_hr_flag_cannot_fall_back_to_old_role():
    assert not hc.checkout_eligible({'role': 'letan', 'hc_checkout_eligible': False})
    assert not hc.checkout_eligible({'role': 'unknown'})
    assert hc.checkout_eligible({'role': 'support'})


@pytest.mark.parametrize('role', ['support', 'thungan', 'giamdoc', 'warehouse'])
def test_hc_requires_explicit_schedule_instead_of_legacy_work_shift(role):
    profile = {'username': 'synthetic', 'role': role, 'work_shift': 'Ca 1 09:00-17:00', 'hc_checkout_eligible': True}
    row = _placeholder_record(profile, date(2026, 10, 1), [], {}, {}, None)
    assert row['shift_start'] == row['shift_end'] == row['shift'] == ''
    assert not row['attendance_expected']


def test_new_hc_schedule_requires_explicit_time_and_overtime():
    row = schedule.ScheduleRow(work_date=date(2026, 10, 1), employee_username='synthetic',
                               department='support', shift_code='Giờ làm', start_time='09:00', end_time='17:00')
    assert schedule._validate_row(row, {}) == ('09:00', '17:00', '', '', '')
    for changed in [{'start_time': ''}, {'end_time': '09:00'}, {'shift_code': 'Ca 1'}, {'overtime_shift': 'TC Ca 2'}]:
        with pytest.raises(HTTPException):
            schedule._validate_row(row.model_copy(update=changed), {})
    overtime = row.model_copy(update={'overtime_shift': 'Từ giờ tới giờ', 'overtime_start_time': '17:00', 'overtime_end_time': '19:00'})
    assert schedule._validate_row(overtime, {}) == ('09:00', '17:00', 'Từ giờ tới giờ', '17:00', '19:00')


def test_additional_hc_department_needs_new_grant_and_active_hr_definition(monkeypatch):
    monkeypatch.setattr(schedule.hr, 'admin_departments', lambda conn: {'support': {'name': 'Support'}})
    ident = SimpleNamespace(role='quanly')
    checks = []
    def legacy_only(conn, user, feature):
        checks.append(feature)
        return feature == 'work_schedule_letan'
    assert schedule._allowed_department(None, ident, 'letan', legacy_only)
    assert not schedule._allowed_department(None, ident, 'support', legacy_only)
    assert not schedule._allowed_department(None, ident, 'inactive', lambda *_: True)
    assert schedule._allowed_department(None, ident, 'support', lambda *_: True)
    assert checks == ['work_schedule_letan', 'work_schedule_hc']


def test_known_overnight_hc_punch_is_assigned_to_previous_workday():
    from datetime import datetime
    day = date(2026, 10, 1)
    windows = {day: fg.shift_interval(day, '17:00', '01:00'),
               date(2026, 10, 2): fg.shift_interval(date(2026, 10, 2), '03:00', '11:00')}
    instant = datetime(2026, 10, 2, 1)
    assert fg.business_day(instant, windows, allow_checkout=hc.checkout_eligible({'role': 'support'})) == (day, '')


def test_new_hc_permission_is_registered_without_nonadmin_default_grants(monkeypatch):
    from copy import deepcopy
    import vera_web_v2_work_schedule_permissions as grants
    monkeypatch.setattr(grants.permissions, 'FEATURE_GROUPS', deepcopy(grants.permissions.FEATURE_GROUPS))
    monkeypatch.setattr(grants.permissions, 'FEATURES', dict(grants.permissions.FEATURES))
    monkeypatch.setattr(grants.permissions, 'DEFAULT_ROLE_FEATURES', deepcopy(grants.permissions.DEFAULT_ROLE_FEATURES))
    monkeypatch.setattr(grants, '_install_giamdoc_role', lambda: None)
    monkeypatch.setattr(grants, '_install_directory_visibility_middleware', lambda: None)
    grants.install_work_schedule_permissions()
    assert 'work_schedule_hc' in grants.permissions.FEATURES
    assert all('work_schedule_hc' not in features for role, features in grants.permissions.DEFAULT_ROLE_FEATURES.items() if role != 'admin')

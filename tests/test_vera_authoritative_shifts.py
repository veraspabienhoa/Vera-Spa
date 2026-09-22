from copy import deepcopy
from datetime import date, timedelta

import pytest
import vera_web_v2_attendance_query_perf as attendance
from vera_web_v2_live_tour_checkin import project
from test_live_tour_shift_effective_date import staff, punches, now_on, DEFINITIONS


@pytest.mark.parametrize('cycle', ['Cố định (Không đổi)', 'Theo chu kỳ Tuần', 'Mỗi 2 ngày'])
def test_attendance_and_tour_share_vera_assignment_and_rotation(cycle):
    profile = staff(rotation_cycle=cycle)
    for offset in range(22):
        day = date(2026, 9, 14) + timedelta(days=offset)
        tour = project([deepcopy(profile)], punches(day, WorkTimeName='Ca 2'), now_on(day))[0]
        name, _, _ = attendance._vera_shift_fields(profile, day, DEFINITIONS)
        assert name == tour['daily_shift']


def test_phuong_vy_vera_ca1_beats_timesoft_ca2_in_actual_attendance_reader(monkeypatch):
    day = date(2026, 9, 22)
    profile = staff(username='Phương Vy', full_name='Phương Vy', work_shift='Ca 1', rotation_cycle='Cố định (Không đổi)')
    class Result:
        def mappings(self): return self
        def all(self): return [profile]
    class Connection:
        def execute(self, *_args, **_kwargs): return Result()
    monkeypatch.setattr(attendance.snapshot, '_shift_break_settings', lambda conn: (DEFINITIONS, {}))
    monkeypatch.setattr(attendance.department_attendance, 'controls', lambda conn: {})
    monkeypatch.setattr(attendance.v42, '_eligible_aliases', lambda conn: ({'phuong vy': 'Phương Vy'}, {'phuong vy': 'nhanvien'}))
    monkeypatch.setattr(attendance, '_schedule_map', lambda *args: {})
    datasets = punches(day, EmployeeName='Phương Vy', WorkTimeName='Ca 2', StartWorkTime='13:00', EndWorkTime='00:00')
    monkeypatch.setattr(attendance, '_datasets', lambda *args: datasets)
    monkeypatch.setattr(attendance, '_append_missing_active_employees', lambda *args: None)
    records = attendance._records_v42_fast(Connection(), day, day)
    assert records[0]['shift'] == 'Ca 1'
    assert records[0]['shift_start'] == '10:00'
    assert records[0]['shift_end'] == '23:00'
    assert records[0]['check_in']  # Preserve actual FaceID evidence.
    assert project([profile], datasets, now_on(day))[0]['daily_shift'] == 'Ca 1'


@pytest.mark.parametrize('profile', [staff(work_shift=''), staff(shift_start_date='2026-10-01'), staff(shift_start_date='invalid')])
def test_missing_or_ineffective_vera_assignment_stays_unassigned(profile):
    day = date(2026, 9, 22)
    assert attendance._vera_shift_fields(profile, day, DEFINITIONS) == ('', '', '')
    assert project([profile], punches(day, WorkTimeName='Ca 2'), now_on(day))[0]['daily_shift'] == ''

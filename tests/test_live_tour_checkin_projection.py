from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from vera_web_v2_live_tour_checkin import project, scheduled_shift
from vera_web_v2_live_tour_roster import reconcile
import vera_web_v2_live_tour as live
from test_live_tour_backend import employee, state_with


NOW = datetime(2026, 9, 14, 18, tzinfo=live.VN_TZ)


def directory():
    return [{'username': 'An', 'full_name': 'Nguyễn An', 'role': 'nhanvien', 'payload': {},
             'work_shift': 'Ca 1', 'shift_start_date': '31/08/2026', 'rotation_cycle': 'Luân phiên (14 ngày)'}]


def data(**fields):
    return [{'payload': [{'EmployeeName': 'Nguyễn An', 'WorkDateStr': '14/09/2026', **fields}]}]


@pytest.mark.parametrize('fields', [{}, {'MachineTimeCheckOutStr': '17:00'}, {'MachineTimeCheckInStr': '00:30'}, {'MachineTimeCheckInStr': '23:10'}, {'MachineTimeCheckInStr': 'invalid'}])
def test_schedule_and_checkout_do_not_enable_shift(fields):
    assert project(directory(), data(**fields), NOW)[0]['daily_shift'] == ''


def test_checkin_enables_daily_timesoft_shift_and_next_day_clears_it():
    rows = data(MachineTimeCheckInStr='10:01', WorkTimeName='Ca 2')
    assert project(directory(), rows, NOW)[0]['daily_shift'] == 'Ca 2'
    assert project(directory(), rows, NOW + timedelta(days=1))[0]['daily_shift'] == ''


def test_rotation_fallback_and_fixed_shift():
    row = directory()[0]
    assert scheduled_shift(row, NOW.date() - timedelta(days=7)) == 'Ca 1'
    assert scheduled_shift(row, NOW.date()) == 'Ca 2'
    assert project([row], data(MachineTimeCheckInStr='14:01'), NOW)[0]['daily_shift'] == 'Ca 2'
    row['rotation_cycle'] = 'Cố định (Không đổi)'
    assert scheduled_shift(row, NOW.date()) == 'Ca 1'


def test_raw_checkin_and_named_main_shift():
    rows = directory()
    rows[0]['shift_definitions'] = [{'Tên ca': 'Buổi chiều', 'Ca chính': 'Ca 2'}]
    assert project(rows, data(CheckInTime='14/09/2026 14:01:00', WorkTimeName='Buổi chiều'), NOW)[0]['daily_shift'] == 'Ca 2'


def test_no_checkin_clears_stale_shift_without_clearing_service():
    worker = employee('e1', 'An')
    worker.update(service='Body', status='Đang thực hiện', started_at=NOW.isoformat(), shift='Ca 1')
    state = state_with(worker)
    rows = project(directory(), [], NOW)
    reconcile(state, rows, live._new_directory_employee)
    assert worker['shift'] == ''
    assert worker['service'] == 'Body'
    assert worker['started_at'] == NOW.isoformat()
    rows = project(directory(), data(MachineTimeCheckInStr='14:01'), NOW)
    reconcile(state, rows, live._new_directory_employee)
    assert worker['shift'] == 'Ca 2'
    worker['work_status'] = 'Nghỉ phép'
    reconcile(state, rows, live._new_directory_employee)
    assert worker['shift'] == ''


def test_duplicate_full_name_does_not_check_in_two_people():
    rows = directory()
    rows.append({**deepcopy(rows[0]), 'username': 'An 2'})
    assert all(row['daily_shift'] == '' for row in project(rows, data(MachineTimeCheckInStr='14:01'), NOW))


def test_board_refresh_picks_up_checkin_then_clears_next_day(monkeypatch):
    from test_live_tour_server_only import SettingsDatabase, app_client
    clock = [NOW]
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
    monkeypatch.setattr(live, 'datetime', FixedDateTime)
    db = SettingsDatabase(state_with(employee('e1', 'An')), directory=directory())
    _, client = app_client(db)
    first = client.get('/v2/live-tour').json()
    assert first['records'][0]['Vào ca'] == ''
    db.datasets = data(MachineTimeCheckInStr='14:01', WorkTimeName='Ca 2')
    checked = client.get('/v2/live-tour').json()
    assert checked['records'][0]['Vào ca'] == 'Ca 2'
    assert checked['revision'] > first['revision']
    assert client.get('/v2/live-tour').json()['revision'] == checked['revision']
    clock[0] += timedelta(days=1)
    assert client.get('/v2/live-tour').json()['records'][0]['Vào ca'] == ''

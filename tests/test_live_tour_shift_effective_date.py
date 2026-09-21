"""The saved, effective staff assignment must beat stale TimeSoft shift labels."""
from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

import vera_web_v2_live_tour as live
from vera_web_v2_live_tour_checkin import project
from vera_web_v2_live_tour_roster import reconcile
from test_live_tour_backend import employee, state_with
from test_live_tour_server_only import SettingsDatabase, app_client


DEFINITIONS = [
    {'Tên ca': 'Ca 1', 'Giờ bắt đầu': '10:00', 'Giờ kết thúc': '23:00', 'Ca chính': 'Ca 1'},
    {'Tên ca': 'Ca 2', 'Giờ bắt đầu': '13:00', 'Giờ kết thúc': '00:00', 'Ca chính': 'Ca 2'},
]


def staff(**changes):
    return {
        'username': 'Thanh Nhã', 'full_name': 'Phan Anh Thư', 'role': 'nhanvien',
        'payload': {}, 'work_shift': 'Ca 1 (10:00 - 23:00)',
        'shift_start_date': '14/09/2026', 'rotation_cycle': 'Luân phiên (14 ngày)',
        'shift_definitions': deepcopy(DEFINITIONS), **changes,
    }


def now_on(day):
    return datetime.combine(day, datetime.min.time(), tzinfo=live.VN_TZ).replace(hour=18)


def punches(day, **changes):
    return [{'payload': [{
        'EmployeeName': 'Phan Anh Thư', 'WorkDateStr': day.strftime('%d/%m/%Y'),
        'MachineTimeCheckInStr': '10:02', 'WorkTimeName': 'Ca 2', **changes,
    }]}]


@pytest.mark.parametrize('day, expected', [
    (date(2026, 9, 13), 'Ca 2'),  # The new assignment is not effective yet.
    (date(2026, 9, 14), 'Ca 1'),
    (date(2026, 9, 15), 'Ca 1'),
    (date(2026, 9, 20), 'Ca 1'),
    (date(2026, 9, 21), 'Ca 2'),
    (date(2026, 9, 27), 'Ca 2'),
    (date(2026, 9, 28), 'Ca 1'),
    (date(2026, 10, 11), 'Ca 2'),
    (date(2026, 10, 12), 'Ca 1'),
])
@pytest.mark.parametrize('timesoft_shift', ['Ca 1', 'Ca 2'])
def test_effective_assignment_and_rotation_win_over_timesoft(day, expected, timesoft_shift):
    if day < date(2026, 9, 14):
        expected = timesoft_shift
    rows = project([staff()], punches(day, WorkTimeName=timesoft_shift), now_on(day))
    assert rows[0]['daily_shift'] == expected


@pytest.mark.parametrize('start', ['14/09/2026', '2026-09-14', date(2026, 9, 14)])
@pytest.mark.parametrize('name', ['Thanh Nhã', 'Phan Anh Thư'])
def test_both_employee_aliases_and_stored_date_formats(start, name):
    day = date(2026, 9, 15)
    rows = project([staff(shift_start_date=start)], punches(day, EmployeeName=name), now_on(day))
    assert rows[0]['daily_shift'] == 'Ca 1'


@pytest.mark.parametrize('updates, timesoft_shift, expected', [
    ({'work_shift': ''}, 'Ca 2', 'Ca 2'),
    ({'work_shift': 'Chưa chọn'}, 'Ca 2', 'Ca 2'),
    ({'work_shift': ''}, '', ''),
    ({'shift_start_date': '16/09/2026'}, 'Ca 2', 'Ca 2'),
    ({'shift_start_date': '16/09/2026'}, '', ''),
    ({'shift_start_date': '31/02/2026'}, 'Ca 2', 'Ca 2'),
    ({'shift_start_date': '31/02/2026'}, '', ''),
    ({'shift_start_date': ''}, 'Ca 2', 'Ca 1'),
    ({'shift_start_date': None}, 'Ca 2', 'Ca 1'),
])
def test_fallback_and_effective_date_safety(updates, timesoft_shift, expected):
    day = date(2026, 9, 15)
    rows = project([staff(**updates)], punches(day, WorkTimeName=timesoft_shift), now_on(day))
    assert rows[0]['daily_shift'] == expected


@pytest.mark.parametrize('cycle, day, expected', [
    ('Cố định (Không đổi)', date(2026, 9, 28), 'Ca 1'),
    ('Theo chu kỳ Tuần', date(2026, 9, 21), 'Ca 2'),
    ('Theo chu kỳ Tuần', date(2026, 9, 28), 'Ca 1'),
    ('Mỗi 2 ngày', date(2026, 9, 16), 'Ca 2'),
    ('Mỗi 2 ngày', date(2026, 9, 18), 'Ca 1'),
])
def test_other_existing_rotation_modes_are_preserved(cycle, day, expected):
    stale = 'Ca 2' if expected == 'Ca 1' else 'Ca 1'
    rows = project([staff(rotation_cycle=cycle)], punches(day, WorkTimeName=stale), now_on(day))
    assert rows[0]['daily_shift'] == expected


def test_custom_staff_shift_uses_configured_main_shift():
    day = date(2026, 9, 15)
    row = staff(work_shift='Buổi sáng (10:00 - 23:00)')
    row['shift_definitions'][0]['Tên ca'] = 'Buổi sáng'
    assert project([row], punches(day), now_on(day))[0]['daily_shift'] == 'Ca 1'


@pytest.mark.parametrize('fields', [
    {'MachineTimeCheckInStr': ''},
    {'MachineTimeCheckInStr': '', 'MachineTimeCheckOutStr': '17:00'},
    {'MachineTimeCheckInStr': '00:30'},
    {'MachineTimeCheckInStr': '23:10'},
    {'MachineTimeCheckInStr': '19:00'},  # A future timestamp is not evidence yet.
    {'MachineTimeCheckInStr': 'invalid'},
    {'WorkDateStr': '14/09/2026'},  # A previous day's check-in cannot open today.
])
def test_assignment_never_fabricates_a_checkin(fields):
    day = date(2026, 9, 15)
    assert project([staff()], punches(day, **fields), now_on(day))[0]['daily_shift'] == ''


def test_empty_timesoft_does_not_open_the_assigned_shift():
    assert project([staff()], [], now_on(date(2026, 9, 15)))[0]['daily_shift'] == ''


def test_same_day_admin_override_wins_then_expires():
    day = date(2026, 9, 14)
    worker = employee('e1', 'Thanh Nhã', shift='Ca 2')
    worker.update(username='Thanh Nhã', manual_shift='Ca 2', manual_shift_date=day.isoformat(), manual_shift_by='admin')
    state = state_with(worker)
    rows = project([staff()], punches(day), now_on(day))
    reconcile(state, rows, live._new_directory_employee, today=day.isoformat())
    live._sync_daily(state, rows, [], automatic=False, today=day.isoformat())
    assert worker['assigned_shift'] == 'Ca 1'
    assert worker['shift'] == 'Ca 2'

    tomorrow = day + timedelta(days=1)
    rows = project([staff()], punches(tomorrow), now_on(tomorrow))
    reconcile(state, rows, live._new_directory_employee, today=tomorrow.isoformat())
    live._sync_daily(state, rows, [], automatic=False, today=tomorrow.isoformat())
    assert worker['shift'] == worker['assigned_shift'] == 'Ca 1'
    assert 'manual_shift_date' not in worker


def test_leave_still_hides_shift_without_removing_service():
    day = date(2026, 9, 15)
    worker = employee('e1', 'Thanh Nhã', shift='Ca 2')
    worker.update(username='Thanh Nhã', work_status='Nghỉ phép', service='Body 90', room='1.1',
                  status='Đang thực hiện', started_at=now_on(day).isoformat())
    state = state_with(worker)
    before = deepcopy(worker)
    rows = project([staff()], punches(day), now_on(day))
    reconcile(state, rows, live._new_directory_employee, today=day.isoformat())
    assert worker['assigned_shift'] == 'Ca 1'
    assert worker['shift'] == ''
    for name in ('service', 'room', 'status', 'started_at'):
        assert worker[name] == before[name]


@pytest.mark.parametrize('day', [date(2026, 9, 14), date(2026, 9, 15)])
def test_api_refresh_repairs_persisted_shift_after_staff_edit(monkeypatch, day):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now_on(day).astimezone(tz) if tz else now_on(day).replace(tzinfo=None)

    monkeypatch.setattr(live, 'datetime', Clock)
    worker = employee('e1', 'Thanh Nhã', shift='Ca 2')
    worker.update(username='Thanh Nhã', service='Body 90', room='1.1',
                  status='Đang thực hiện', started_at=now_on(day).isoformat())
    state = state_with(worker)
    db = SettingsDatabase(state, directory=[staff(work_shift='Ca 2', shift_start_date='')])
    db.datasets = punches(day)
    _, client = app_client(db)
    first_response = client.get('/v2/live-tour')
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    assert first['records'][0]['Vào ca'] == 'Ca 2'
    before = deepcopy(db.stored)

    # Simulate the persisted staff edit; TimeSoft intentionally still says Ca 2.
    db.directory = [staff()]
    with db.begin() as conn:
        live._read_state(conn, now_on(day), for_update=True)
    changed_response = client.get('/v2/live-tour?refresh=true')
    assert changed_response.status_code == 200, changed_response.text
    changed = changed_response.json()
    assert changed['records'][0]['Vào ca'] == 'Ca 1'
    assert changed['revision'] == first['revision'] + 1
    for name in ('service', 'room', 'status', 'started_at', 'tour_count', 'request_count', 'stt'):
        assert db.stored['employees'][0][name] == before['employees'][0][name]
    for name in ('invoices', 'pending', 'customers', 'reports', 'idempotency'):
        assert db.stored[name] == before[name]

    # A second device's conditional poll receives the new revision and shift.
    polled = client.get('/v2/live-tour', params={'known_revision': first['revision']}).json()
    assert polled['records'][0]['Vào ca'] == 'Ca 1'
    assert polled['revision'] == changed['revision']
    assert client.get('/v2/live-tour').json()['revision'] == changed['revision']
    unchanged = client.get('/v2/live-tour', params={'known_revision': changed['revision']}).json()
    assert unchanged['unchanged'] is True

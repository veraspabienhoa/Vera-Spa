"""Live Tour shifts last until 02:00 VN, independently of other day cutoffs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
import vera_web_v2_live_tour_checkin as checkin
from test_live_tour_backend import employee, state_with
from test_live_tour_server_only import SettingsDatabase, app_client


def instant(value):
    return datetime.fromisoformat(value + '+07:00')


def directory(shift='Ca 1', **updates):
    return [{
        'username': 'Thanh Nhã', 'full_name': 'Phan Anh Thư', 'role': 'nhanvien',
        'payload': {}, 'work_shift': shift, 'shift_start_date': '14/09/2026',
        'rotation_cycle': 'Cố định (Không đổi)', **updates,
    }]


def punches(day='15/09/2026', **updates):
    return [{'payload': [{
        'EmployeeName': 'Phan Anh Thư', 'WorkDateStr': day,
        'MachineTimeCheckInStr': '10:01', 'WorkTimeName': 'Ca 2', **updates,
    }]}]


def worker_state(**updates):
    worker = employee('e1', 'Thanh Nhã')
    worker.update(username='Thanh Nhã', **updates)
    return state_with(worker)


def freeze_clock(monkeypatch, value):
    clock = [value]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    monkeypatch.setattr(live, 'datetime', Clock)
    return clock


@pytest.mark.parametrize('shift', ['Ca 1', 'Ca 2'])
@pytest.mark.parametrize('value, retained', [
    ('2026-09-15T23:59:59', True),
    ('2026-09-16T00:00:00', True),
    ('2026-09-16T00:15:00', True),
    ('2026-09-16T01:59:59.999999', True),
    ('2026-09-16T02:00:00', False),
    ('2026-09-16T02:00:01', False),
    ('2026-09-16T09:00:00', False),
])
def test_shift_survives_midnight_and_expires_at_two(shift, value, retained):
    result = checkin.project(directory(shift), punches(), instant(value))[0]
    assert result['daily_shift'] == (shift if retained else '')
    assert result['shift_checkin_date'] == ('2026-09-15' if retained else '2026-09-16')


@pytest.mark.parametrize('now, expected_day, expected_shift', [
    (datetime(2026, 9, 15, 18, 59, 59, 999999, tzinfo=timezone.utc), '2026-09-15', 'Ca 1'),
    (datetime(2026, 9, 15, 19, tzinfo=timezone.utc), '2026-09-16', ''),
    (datetime(2026, 9, 16, 1, 59, 59), '2026-09-15', 'Ca 1'),
    (datetime(2026, 9, 16, 2), '2026-09-16', ''),
])
def test_rollover_uses_vietnam_time_even_on_a_utc_host(now, expected_day, expected_shift):
    result = checkin.project(directory(), punches(), now)[0]
    assert result['shift_checkin_date'] == expected_day
    assert result['daily_shift'] == expected_shift


@pytest.mark.parametrize('value', ['2026-10-01T01:59:59', '2027-01-01T00:00:00', '2028-03-01T01:30:00'])
def test_month_year_and_leap_day_rollovers(value):
    now = instant(value)
    yesterday = now.date() - timedelta(days=1)
    result = checkin.project(directory(), punches(yesterday.strftime('%d/%m/%Y')), now)[0]
    assert result['daily_shift'] == 'Ca 1'
    assert result['shift_checkin_date'] == yesterday.isoformat()


@pytest.mark.parametrize('value, expected_day', [
    ('2026-09-16T00:00:00', '2026-09-15'),
    ('2026-09-16T01:59:59', '2026-09-15'),
    ('2026-09-16T02:00:00', '2026-09-16'),
])
def test_dataset_query_uses_the_same_shift_day(monkeypatch, value, expected_day):
    queries = []
    connection = object()

    def datasets(conn, start, end):
        assert conn is connection
        queries.append((start.isoformat(), end.isoformat()))
        return punches()

    monkeypatch.setattr(checkin, '_datasets', datasets)
    checkin.with_checkin(connection, directory(), instant(value))
    assert queries == [(expected_day, expected_day)]
    checkin.with_checkin(connection, [], instant(value))
    assert len(queries) == 1  # No extra query for an empty directory.


@pytest.mark.parametrize('value, expected', [
    ('2026-09-28T01:59:59', 'Ca 1'),
    ('2026-09-28T02:00:00', ''),
    ('2026-09-28T10:01:00', 'Ca 2'),
])
def test_rotation_does_not_switch_the_retained_shift_early(value, expected):
    datasets = punches('27/09/2026') + punches('28/09/2026')
    result = checkin.project(directory(rotation_cycle='Luân phiên (14 ngày)'), datasets, instant(value))[0]
    assert result['daily_shift'] == expected


@pytest.mark.parametrize('value, expected', [
    ('2026-09-16T01:59:59', 'Ca 1'),
    ('2026-09-16T02:00:00', ''),
    ('2026-09-16T10:01:00', 'Ca 2'),
])
def test_future_assignment_does_not_take_effect_in_previous_shift(value, expected):
    datasets = punches(WorkTimeName='Ca 1') + punches('16/09/2026')
    result = checkin.project(directory('Ca 2', shift_start_date='16/09/2026'), datasets, instant(value))[0]
    assert result['daily_shift'] == expected


@pytest.mark.parametrize('value', ['2026-09-16T01:00:00', '2026-09-16T02:00:00'])
@pytest.mark.parametrize('datasets', [
    [],
    punches(MachineTimeCheckInStr='', MachineTimeCheckOutStr='23:50'),
    punches('16/09/2026', MachineTimeCheckInStr='00:30'),
    punches('14/09/2026'),
])
def test_no_fabricated_checkin_or_two_day_old_carryover(value, datasets):
    assert checkin.project(directory(), datasets, instant(value))[0]['daily_shift'] == ''


@pytest.mark.parametrize('value, allowed', [
    ('2026-09-16T00:00:00', True),
    ('2026-09-16T01:59:59', True),
    ('2026-09-16T02:00:00', False),
])
def test_booking_guard_accepts_only_unexpired_checkin(value, allowed):
    worker = worker_state(shift='Ca 2', assigned_shift='Ca 2', shift_checkin_date='2026-09-15')['employees'][0]
    if allowed:
        live._require_checked_in(worker, instant(value))
        # Do not reapply the 13:00 readiness gate to a shift from yesterday.
        assert not live._before_shift_ready(state_with(worker), worker, instant(value))
    else:
        with pytest.raises(HTTPException) as caught:
            live._require_checked_in(worker, instant(value))
        assert caught.value.status_code == 409


@pytest.mark.parametrize('value, expected', [
    ('2026-09-16T00:00:00', 'Ca 2'),
    ('2026-09-16T01:59:59', 'Ca 2'),
    ('2026-09-16T02:00:00', ''),
])
def test_manual_shift_survives_projection_and_daily_sync_until_two(value, expected):
    db = SettingsDatabase(worker_state(
        shift='Ca 2', manual_shift='Ca 2', manual_shift_date='2026-09-15', manual_shift_by='admin',
    ), directory=directory())
    db.datasets = punches()
    state, _ = live._read_state(db, instant(value))
    worker = state['employees'][0]
    assert worker['shift'] == expected
    assert ('manual_shift_date' in worker) == bool(expected)
    assert worker['assigned_shift'] == ('Ca 1' if expected else '')


def test_manual_shift_set_after_midnight_is_owned_by_previous_shift():
    now = instant('2026-09-16T01:00:00')
    state = worker_state(assigned_shift='Ca 1')
    live._apply_action(state, 'set_shift', {'employee_id': 'e1', 'shift': 'Ca 2'}, 'admin', now)
    worker = state['employees'][0]
    assert worker['manual_shift_date'] == '2026-09-15'
    live._apply_action(state, 'set_work_status', {'employee_id': 'e1', 'status': 'Đi làm'}, 'admin', now)
    assert worker['shift'] == 'Ca 2'
    # The calendar date for manual attendance/work-status is intentionally unchanged.
    assert worker['manual_work_status_date'] == '2026-09-16'


def test_daily_sync_can_use_shift_day_without_changing_leave_day():
    state = worker_state(shift='Ca 2', assigned_shift='Ca 1', manual_shift='Ca 2',
                         manual_shift_date='2026-09-15', manual_shift_by='admin')
    live._sync_daily(state, directory(), [], today='2026-09-16', shift_day='2026-09-15')
    assert state['employees'][0]['shift'] == 'Ca 2'
    live._sync_daily(state, directory(), [{'employee_name': 'Thanh Nhã', 'leave_reason': 'Nghỉ có phép'}],
                     today='2026-09-16', shift_day='2026-09-15')
    assert state['employees'][0]['work_status'] == 'Nghỉ phép'
    assert state['employees'][0]['shift'] == ''


@pytest.mark.parametrize('value, status', [('2026-09-16T01:59:59', 200), ('2026-09-16T02:00:00', 409)])
def test_booking_api_obeys_two_am_boundary(monkeypatch, value, status):
    freeze_clock(monkeypatch, instant(value))
    db = SettingsDatabase(worker_state(), directory=directory())
    db.datasets = punches()
    _, client = app_client(db)
    board = client.get('/v2/live-tour').json()
    response = client.post('/v2/live-tour/action', json={
        'action': 'booking', 'expected_revision': board['revision'], 'idempotency_key': 'overnight-booking',
        'payload': {'employee_id': 'e1', 'service': 'Body 90', 'room': '1.1'},
    })
    assert response.status_code == status, response.text


def test_manual_daily_sync_route_does_not_expire_override_at_midnight(monkeypatch):
    freeze_clock(monkeypatch, instant('2026-09-16T01:00:00'))
    db = SettingsDatabase(worker_state(shift='Ca 2', manual_shift='Ca 2',
        manual_shift_date='2026-09-15', manual_shift_by='admin'), directory=directory())
    db.datasets = punches()
    _, client = app_client(db)
    board = client.get('/v2/live-tour').json()
    response = client.post('/v2/live-tour/action', json={
        'action': 'sync_daily_status', 'expected_revision': board['revision'], 'idempotency_key': 'overnight-sync',
        'payload': {'today': '2099-01-01', 'shift_day': '2099-01-01'},
    })
    assert response.status_code == 200, response.text
    assert response.json()['records'][0]['Vào ca'] == 'Ca 2'
    assert db.stored['employees'][0]['manual_shift_date'] == '2026-09-15'


def test_refresh_restart_scheduler_and_conditional_poll_preserve_work(monkeypatch):
    clock = freeze_clock(monkeypatch, instant('2026-09-15T23:55:00'))
    state = worker_state(service='Body 90', room='1.1', status='Đang thực hiện',
                         duration=240, started_at=clock[0].isoformat(), tour_count=3, request_count=2)
    state['invoices'] = [{'bill_no': 'historic', 'total': 450000}]
    state['customers'] = [{'id': 'c1', 'name': 'Khách mẫu', 'combo_purchases': []}]
    db = SettingsDatabase(state, directory=directory())
    db.datasets = punches()
    _, first = app_client(db)
    response = first.get('/v2/live-tour')
    assert response.status_code == 200, response.text
    assert response.json()['records'][0]['Vào ca'] == 'Ca 1'
    saved = deepcopy(db.stored)
    for value in ['2026-09-16T00:00:00', '2026-09-16T01:59:59.999999']:
        clock[0] = instant(value)
        _, reopened = app_client(db)  # Fresh app/device, no in-memory attendance cache.
        response = reopened.get('/v2/live-tour?refresh=true')
        assert response.status_code == 200, response.text
        assert response.json()['records'][0]['Vào ca'] == 'Ca 1'
        assert response.json()['records'][0]['_shift_checkin_date'] == '2026-09-15'
    previous_revision = db.revision
    clock[0] = instant('2026-09-16T02:00:00')
    # Scheduler and first/explicit refresh share this locked projection path.
    _, revision = live._read_state(db, clock[0], for_update=True)
    assert revision == previous_revision + 1
    polled = first.get('/v2/live-tour', params={'known_revision': previous_revision}).json()
    assert polled['records'][0]['Vào ca'] == ''
    assert polled['revision'] == revision
    assert first.get('/v2/live-tour', params={'known_revision': revision}).json()['unchanged'] is True
    assert first.get('/v2/live-tour').json()['revision'] == revision  # Clearing is idempotent.
    for field in ('service', 'room', 'status', 'duration', 'started_at', 'stt', 'tour_count', 'request_count'):
        assert db.stored['employees'][0][field] == saved['employees'][0][field]
    for field in ('invoices', 'pending', 'customers', 'reports', 'idempotency'):
        assert db.stored[field] == saved[field]
    # A real check-in for the new day can open a new shift normally.
    clock[0] = instant('2026-09-16T10:01:00')
    db.datasets += punches('16/09/2026')
    refreshed = first.get('/v2/live-tour?refresh=true').json()
    assert refreshed['records'][0]['Vào ca'] == 'Ca 1'
    assert refreshed['records'][0]['_shift_checkin_date'] == '2026-09-16'


def test_midnight_auto_start_still_runs_with_yesterdays_checkin():
    state = worker_state(shift='Ca 2', assigned_shift='Ca 2', shift_checkin_date='2026-09-15',
        service='Body 90', room='1.1', status='Đang chờ', duration=90,
        booked_at=instant('2026-09-15T23:50:00').isoformat())
    live._auto_start_waiting(state, instant('2026-09-16T00:15:00'))
    assert state['employees'][0]['status'] == 'Đang thực hiện'
    assert state['employees'][0]['started_at'] == instant('2026-09-16T00:15:00').isoformat()


@pytest.mark.parametrize('value, status', [('2026-09-16T01:59:59', 200), ('2026-09-16T02:00:00', 409)])
def test_manual_override_without_face_id_has_the_same_booking_cutoff(monkeypatch, value, status):
    freeze_clock(monkeypatch, instant(value))
    db = SettingsDatabase(worker_state(shift='Ca 2', manual_shift='Ca 2',
        manual_shift_date='2026-09-15', manual_shift_by='admin'), directory=directory())
    _, client = app_client(db)
    board = client.get('/v2/live-tour').json()
    assert not db.stored['employees'][0]['assigned_shift']
    if status == 200:
        assert 'shift_checkin_date' not in db.stored['employees'][0]
    response = client.post('/v2/live-tour/action', json={
        'action': 'booking', 'expected_revision': board['revision'], 'idempotency_key': 'overnight-manual-booking',
        'payload': {'employee_id': 'e1', 'service': 'Body 90', 'room': '1.1'},
    })
    assert response.status_code == status, response.text


@pytest.mark.parametrize('value, allowed', [('2026-09-16T01:59:59', True), ('2026-09-16T02:00:00', False)])
def test_quick_checkout_cannot_reuse_expired_manual_shift_without_projection(value, allowed):
    # Quick checkout intentionally bypasses attendance projection to shorten
    # its critical section. The shared guard must reject stale manual evidence.
    from test_live_tour_quick_booking import scenario
    now = instant(value)
    state, payload = scenario()
    state['employees'][0].update(shift='Ca 2', assigned_shift='', manual_shift='Ca 2',
                                manual_shift_date='2026-09-15', manual_shift_by='admin')
    state['employees'][0].pop('shift_checkin_date', None)
    payload['quick_booking']['booked_at'] = now.isoformat()
    # Align this older reusable fixture's unrelated daily counters first.
    live._ensure_counter_day(state, now)
    before = deepcopy(state)
    if allowed:
        result = live._apply_action(state, 'quick_checkout', payload, 'admin', now)
        assert result['invoice']['total'] > 0
    else:
        with pytest.raises(HTTPException) as caught:
            live._apply_action(state, 'quick_checkout', payload, 'admin', now)
        assert caught.value.status_code == 409
        assert state == before  # No financial write when the shift is expired.


def test_scheduler_rolls_over_without_any_browser_request(monkeypatch):
    import asyncio

    clock = freeze_clock(monkeypatch, instant('2026-09-16T01:59:59'))
    ticks = []

    class OneTickEvent:
        stopped = False

        def clear(self): self.stopped = False
        def set(self): self.stopped = True
        def is_set(self): return self.stopped
        def wait(self, seconds):
            ticks.append(seconds)
            self.set()

    class InlineThread:
        def __init__(self, *, target, **kwargs): self.target = target
        def start(self): self.target()
        def join(self, timeout): pass

    monkeypatch.setattr(live, 'Event', OneTickEvent)
    monkeypatch.setattr(live, 'Thread', InlineThread)
    db = SettingsDatabase(worker_state(), directory=directory())
    db.datasets = punches()
    app, _ = app_client(db)

    async def one_startup_tick():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(one_startup_tick())
    assert db.stored['employees'][0]['shift'] == 'Ca 1'
    prior_revision = db.revision
    clock[0] = instant('2026-09-16T02:00:00')
    asyncio.run(one_startup_tick())
    assert db.stored['employees'][0]['shift'] == ''
    assert db.revision == prior_revision + 1
    assert ticks == [15, 15]


def test_first_boot_after_midnight_uses_previous_dated_attendance():
    db = SettingsDatabase(directory=directory())
    db.datasets = punches()
    state, _ = live._read_state(db, instant('2026-09-16T01:59:59'))
    assert state['employees'][0]['assigned_shift'] == 'Ca 1'
    assert state['employees'][0]['shift_checkin_date'] == '2026-09-15'

from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from vera_web_v2_live_tour_attendance import AttendanceBreakReader, sync_breaks
from test_live_tour_backend import employee, RouteIdentity
from test_live_tour_server_only import SettingsDatabase

NOW = datetime(2026, 9, 12, 16, 0, tzinfo=live.VN_TZ)


def record(**extra):
    return {'date': '12/09/2026', 'employee_name': 'An', 'break_out': '15:30:00',
            'break_in': '', 'break_return_deadline_iso': '2026-09-12T16:15:00',
            'break_planned_minutes': 45, 'break_source': 'TimeSoft FaceID', **extra}


def board():
    worker = employee('e1', 'An')
    worker.update(username='An', full_name='Nguyễn An', appointment='Khách 18h', sort_index=3)
    state = live._empty_state(NOW)
    state["employees"] = [worker]
    live._ensure_counter_day(state, NOW)
    return state


def test_open_completed_and_repeat_preserve_service_and_ledgers():
    state = board()
    worker = state['employees'][0]
    worker.update(service='Body', status='Đang thực hiện', room='1.1', started_at=NOW.isoformat())
    original = deepcopy(state)
    sync_breaks(state, [record()], NOW)
    shown = live._employee_record(worker, NOW)
    assert shown['TG nghỉ còn lại'] == 15  # Chấm công's 45m rule, not 90m.
    assert shown['_attendance_break_active'] is True
    assert shown['Giờ ra'] == '2026-09-12T15:30:00+07:00'
    assert live._employee_record(worker, NOW + timedelta(minutes=20))['TG nghỉ còn lại'] == -5
    snapshot = deepcopy(state)
    sync_breaks(state, [record()], NOW + timedelta(minutes=1))
    assert state == snapshot  # No ticking writes/revisions.
    sync_breaks(state, [record(break_in='15:59:00')], NOW)
    shown = live._employee_record(worker, NOW)
    assert shown['Giờ vào'] == '2026-09-12T15:59:00+07:00'
    assert shown['TG nghỉ còn lại'] == 0 and not shown['_attendance_break_active']
    assert shown['_break_countdown_deadline'] == ''
    for field in ('service', 'status', 'room', 'started_at', 'appointment', 'sort_index'):
        assert worker[field] == original['employees'][0][field]
    assert {k: v for k, v in state.items() if k != 'employees'} == {k: v for k, v in original.items() if k != 'employees'}
    sync_breaks(state, [record()], NOW)
    assert worker['clock_in']  # Incomplete cache cannot reopen a completed break.


def test_break_metric_counts_unique_people_who_resting_and_currently_resting():
    state = live._empty_state(NOW)
    state['employees'] = []
    attendance_rows = []
    for index in range(1, 6):
        worker = employee(f'e{index}', f'Nhân viên {index}')
        worker.update(username=f'nv{index}', full_name=f'Nhân viên {index}')
        state['employees'].append(worker)
        attendance_rows.append(record(
            employee_name=f'Nhân viên {index}',
            break_out=f'15:{20 + index:02d}:00',
            break_in='15:50:00' if index == 1 else '',
        ))

    sync_breaks(state, attendance_rows, NOW)
    metrics = live._metric_bucket(state['employees'], NOW)

    assert metrics['break_total_count'] == 5
    assert metrics['break_active_count'] == 4

    # Multiple manual rests still count as one employee, not multiple events.
    state['employees'][0]['break_count'] = 3
    assert live._metric_bucket(state['employees'], NOW)['break_total_count'] == 5


@pytest.mark.parametrize('patch', [
    {'date': '11/09/2026'}, {'employee_name': 'Unknown'}, {'break_out': 'invalid'},
    {'break_out': '17:00:00'}, {'break_in': '17:00:00'}, {'break_in': 'invalid'},
    {'break_return_deadline_iso': ''},
])
def test_invalid_future_or_other_day_facts_do_not_change_board(patch):
    state = board()
    before = deepcopy(state)
    sync_breaks(state, [record(**patch)], NOW)
    assert state == before


def test_missing_source_preserves_today_and_day_rollover_clears_only_owned_clocks():
    state = board()
    sync_breaks(state, [record()], NOW)
    saved = deepcopy(state)
    sync_breaks(state, [], NOW)
    assert state == saved
    sync_breaks(state, [], NOW + timedelta(days=1))
    assert not state['employees'][0]['clock_out']
    assert not state['employees'][0]['break_started_at']
    assert state['employees'][0]['appointment'] == 'Khách 18h'


def test_ambiguous_names_are_not_assigned_to_wrong_employee():
    state = board()
    other = employee('e2', 'Bình')
    other['full_name'] = 'Nguyễn An'
    state['employees'].append(other)
    original = deepcopy(state)
    sync_breaks(state, [record(employee_name='Nguyễn An')], NOW)
    assert state == original
    sync_breaks(state, [record()], NOW)
    assert state['employees'][0]['break_started_at']
    assert not other.get('break_started_at')


def test_attendance_active_break_blocks_booking_and_manual_return():
    state = board()
    sync_breaks(state, [record()], NOW)
    for action in ('booking', 'end_break'):
        with pytest.raises(HTTPException) as error:
            live._apply_action(state, action, {'employee_id': 'e1'}, 'letan', NOW)
        assert error.value.status_code == 409


@pytest.mark.parametrize('role', ['admin', 'letan', 'quanly'])
def test_authorized_manual_return_wins_until_next_day(monkeypatch, role):
    class OperatorIdentity(RouteIdentity):
        role: str = ''
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    monkeypatch.setattr(live, 'datetime', Clock)
    db = SettingsDatabase(board())
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda: db,
        current_identity=lambda: OperatorIdentity(role=role), require_feature=lambda *_: None,
        feature_allowed=lambda *_: True, identity_type=OperatorIdentity,
        attendance_reader=lambda *args: [record()])
    client = TestClient(app)
    loaded = client.get('/v2/live-tour').json()
    result = client.post('/v2/live-tour/action', json={
        'action': 'end_break', 'expected_revision': loaded['revision'],
        'idempotency_key': 'manual-end-' + role, 'payload': {'employee_id': 'e1'},
    })
    assert result.status_code == 200, result.text
    refreshed = client.get('/v2/live-tour').json()
    assert not refreshed['records'][0]['_attendance_break_active']
    worker = db.stored['employees'][0]
    assert worker['manual_break_end']['date'] == NOW.date().isoformat()
    tomorrow = NOW + timedelta(days=1)
    sync_breaks(db.stored, [record(date=tomorrow.strftime('%d/%m/%Y'),
        break_return_deadline_iso=tomorrow.replace(hour=16, minute=15).isoformat())], tomorrow)
    assert worker['break_started_at']
    assert 'manual_break_end' not in worker


def test_overdue_break_blocks_single_multi_and_quick_booking_until_return():
    state = board()
    state['employees'].append(employee('e2', 'Bình'))
    service = next(row for row in state['services'] if row['name'] == 'Body 90')
    payload = {'employee_id': 'e1', 'room': '1.1', 'service_id': service['id']}
    overdue = NOW + timedelta(minutes=30)
    live._ensure_counter_day(state, overdue)
    sync_breaks(state, [record()], overdue)
    before = deepcopy(state)
    for action, data in [
        ('booking', payload),
        ('multi_booking', {'bookings': [{**payload, 'employee_id': 'e2'}, {**payload, 'room': '1.2'}]}),
        ('quick_checkout', {'payment_method': 'TIỀN MẶT', 'quick_booking': {
            'employee_id': 'e1', 'room': '1.1', 'booked_at': overdue.isoformat(),
            'service_items': [{'service_id': service['id'], 'quantity': 1}],
        }}),
    ]:
        with pytest.raises(HTTPException) as error:
            live._apply_action(state, action, data, 'letan', overdue)
        assert error.value.status_code == 409
        assert state == before
    sync_breaks(state, [record(break_in='16:29:00')], overdue)
    live._apply_action(state, 'booking', payload, 'letan', overdue)
    assert state['employees'][0]['service'] == 'Body 90'


def test_shared_reader_reuses_results_and_invalidates_by_time_and_day():
    calls, ticks = [], [0]
    def source(conn, start, end):
        calls.append((start, end))
        return [record(private_profile='not cached')]
    reader = AttendanceBreakReader(source, clock=lambda: ticks[0])
    result = reader.read(None, NOW.date())
    result[0]['break_out'] = 'changed by caller'
    assert reader.read(None, NOW.date())[0]['break_out'] == '15:30:00'
    assert 'private_profile' not in reader.rows[0]
    assert len(calls) == 1
    ticks[0] = 11
    reader.read(None, NOW.date())
    reader.read(None, (NOW + timedelta(days=1)).date())
    assert len(calls) == 3
    reader.read(None, (NOW + timedelta(days=1)).date(), force=True)
    assert len(calls) == 4  # Mutations must recheck newly arrived FaceID.


def test_route_projects_persists_and_rejects_stale_revision(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    monkeypatch.setattr(live, 'datetime', Clock)
    db = SettingsDatabase(board())
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda: db,
        current_identity=lambda: RouteIdentity(), require_feature=lambda *_: None,
        feature_allowed=lambda *_: True, identity_type=RouteIdentity,
        attendance_reader=lambda *args: [record()])
    client = TestClient(app)
    old_revision = db.revision
    first = client.get('/v2/live-tour').json()
    assert first['records'][0]['TG nghỉ còn lại'] == 15
    assert db.stored['employees'][0]['clock_out'] == '2026-09-12T15:30:00+07:00'
    assert client.get('/v2/live-tour').json()['revision'] == first['revision']
    response = client.post('/v2/live-tour/action', json={
        'action': 'set_vip', 'expected_revision': old_revision, 'idempotency_key': 'stale-break',
        'payload': {'employee_id': 'e1', 'vip': True},
    })
    assert response.status_code == 409


def test_canonical_attendance_open_punch_and_twenty_hour_cutoff(monkeypatch):
    import vera_web_v2_attendance_v42 as attendance
    from vera_web_v2_attendance_break_window import _enhance_break_payload, _pick_break_pair
    monkeypatch.setattr(attendance, '_pick_break_pair', _pick_break_pair)
    punches = [datetime(2026, 9, 12, 10), datetime(2026, 9, 12, 19, 30)]
    result = _enhance_break_payload(attendance._break_from_punches, punches,
        work_day=NOW.date(), representative={'WorkTimeName': 'Ca 1'},
        cfg={'break_enabled': True, 'break_planned_minutes': 90})
    state = board()
    sync_breaks(state, [{'date': '12/09/2026', 'employee_name': 'An', **result}], NOW.replace(hour=19, minute=45))
    shown = live._employee_record(state['employees'][0], NOW.replace(hour=19, minute=45))
    assert shown['TG nghỉ còn lại'] == 15
    assert shown['_break_countdown_deadline'] == '2026-09-12T20:00:00+07:00'


def test_booking_rechecks_faceid_that_arrives_after_board_was_loaded(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    monkeypatch.setattr(live, 'datetime', Clock)
    db, rows = SettingsDatabase(board()), []
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda: db,
        current_identity=lambda: RouteIdentity(), require_feature=lambda *_: None,
        feature_allowed=lambda *_: True, identity_type=RouteIdentity,
        attendance_reader=lambda *args: rows)
    client = TestClient(app)
    loaded = client.get('/v2/live-tour').json()
    rows.append(record())
    service = next(row for row in db.stored['services'] if row['name'] == 'Body 90')
    request = {'action': 'booking', 'expected_revision': loaded['revision'],
               'idempotency_key': 'booking-before-faceid',
               'payload': {'employee_id': 'e1', 'room': '1.1', 'service_id': service['id']}}
    assert client.post('/v2/live-tour/action', json=request).status_code == 409
    assert not db.stored['employees'][0]['service']
    refreshed = client.get('/v2/live-tour').json()
    request['expected_revision'] = refreshed['revision']
    blocked = client.post('/v2/live-tour/action', json=request)
    assert blocked.status_code == 409 and 'nghỉ giữa ca' in blocked.text

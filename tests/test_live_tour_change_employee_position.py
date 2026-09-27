"""A replaced standard-tour worker regains their pre-start board position."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with


def order(state, now=NOW):
    return [row['_employee_id'] for row in live._state_response(state, 1, now)['records']]


def book_and_start(state, employee_id, minute=0, room='1.1'):
    now = NOW + timedelta(minutes=minute)
    live._apply_action(state, 'booking', {
        'employee_id': employee_id, 'service': 'Body 90', 'room': room, 'request': '',
    }, 'test', now)
    live._apply_action(state, 'start', {'employee_id': employee_id}, 'test', now)


def replace(state, source='e1', target='e2', minute=80):
    live._apply_action(state, 'change_employee', {
        'employee_id': source, 'target_employee_id': target,
    }, 'test', NOW + timedelta(minutes=minute))


@pytest.mark.parametrize('mode', ['off', 'active'])
@pytest.mark.parametrize('prior_minutes', [None, 30])
def test_standard_replacement_returns_first_worker_to_first_slot(monkeypatch, mode, prior_minutes):
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE', mode)
    workers = [employee(f'e{i}', f'Test Worker {i}') for i in range(1, 4)]
    for index, row in enumerate(workers):
        row['board_started_at'] = '' if prior_minutes is None else live._iso(NOW - timedelta(minutes=prior_minutes-index))
        row['board_yc_started_at'] = live._iso(NOW - timedelta(days=1))
    state = state_with(*workers)
    starts = live._board_starts(workers[0])
    unrelated = deepcopy(workers[2])
    assert order(state) == ['e1', 'e2', 'e3']
    book_and_start(state, 'e1')
    assert order(state) == ['e2', 'e3', 'e1']
    replace(state)
    assert order(state) == ['e1', 'e2', 'e3']
    assert live._board_starts(workers[0]) == starts
    assert workers[2] == unrelated  # No board-wide writes when the old clock restores the slot.
    assert workers[0]['tour_count'] == 0 and workers[1]['tour_count'] == 1
    assert workers[1]['started_at'] == live._iso(NOW)
    assert not workers[0]['service'] and not workers[0]['room']
    # Refresh/reload must not put the replaced employee back at the bottom.
    restored = live._normalize_state(json.loads(json.dumps(state)), NOW + timedelta(minutes=81))
    assert order(restored) == ['e1', 'e2', 'e3']


@pytest.mark.parametrize('mode', ['off', 'active'])
def test_exact_original_slot_after_other_worker_starts_and_repeated_replacement(monkeypatch, mode):
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE', mode)
    workers = [employee(f'e{i}', f'Test Worker {i}') for i in range(1, 5)]
    for index, row in enumerate(workers):
        row['board_started_at'] = live._iso(NOW - timedelta(minutes=40-index*10))
    state = state_with(*workers)
    book_and_start(state, 'e2')
    book_and_start(state, 'e1', minute=1, room='2.1')
    assert order(state) == ['e3', 'e4', 'e2', 'e1']
    others_before = [item for item in order(state) if item != 'e2']
    replace(state, 'e2', 'e4')
    assert order(state).index('e2') == 1
    assert [item for item in order(state) if item != 'e2'] == others_before
    assert state['manual_order_active'] is True
    target_slot = order(state).index('e4')
    target_before = deepcopy(workers[3]['pre_start_tour_position'])
    replace(state, 'e4', 'e3', minute=81)
    assert order(state).index('e4') == target_before['board_index']
    assert target_slot != target_before['board_index']  # Its own pre-transfer slot, not the first worker's.
    assert workers[3]['tour_count'] == 0 and workers[2]['tour_count'] == 1
    assert workers[2]['started_at'] == live._iso(NOW)
    assert live._remaining(workers[2], NOW + timedelta(minutes=81))[0] == 9
    book_and_start(state, 'e4', minute=82, room='4')
    assert order(state).index('e2') < order(state).index('e4')


@pytest.mark.parametrize('prior_minutes', [None, 30])
def test_booking_started_before_update_restores_saved_display_clock(prior_minutes):
    workers = [employee(f'e{i}', f'Test Worker {i}') for i in range(1, 4)]
    for index, row in enumerate(workers):
        row['board_started_at'] = '' if prior_minutes is None else live._iso(NOW - timedelta(minutes=prior_minutes-index))
    state = state_with(*workers)
    before = live._employee_record(workers[0], NOW)['TG bắt đầu thực hiện']
    book_and_start(state, 'e1')
    workers[0]['pre_start_tour_position'].pop('board_started_at', None)
    replace(state)
    assert order(state) == ['e1', 'e2', 'e3']
    assert live._employee_record(workers[0], NOW)['TG bắt đầu thực hiện'] == before

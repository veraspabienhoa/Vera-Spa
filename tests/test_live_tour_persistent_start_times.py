from copy import deepcopy
from datetime import timedelta

import pytest

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with


def test_booking_start_finish_and_next_booking_preserve_both_board_times():
    worker = employee('e1', 'An')
    worker.update(board_started_at=(NOW - timedelta(days=1)).isoformat(),
                  board_yc_started_at=(NOW - timedelta(days=2)).isoformat())
    state = state_with(worker)
    original = live._board_starts(worker)
    payload = {'employee_id': 'e1', 'service': 'Body 90', 'room': '1.1', 'request': 'YC'}
    live._apply_action(state, 'booking', payload, 'admin', NOW)
    assert live._board_starts(worker) == original
    live._apply_action(state, 'start', {'employee_id': 'e1'}, 'admin', NOW)
    assert worker['board_started_at'] == original['board_started_at']
    assert worker['board_yc_started_at'] == live._iso(NOW)
    started = live._board_starts(worker)
    live._apply_action(state, 'finish_to_pending', {'employee_id': 'e1'}, 'admin', NOW + timedelta(minutes=90))
    live._apply_action(state, 'booking', {**payload, 'request': ''}, 'admin', NOW + timedelta(minutes=91))
    assert live._board_starts(worker) == started
    live._apply_action(state, 'cancel_booking', {'employee_id': 'e1'}, 'admin', NOW + timedelta(minutes=92))
    assert live._board_starts(worker) == started
    normalized = live._normalize_state(state, NOW + timedelta(days=1))
    live._ensure_counter_day(normalized, NOW + timedelta(days=1))
    assert live._board_starts(normalized['employees'][0]) == started


@pytest.mark.parametrize('direction,steps,position', [
    ('top', 1, None), ('bottom', 1, None), ('up', 1, None),
    ('up', 3, None), ('down', 3, None), ('up', 5, None),
    ('down', 5, None), ('position', 1, 3),
])
def test_reorder_changes_only_standard_board_time_using_final_neighbor(direction, steps, position):
    workers = [employee(f'e{i}', f'Worker {i}') for i in range(1, 9)]
    for index, worker in enumerate(workers):
        worker.update(board_started_at=live._iso(NOW - timedelta(minutes=80-index*10)),
                      board_yc_started_at=live._iso(NOW-timedelta(days=1)),
                      started_at=live._iso(NOW-timedelta(minutes=10)),
                      service='Body 90', room=f'{index+1}.1', duration=90, status='Đang thực hiện')
    state = state_with(*workers)
    before = deepcopy(workers)
    worker = workers[3]
    deadline = live._remaining(worker, NOW)
    live._apply_action(state, 'admin_reorder', {
        'employee_id': worker['id'], 'direction': direction, 'steps': steps, 'position': position,
    }, 'admin', NOW)
    ordered = live._ordered_employees(state['employees'], NOW)
    index = ordered.index(worker)
    neighbor = ordered[index-1] if index else ordered[1]
    expected = live._parse_datetime(neighbor['board_started_at']) + timedelta(seconds=1 if index else -1)
    assert worker['board_started_at'] == live._iso(expected)
    assert worker['board_yc_started_at'] == before[3]['board_yc_started_at']
    assert live._remaining(worker, NOW) == deadline
    for old in before:
        if old['id'] != worker['id']:
            current = next(row for row in ordered if row['id'] == old['id'])
            assert live._board_starts(current) == live._board_starts(old)


def test_restore_does_not_replace_current_board_times():
    worker = employee('e1', 'An')
    worker.update(board_started_at=live._iso(NOW-timedelta(days=2)), board_yc_started_at='')
    state = state_with(worker)
    backup = live._apply_action(state, 'backup', {}, 'admin', NOW)['backup']
    worker['board_started_at'] = live._iso(NOW)
    live._apply_action(state, 'restore', {'backup_id': backup['id']}, 'admin', NOW)
    assert state['employees'][0]['board_started_at'] == live._iso(NOW)

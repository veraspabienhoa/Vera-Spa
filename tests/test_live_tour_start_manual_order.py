from datetime import timedelta

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_cancel_booking import waiting


def prepared(request=''):
    source = waiting()
    for key in ('combo_purchase_id', 'combo_reserved_units', 'combo_reserved_components'):
        source.pop(key, None)
    source.update(name='Cẩm Nhung', request=request)
    earlier = employee('e2', 'Quỳnh Phương')
    earlier.update(last_assignment_display={'TG bắt đầu thực hiện': live._iso(NOW - timedelta(seconds=5))})
    leave = employee('e4', 'Nghỉ')
    leave['work_status'] = 'Nghỉ phép'
    state = state_with(source, earlier, employee('e3', 'Chưa thực hiện'), leave)
    live._apply_action(state, 'admin_reorder', {'employee_id': 'e1', 'direction': 'top'}, 'admin', NOW)
    return state, source


def ids(state):
    return [row['id'] for row in live._ordered_employees(state['employees'], NOW)]


def test_standard_start_resumes_time_order_after_manual_move():
    state, source = prepared()
    live._apply_action(state, 'start', {'employee_id': 'e1'}, 'admin', NOW)
    assert ids(state) == ['e3', 'e2', 'e1', 'e4']
    assert not any(row.get('manual_order') for row in state['employees'])
    assert source['pre_start_tour_position']['board_index'] == 0
    records = live._state_response(state, 1, NOW)['records']
    assert not any(row['_manual_order'] for row in records)


def test_yc_start_keeps_manual_order():
    state, _ = prepared('YC')
    before = ids(state)
    live._apply_action(state, 'start', {'employee_id': 'e1'}, 'admin', NOW)
    assert ids(state) == before


def test_replacement_restores_pre_start_manual_position():
    state, _ = prepared()
    live._apply_action(state, 'start', {'employee_id': 'e1'}, 'admin', NOW)
    live._apply_action(state, 'change_employee', {'employee_id': 'e1', 'target_employee_id': 'e3'}, 'admin', NOW + timedelta(minutes=80))
    assert ids(state)[0] == 'e1'
    assert ids(state)[-1] == 'e4'
    # A subsequent standard start can resume automatic order again.
    assert all(row.get('manual_order') for row in state['employees'])


def test_resource_start_invalidates_order_without_modifying_other_employees(monkeypatch):
    from copy import deepcopy
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE', 'active')
    state, source = prepared()
    other_rows = deepcopy(state['employees'][1:])
    live._apply_action(state, 'start', {'employee_id': 'e1'}, 'admin', NOW)
    assert state['manual_order_active'] is False
    assert state['employees'][1:] == other_rows
    public = live._state_response(state, 1, NOW)
    assert [row['_employee_id'] for row in public['records']] == ['e3', 'e2', 'e1', 'e4']
    assert not any(row['_manual_order'] for row in public['records'])
    assert source['pre_start_tour_position']['board_index'] == 0
    normalized = live._normalize_state(state, NOW)
    assert not any(row.get('manual_order') for row in normalized['employees'])


def test_new_manual_move_and_replacement_can_restore_order_in_resource_mode(monkeypatch):
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE', 'active')
    state, _ = prepared()
    live._apply_action(state, 'start', {'employee_id': 'e1'}, 'admin', NOW)
    live._apply_action(state, 'change_employee', {'employee_id':'e1','target_employee_id':'e3'}, 'admin', NOW + timedelta(minutes=80))
    assert state['manual_order_active'] is True
    assert ids(state)[0] == 'e1'
    # A new explicit manual move re-enables ordering after a prior invalidation.
    state['manual_order_active'] = False
    state = live._normalize_state(state, NOW)
    live._apply_action(state, 'admin_reorder', {'employee_id':'e2','direction':'top'}, 'admin', NOW)
    assert state['manual_order_active'] is True
    assert ids(state)[0] == 'e2'


def test_yc_start_does_not_reenable_invalidated_manual_order(monkeypatch):
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE', 'active')
    state, _ = prepared('YC')
    state['manual_order_active'] = False
    live._apply_action(state, 'start', {'employee_id':'e1'}, 'admin', NOW)
    assert state['manual_order_active'] is False
    assert not any(row['_manual_order'] for row in live._state_response(state, 1, NOW)['records'])

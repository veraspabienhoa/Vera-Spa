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
    live._apply_action(state, 'change_employee', {'employee_id': 'e1', 'target_employee_id': 'e3'}, 'admin', NOW + timedelta(seconds=30))
    assert ids(state)[0] == 'e1'
    assert ids(state)[-1] == 'e4'
    # A subsequent standard start can resume automatic order again.
    assert all(row.get('manual_order') for row in state['employees'])

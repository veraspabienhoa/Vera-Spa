"""Moving to the tail survives automatic ordering without changing service clocks."""
from copy import deepcopy
from datetime import timedelta

import pytest
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_cancel_booking import waiting


def board():
    first = waiting()
    for key in ('combo_purchase_id', 'combo_reserved_units', 'combo_reserved_components'):
        first.pop(key, None)
    first.update(name='A', board_started_at=live._iso(NOW - timedelta(hours=3)))
    second, tail, ngoc, leave = (employee('e2','B'), employee('e3','C'),
                                employee('e4','Ngọc Như'), employee('e5','Nghỉ phép'))
    second['board_started_at'] = live._iso(NOW - timedelta(hours=2))
    tail['board_started_at'] = live._iso(NOW - timedelta(hours=1))
    ngoc.update(board_started_at=live._iso(NOW - timedelta(hours=4)),
                started_at=live._iso(NOW - timedelta(minutes=10)), request='YC',
                board_yc_started_at=live._iso(NOW - timedelta(minutes=10)),
                duration=90, service='Body 90', room='3.1', status='Đang thực hiện')
    leave['work_status'] = 'Nghỉ phép'
    return state_with(first, second, tail, ngoc, leave), ngoc, tail


def automatic_ids(state, now=NOW):
    return [row['id'] for row in live._ordered_employees(state['employees'], now, manual_order_active=False)]


@pytest.mark.parametrize('with_leave',[False,True])
@pytest.mark.parametrize('resource_mode',['off','active'])
def test_bottom_adds_one_second_to_working_tail_then_standard_start_advances_one_place(monkeypatch,resource_mode,with_leave):
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE',resource_mode)
    state, ngoc, tail = board()
    if not with_leave:
        state['employees'] = [r for r in state['employees'] if r['id']!='e5']
    suffix = ['e5'] if with_leave else []
    before = deepcopy(ngoc)
    tail_clock = live._parse_datetime(tail['board_started_at'])
    live._apply_action(state,'admin_reorder',{'employee_id':'e4','direction':'bottom'},'admin',NOW)
    assert live._parse_datetime(ngoc['board_started_at']) == tail_clock + timedelta(seconds=1)
    assert automatic_ids(state)==['e1','e2','e3','e4']+suffix
    for key in ('started_at','duration','service','room','request','board_yc_started_at','tour_count','request_count'):
        assert ngoc[key]==before[key]
    live._apply_action(state,'start',{'employee_id':'e1'},'admin',NOW)
    public = live._state_response(live._normalize_state(deepcopy(state),NOW), 1, NOW)
    assert [r['_employee_id'] for r in public['records']]==['e2','e3','e4','e1']+suffix
    assert live._parse_datetime(ngoc['board_started_at'])==tail_clock+timedelta(seconds=1)


def test_empty_tail_clock_gets_persistent_fallback_and_next_start_can_pass_it():
    state, ngoc, _ = board()
    for row in state['employees']:
        row['board_started_at']=''
    live._apply_action(state,'admin_reorder',{'employee_id':'e4','direction':'bottom'},'admin',NOW)
    assert live._parse_datetime(ngoc['board_started_at'])==NOW+timedelta(seconds=1)
    assert automatic_ids(state)==['e1','e2','e3','e4','e5']
    live._apply_action(state,'start',{'employee_id':'e1'},'admin',NOW+timedelta(seconds=2))
    assert automatic_ids(state,NOW+timedelta(seconds=2))==['e2','e3','e4','e1','e5']


def test_tail_return_queue_clock_is_used_and_yc_start_preserves_order():
    state, ngoc, tail=board()
    tail[live.leave_return.MARKER]={'status':'queued','queue_at':live._iso(NOW-timedelta(minutes=30)), 'kind':'early'}
    live._apply_action(state,'admin_reorder',{'employee_id':'e4','direction':'bottom'},'admin',NOW)
    assert live._parse_datetime(ngoc['board_started_at'])==NOW-timedelta(minutes=30)+timedelta(seconds=1)
    prior=automatic_ids(state)
    state['employees'][0]['request']='YC'
    live._apply_action(state,'start',{'employee_id':'e1'},'admin',NOW)
    assert automatic_ids(state)==prior

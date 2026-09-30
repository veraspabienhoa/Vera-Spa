from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import subprocess

import pytest

import vera_live_tour_leave_return as returns
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with

DAY = NOW.replace(year=2026, month=9, day=27, hour=12, minute=0)

UNEXCUSED_REASONS = [
    'Về sớm CÓ phép', 'Về sớm KHÔNG phép', 'Về sớm CUỐI TUẦN CÓ phép',
    'Về sớm CUỐI TUẦN KHÔNG phép', 'Về sớm phát sinh',
    'Nghỉ KHÔNG phép', 'Nghỉ CUỐI TUẦN KHÔNG phép',
]


def fixture():
    workers = [employee(f'e{i}', f'Test {i}') for i in range(1, 6)]
    for i, worker in enumerate(workers):
        worker.update(username=worker['name'], role='nhanvien', roster_eligible=True,
                      board_started_at=live._iso(DAY - timedelta(days=2, minutes=10-i)))
    return state_with(*workers)


def directory(now, checked=()):
    return [dict(username=f'Test {i}', full_name=f'Full Test {i}', role='nhanvien', payload={},
                 work_shift='Ca 1', daily_shift='Ca 1' if i in checked else '',
                 shift_checkin_date=now.date().isoformat()) for i in range(1, 6)]


def leaves(reason='Nghỉ không phép'):
    return [dict(employee_name=f'Test {i}', leave_reason=reason, record_uid=f'leave-{i}',
                 leave_date=DAY.date(), id=10-i, source_row=i,
                 detail=f'Người Thứ {i} nghỉ không phép') for i in (3, 1, 2)]


def project(state, now, checked=(), records=()):
    rows = directory(now, checked)
    live._reconcile_roster(state, rows, live._new_directory_employee, today=now.date().isoformat())
    # These are yesterday's batch inputs, not today's work-status records.
    returns.sync_returns(state, rows, records, now, now.date()-timedelta(days=1), live._ordered_employees, live._employee_time_key)


def order(state, now):
    return [row['id'] for row in live._ordered_employees(state['employees'], now,
            manual_order_active=state.get('manual_order_active', True))]


@pytest.mark.parametrize('manual', [False, True])
@pytest.mark.parametrize('reason', UNEXCUSED_REASONS)
def test_batch_at_0300_without_checkin_and_never_repeated(manual, reason):
    state = fixture()
    for worker in state['employees']:
        worker['manual_order'] = manual
    clocks = [row['board_started_at'] for row in state['employees']]
    project(state, DAY)
    boundary = (DAY + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    project(state, boundary - timedelta(seconds=1), records=leaves(reason))
    assert order(state, boundary) == ['e1', 'e2', 'e3', 'e4', 'e5']
    project(state, boundary, records=leaves(reason))
    assert order(state, boundary) == ['e4', 'e5', 'e1', 'e2', 'e3']
    assert [row['board_started_at'] for row in state['employees']] == clocks
    snapshot = deepcopy(state)
    project(state, boundary + timedelta(hours=6), checked=(3, 2, 1), records=leaves(reason))
    assert state == snapshot
    assert all(not state[name] for name in ('invoices', 'reports', 'pending', 'combo_usage'))


@pytest.mark.parametrize('reason', ['Nghỉ CÓ phép', 'Nghỉ phát sinh', 'Nghỉ phép năm',
    'Đi trễ KHÔNG phép', 'Đi trễ CUỐI TUẦN KHÔNG phép',
    'Về sớm bệnh có giấy khám hoặc được quản lý duyệt'])
def test_only_seven_exact_reasons(reason):
    state = fixture()
    project(state, DAY)
    project(state, DAY + timedelta(days=1), records=leaves(reason))
    assert order(state, DAY) == ['e1', 'e2', 'e3', 'e4', 'e5']


def test_deploy_midday_waits_until_next_cutoff_and_no_old_backlog():
    state = fixture()
    project(state, DAY + timedelta(days=1), records=leaves())
    assert not any(returns.queue_clock(row) for row in state['employees'])
    project(state, DAY + timedelta(days=2), records=leaves())
    assert not any(returns.queue_clock(row) for row in state['employees'])


def test_empty_batch_is_final_even_if_leave_added_later():
    state = fixture()
    project(state, DAY)
    project(state, DAY + timedelta(days=1))
    before = deepcopy(state)
    project(state, DAY + timedelta(days=1, hours=2), records=leaves())
    assert state == before


def test_group_priority_and_correction_before_cutoff():
    state = fixture()
    project(state, DAY)
    records = leaves()
    records[0]['leave_reason'] = 'Về sớm CÓ phép'  # e3 before absence group
    records = [row for row in records if row['employee_name'] != 'Test 1']
    project(state, DAY + timedelta(days=1), records=records)
    assert order(state, DAY) == ['e1', 'e4', 'e5', 'e3', 'e2']


def ready_state():
    state = fixture()
    project(state, DAY)
    later = DAY + timedelta(days=1)
    project(state, later, checked=(1, 2, 3, 4, 5), records=leaves())
    return state, later + timedelta(minutes=1)


def test_admin_order_is_not_overwritten_by_later_projection():
    state, now = ready_state()
    live._apply_action(state, 'admin_reorder', {'employee_id': 'e1', 'direction': 'top'}, 'test', now)
    project(state, now + timedelta(minutes=5), records=leaves())
    assert order(state, now)[0] == 'e1'


def test_normal_turn_releases_position_and_no_requeue():
    state, now = ready_state()
    start(state, 'e1', now)
    assert not returns.queue_clock(state['employees'][0])
    project(state, now + timedelta(minutes=5), records=leaves())
    assert order(state, now)[-1] == 'e1'

def start(state, worker, now, requested=False):
    live._apply_action(state, 'booking', {'employee_id': worker, 'room': '1.1',
        'service': 'Body 90', 'request': 'YC' if requested else ''}, 'test', now)
    live._apply_action(state, 'start', {'employee_id': worker}, 'test', now)


def test_normal_service_continues_queue_but_requested_service_keeps_position():
    state, now = ready_state()
    start(state, 'e4', now)
    assert order(state, now) == ['e5', 'e1', 'e2', 'e3', 'e4']
    other, now = ready_state()
    start(other, 'e1', now, requested=True)
    assert returns.queue_clock(other['employees'][0])
    assert order(other, now) == ['e4', 'e5', 'e1', 'e2', 'e3']


def test_replacement_and_restart_restore_the_return_position_without_invoice():
    for action in ('change_employee', 'restart_booking'):
        state, now = ready_state()
        start(state, 'e1', now)
        assert state['employees'][0][returns.MARKER]['status'] == 'served'
        live._apply_action(state, action, {'employee_id': 'e1', 'target_employee_id': 'e4'},
                           'test', now + timedelta(minutes=80))
        assert state['employees'][0][returns.MARKER]['status'] == 'queued'
        assert order(state, now).index('e1') == 2
        assert not state['invoices']


def test_browser_sort_preserves_server_return_order_even_with_active_filter():
    state, now = ready_state()
    response = live._state_response(state, 1, now, can_operate=True, can_payment=True, can_admin=True, can_export=True)
    records = response['records']
    next(row for row in records if row['_employee_id'] == 'e3')['_tour_groups'].append('finishing')
    path = Path('web-v2/src/pages/LiveTourPage.jsx')
    source = path.read_text()
    sorter = source[source.index('function prioritizeRecords('):source.index('function shiftBucket(')]
    script = 'import {tourStartOrder} from ' + json.dumps(Path('web-v2/src/lib/liveTourOrder.js').resolve().as_uri()) + ';\n'
    script += 'const hasGroup=(r,k)=>r._tour_groups.includes(k), findColumn=()=>"TG bắt đầu thực hiện", cellValue=(r,c)=>r[c];\n'
    script += sorter + '\nconst records=' + json.dumps(records) + ';\n'
    script += 'console.log(JSON.stringify(prioritizeRecords(records,[],"finishing").map(r=>r._employee_id)));'
    result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == ['e4', 'e5', 'e1', 'e2', 'e3']




def test_duplicate_identity_and_ineligible_roster_are_not_guessed():
    state = fixture()
    project(state, DAY)
    now = DAY + timedelta(days=1)
    rows = directory(now)
    rows[0]['full_name'] = rows[1]['full_name'] = 'Duplicate'
    state['employees'][2]['roster_eligible'] = False
    records = leaves()
    for row in records:
        if row['employee_name'] != 'Test 3':
            row['employee_name'] = 'Duplicate'
    returns.sync_returns(state, rows, records, now, DAY.date(), live._ordered_employees, live._employee_time_key)
    assert not any(returns.queue_clock(row) for row in state['employees'])


def test_next_day_expires_prior_marker_without_carrying_absence_forward():
    state, now = ready_state()
    project(state, now + timedelta(days=1), records=leaves())
    assert not any(returns.queue_clock(row) for row in state['employees'])

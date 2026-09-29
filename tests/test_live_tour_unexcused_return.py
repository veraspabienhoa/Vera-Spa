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
    'Nghỉ không phép', 'Đi trễ không phép', 'Về sớm không phép',
    'Nghỉ CUỐI TUẦN KHÔNG phép', 'Đi trễ CUỐI TUẦN KHÔNG phép',
    'Về sớm CUỐI TUẦN KHÔNG phép',
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
    live._sync_daily(state, rows, records, automatic=True, today=now.date().isoformat())
    returns.sync_returns(state, rows, records, now, (now-timedelta(hours=5)).date(), live._ordered_employees, live._employee_time_key)


def order(state, now):
    return [row['id'] for row in live._ordered_employees(state['employees'], now,
            manual_order_active=state.get('manual_order_active', True))]


@pytest.mark.parametrize('days', [1, 2, 9])
@pytest.mark.parametrize('manual', [False, True])
@pytest.mark.parametrize('reason', UNEXCUSED_REASONS)
def test_returning_group_moves_once_to_bottom_in_original_ordinal(days, manual, reason):
    state = fixture()
    if manual:
        for row in state['employees']:
            row['manual_order'] = True
    original_clocks = [row['board_started_at'] for row in state['employees']]
    project(state, DAY, records=leaves(reason))
    later = DAY + timedelta(days=days)
    project(state, later)  # Midnight/daily rollover without a check-in is not a return.
    assert all(row[returns.MARKER]['status'] == 'absent' for row in state['employees'][:3])
    project(state, later, checked=(1, 2, 3, 4, 5))
    assert order(state, later) == ['e4', 'e5', 'e1', 'e2', 'e3']
    assert [row['board_started_at'] for row in state['employees']] == original_clocks
    before = deepcopy(state)
    project(state, later + timedelta(minutes=5), checked=(1, 2, 3, 4, 5))
    assert state == before
    assert not any(state[name] for name in ('invoices', 'pending', 'reports', 'combo_usage'))


@pytest.mark.parametrize('reason', ['Nghỉ CÓ phép', 'Nghỉ phép năm', 'Nghỉ phát sinh',
                                  'Đi trễ có phép',
                                  'Đi trễ CUỐI TUẦN CÓ phép'])
def test_other_leave_types_never_get_return_queue_penalty(reason):
    state = fixture()
    project(state, DAY, records=leaves(reason))
    later = DAY + timedelta(days=1)
    project(state, later, checked=(1, 2, 3, 4, 5))
    assert order(state, later) == ['e1', 'e2', 'e3', 'e4', 'e5']
    assert not any(returns.MARKER in row for row in state['employees'])


@pytest.mark.parametrize('reason', UNEXCUSED_REASONS)
def test_reverse_checkins_across_ticks_and_days_keep_unserved_cohort_order(reason):
    state = fixture()
    project(state, DAY, records=leaves(reason))
    later = DAY + timedelta(days=1)
    project(state, later, checked=(3, 4, 5))
    project(state, later + timedelta(minutes=5), checked=(2, 3, 4, 5))
    project(state, later + timedelta(days=1), checked=(1, 2, 3, 4, 5))
    assert order(state, later) == ['e4', 'e5', 'e1', 'e2', 'e3']


def test_weekend_source_order_and_duplicate_identity_are_safe():
    state = fixture()
    records = leaves('Nghỉ CUỐI TUẦN KHÔNG phép')
    for row in records:
        row['detail'] = ''  # Weekend surcharge off still has a stable ordinal.
    project(state, DAY, records=records)
    assert [row[returns.MARKER]['ordinal'] for row in state['employees'][:3]] == [1, 2, 3]
    rows = directory(DAY)
    rows[0]['full_name'] = rows[1]['full_name'] = 'Duplicate'
    untouched = fixture()
    returns.sync_returns(untouched, rows, [{'employee_name': 'Duplicate', 'leave_reason': 'Nghỉ không phép'}],
                         DAY, DAY.date(), live._ordered_employees, live._employee_time_key)
    assert not any(returns.MARKER in row for row in untouched['employees'])


def test_same_day_correction_cancels_pending_placement_and_missing_roster_is_ignored():
    state = fixture()
    project(state, DAY, records=leaves())
    project(state, DAY + timedelta(minutes=5), records=leaves('Nghỉ CÓ phép'))
    assert not any(returns.MARKER in row for row in state['employees'])
    state['employees'][0]['roster_eligible'] = False
    returns.sync_returns(state, directory(DAY), leaves(), DAY, DAY.date(), live._ordered_employees, live._employee_time_key)
    assert returns.MARKER not in state['employees'][0]


def ready_state():
    state = fixture()
    project(state, DAY, records=leaves())
    later = DAY + timedelta(days=1, minutes=5)
    project(state, later, checked=(1, 2, 3, 4, 5))
    return state, later + timedelta(minutes=1)


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


def test_manual_assignment_allows_return_and_admin_can_override_once():
    state = fixture()
    project(state, DAY, records=leaves())
    now = DAY + timedelta(days=1)
    worker = state['employees'][0]
    worker.update(manual_shift='Ca 1', manual_shift_date=now.date().isoformat(), shift='Ca 1')
    project(state, now)
    assert returns.queue_clock(worker)
    live._apply_action(state, 'admin_reorder', {'employee_id': 'e1', 'direction': 'top'}, 'test', now)
    assert not returns.queue_clock(worker)
    project(state, now + timedelta(minutes=5))
    assert order(state, now)[0] == 'e1'


@pytest.mark.parametrize('correction', ['delete', 'approved', 'renamed'])
@pytest.mark.parametrize('reason', UNEXCUSED_REASONS)
def test_historical_correction_is_rechecked_before_placement(correction, reason):
    state = fixture()
    project(state, DAY, records=leaves(reason))
    now = DAY + timedelta(days=2)
    records = leaves(reason)
    if correction == 'delete':
        records = [row for row in records if row['employee_name'] != 'Test 1']
    else:
        row = next(row for row in records if row['employee_name'] == 'Test 1')
        row['leave_reason' if correction == 'approved' else 'employee_name'] = 'Nghỉ CÓ phép' if correction == 'approved' else 'Unknown'
    rows = directory(now, (1, 2, 3, 4, 5))
    live._reconcile_roster(state, rows, live._new_directory_employee, today=now.date().isoformat())
    live._sync_daily(state, rows, [], automatic=True, today=now.date().isoformat())
    returns.sync_returns(state, rows, [], now, now.date(), live._ordered_employees, live._employee_time_key, records)
    assert returns.MARKER not in state['employees'][0]
    assert order(state, now) == ['e1', 'e4', 'e5', 'e2', 'e3']


@pytest.mark.parametrize('reason', UNEXCUSED_REASONS)
def test_early_morning_previous_leave_day_does_not_count_as_return(reason):
    state = fixture()
    project(state, DAY, records=leaves(reason))
    now = (DAY + timedelta(days=1)).replace(hour=4)
    project(state, now, checked=(1, 2, 3), records=leaves(reason))
    assert all(row[returns.MARKER]['status'] == 'absent' for row in state['employees'][:3])


@pytest.mark.parametrize('weekend', [False, True])
def test_mixed_unexcused_group_waits_for_later_day_and_keeps_source_order(weekend):
    state = fixture()
    records = leaves()
    reasons = UNEXCUSED_REASONS[3:] if weekend else UNEXCUSED_REASONS[:3]
    for row in records:
        row['leave_reason'] = reasons[row['source_row'] - 1]
        row['detail'] = ''
    # Late/early employees may already have checked in on the violation day.
    project(state, DAY, checked=(1, 2, 3, 4, 5), records=records)
    assert all(row[returns.MARKER]['status'] == 'absent' for row in state['employees'][:3])
    assert not any(returns.queue_clock(row) for row in state['employees'])
    later = DAY + timedelta(days=1)
    project(state, later, checked=(3, 4, 5))
    project(state, later + timedelta(minutes=5), checked=(2, 3, 4, 5))
    project(state, later + timedelta(minutes=10), checked=(1, 2, 3, 4, 5))
    assert order(state, later) == ['e4', 'e5', 'e3', 'e1', 'e2']
    before = deepcopy(state)
    project(state, later + timedelta(minutes=15), checked=(1, 2, 3, 4, 5))
    assert state == before


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


@pytest.mark.parametrize('reason', ['Về sớm CÓ phép', 'Về sớm KHÔNG phép', 'Về sớm CUỐI TUẦN CÓ phép', 'Về sớm CUỐI TUẦN KHÔNG phép', 'Về sớm phát sinh'])
@pytest.mark.parametrize('manual', [False, True])
def test_early_returns_precede_unexcused_returns(reason, manual):
    state = fixture()
    for worker in state['employees']:
        worker['manual_order'] = manual
    records = leaves()
    records[0]['leave_reason'] = reason  # e3: early, e1/e2: unexcused
    project(state, DAY, records=records)
    later = DAY + timedelta(days=1)
    project(state, later, checked=(1, 2, 4, 5))
    project(state, later + timedelta(minutes=1), checked=(1, 2, 3, 4, 5))
    assert order(state, later) == ['e4', 'e5', 'e3', 'e1', 'e2']

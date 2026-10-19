"""Directory edits must refresh fixed-shift classification without altering work."""
from vera_web_v2_live_tour_roster import reconcile


def test_roster_retains_raw_shift_for_new_and_existing_workers():
    state = {'employees': [], 'pending': []}
    directory = [{'username': 'Synthetic', 'role': 'leader', 'payload': {},
        'work_shift': 'Cố định Ca 1 (10:00 - 23:00)', 'rotation_cycle': '',
        'scheduled_week_shift': 'Ca 1', 'scheduled_next_shift': 'Ca 1'}]
    make = lambda row, i: {'id': str(i), 'name': row['username'], 'username': row['username']}
    assert reconcile(state, directory, make, today='2026-10-19')
    worker = state['employees'][0]
    assert worker['work_shift'] == directory[0]['work_shift']
    assert worker['rotation_cycle'] == ''
    worker.update(service='Active service', status='Đang thực hiện', manual_shift='Ca 2', manual_shift_date='2026-10-19')
    directory[0].update(work_shift='Ca 1', rotation_cycle='Theo chu kỳ Tuần')
    assert reconcile(state, directory, make, today='2026-10-19')
    assert worker['work_shift'] == 'Ca 1'
    assert worker['rotation_cycle'] == 'Theo chu kỳ Tuần'
    assert worker['service'] == 'Active service'
    assert worker['shift'] == 'Ca 2'
    directory[0].update(work_shift='Cố định Ca 1 (10:00 - 23:00)', rotation_cycle='')
    reconcile(state, directory, make, today='2026-10-19')
    assert worker['work_shift'] == directory[0]['work_shift']
    assert worker['rotation_cycle'] == ''


def test_board_record_exposes_original_shift_separately_from_current_shift():
    import vera_web_v2_live_tour as live
    from test_live_tour_backend import employee, NOW
    worker = employee('e1', 'Synthetic')
    worker.update(work_shift='Cố định Ca 1 (10:00 - 23:00)', rotation_cycle='', shift='Ca 1')
    record = live._employee_record(worker, NOW)
    assert record['_work_shift'] == worker['work_shift']
    assert record['_rotation_cycle'] == ''

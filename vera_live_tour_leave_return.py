"""One-shot next-day queue placement for recorded unexcused attendance.

Called only by the existing exclusive daily projection. No I/O or money writes.
"""
from datetime import datetime
import re

from vera_progressive_penalty import canonical_reason
from vera_web_v2_live_tour_roster import key

MARKER = 'unexcused_leave_return'


def return_kind(reason):
    if key(reason).startswith('ve som'):
        return 'early'
    return 'unexcused' if canonical_reason(reason) is not None else ''


def queue_clock(worker):
    marker = worker.get(MARKER) or {}
    return marker.get('queue_at', '') if marker.get('status') == 'queued' else ''


def queue_order(worker):
    marker = worker.get(MARKER) or {}
    return (0 if marker.get('kind') == 'early' else 1, marker.get('day', ''), marker.get('ordinal', 0)) if queue_clock(worker) else (0, '', 0)


def release(worker, status='served'):
    if queue_clock(worker):
        worker[MARKER]['status'] = status


def pending_source_ids(state, leave_day):
    return sorted({marker['record_id'] for worker in state['employees']
                   if (marker := worker.get(MARKER) or {}).get('status') == 'absent'
                   and marker.get('day', str(leave_day)) < str(leave_day)
                   and isinstance(marker.get('record_id'), int)})


def sync_returns(state, directory, leaves, now, leave_day, ordered_employees, time_key, history_leaves=None):
    today, day = now.date().isoformat(), str(leave_day)
    by_user = {key(row['username']): row for row in directory if row.get('username')}
    owners = {}
    for username, row in by_user.items():
        owners.setdefault(key(row.get('full_name')), set()).add(username)
    history = {row['id']: row for row in (history_leaves or [])}
    # Same source ordering as the canonical Người Thứ N rebalance. The ordinal
    # remains deterministic on weekends even when the monetary surcharge is off.
    indexed = list(enumerate(leaves))
    indexed.sort(key=lambda pair: (pair[1].get('source_row') is None,
                                  pair[1].get('source_row') or 0,
                                  pair[1].get('id') or pair[0]))
    absent, ordinal = {}, 0
    for _, row in indexed:
        if not return_kind(row.get('leave_reason') or row.get('leave_type')):
            continue
        if row.get('leave_date') and str(row['leave_date']) != day:
            continue
        ordinal += 1
        name = key(row.get('employee_name'))
        matches = owners.get(name, set())
        username = name if name in by_user else next(iter(matches)) if len(matches) == 1 else ''
        if not username or username in absent:
            continue
        explicit = re.match(r'^nguoi thu\s+(\d+)\b', key(row.get('detail')))
        absent[username] = {'day': day, 'record_uid': str(row.get('record_uid') or row.get('id') or ''),
                            'record_id': row.get('id'), 'kind': return_kind(row.get('leave_reason') or row.get('leave_type')),
                            'ordinal': max(1, int(explicit.group(1))) if explicit else ordinal}
    ready = []
    for worker in state['employees']:
        username = key(worker.get('username') or worker.get('name'))
        if worker.get('roster_eligible') is False or username not in by_user:
            continue
        marker = worker.get(MARKER) or {}
        source = absent.get(username)
        if source and (not marker or source['day'] >= marker.get('day', '')):
            if source['day'] != marker.get('day'):
                worker[MARKER] = marker = {**source, 'status': 'absent'}
            elif marker.get('status') == 'absent':
                marker.update(source)
        elif marker.get('day') == day and marker.get('status') == 'absent':
            # A same-day correction/deletion must not leave a stale penalty.
            worker.pop(MARKER, None)
            continue
        if marker.get('status') != 'absent' or marker.get('day', day) >= day:
            continue
        if history_leaves is not None and marker.get('record_id') is not None:
            record = history.get(marker['record_id']) or {}
            source_name = key(record.get('employee_name'))
            matches = owners.get(source_name, set())
            source_user = source_name if source_name in by_user else next(iter(matches)) if len(matches) == 1 else ''
            if (source_user != username or str(record.get('leave_date')) != marker['day']
                    or not return_kind(record.get('leave_reason') or record.get('leave_type'))):
                worker.pop(MARKER, None)
                continue
            marker['kind'] = return_kind(record.get('leave_reason') or record.get('leave_type'))
            explicit = re.match(r'^nguoi thu\s+(\d+)\b', key(record.get('detail')))
            if explicit:
                marker['ordinal'] = max(1, int(explicit.group(1)))
        row = by_user[username]
        checked_in = row.get('shift_checkin_date') == today and row.get('daily_shift') in {'Ca 1', 'Ca 2'}
        assigned_by_admin = worker.get('manual_shift_date') == today and worker.get('shift') in {'Ca 1', 'Ca 2'}
        if key(worker.get('work_status')) != 'di lam' or not (checked_in or assigned_by_admin):
            continue
        # A projection arriving after a normal turn has started must not put
        # that employee back into the waiting queue for the same absence.
        started = str(worker.get('started_at') or '')
        if started[:10] > marker['day'] and key(worker.get('request')) != 'yc' and worker.get('service'):
            marker['status'] = 'served'
            continue
        ready.append(worker)
    if not ready:
        return
    ordered = ordered_employees(state['employees'], now, manual_order_active=state.get('manual_order_active', True))
    cohorts = {worker[MARKER]['day'] for worker in ready}
    ready_ids = {worker['id'] for worker in ready}
    # Check-ins may arrive in reverse order or in separate projection ticks.
    # Keep the still-unserved members of each returning cohort together.
    group = [worker for worker in ordered if worker['id'] in ready_ids or (
        queue_clock(worker) and worker[MARKER]['day'] in cohorts
        and worker.get('roster_eligible') is not False and key(worker.get('work_status')) == 'di lam')]
    anchor = max(int(now.timestamp()), max((time_key(worker, now)[2] for worker in ordered), default=0)) + 1
    queued_at = datetime.fromtimestamp(anchor, now.tzinfo).replace(microsecond=0).isoformat()
    for worker in group:
        worker[MARKER].update(status='queued', queue_at=queued_at, returned_day=today)
    group.sort(key=lambda worker: (*queue_order(worker), str(worker['id'])))
    if state.get('manual_order_active', True) and any(worker.get('manual_order') for worker in ordered):
        group_ids = {worker['id'] for worker in group}
        for index, worker in enumerate([row for row in ordered if row['id'] not in group_ids] + group):
            worker.update(sort_index=index, manual_order=True)

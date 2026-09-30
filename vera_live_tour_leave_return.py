"""Once-daily queue placement at 03:00 Vietnam time, under the board lock."""
from datetime import timedelta
import re

from vera_web_v2_live_tour_roster import key

MARKER = 'unexcused_leave_return'
DAILY_MARKER = 'leave_queue_0300_v1'
EARLY = {'ve som co phep', 've som khong phep', 've som cuoi tuan co phep',
         've som cuoi tuan khong phep', 've som phat sinh',
         'leader ve som ve som theo chinh sach',
         've som benh co giay kham hoac duoc quan ly duyet'}
UNEXCUSED = {'nghi khong phep', 'nghi cuoi tuan khong phep'}


def return_kind(reason):
    value = key(reason)
    return 'early' if value in EARLY else 'unexcused' if value in UNEXCUSED else ''


def queue_clock(worker):
    marker = worker.get(MARKER) or {}
    return marker.get('queue_at', '') if marker.get('status') == 'queued' else ''


def queue_order(worker):
    marker = worker.get(MARKER) or {}
    return (0 if marker.get('kind') == 'early' else 1, marker.get('day', ''), marker.get('ordinal', 0)) if queue_clock(worker) else (0, '', 0)


def release(worker, status='served'):
    if queue_clock(worker):
        worker[MARKER]['status'] = status


def cutoff(now):
    return now.replace(hour=3, minute=0, second=0, microsecond=0)


def scheduler_delay(now, refresh_seconds):
    next_cutoff = cutoff(now)
    if next_cutoff <= now:
        next_cutoff += timedelta(days=1)
    return min(refresh_seconds, max(0.1, (next_cutoff - now).total_seconds()))


def prepare_daily(state, now):
    """Arm new installations for the next cutoff; never reorder on deployment."""
    boundary = cutoff(now)
    if DAILY_MARKER not in state:
        state[DAILY_MARKER] = {
            'last_day': (now.date() if now >= boundary else now.date() - timedelta(days=1)).isoformat(),
            'initialized_at': now.isoformat(),
        }
        return False
    return now >= boundary and state[DAILY_MARKER]['last_day'] < now.date().isoformat()


def sync_returns(state, directory, leaves, now, leave_day, ordered_employees, time_key, history_leaves=None, *, policy=None):
    """Apply yesterday's nine reasons once, without waiting for a check-in.

    The scheduler targets 03:00. A delayed/retried worker catches up once under
    the existing transaction lock. There is no per-employee return trigger.
    """
    if not prepare_daily(state, now):
        return
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    users = {key(row['username']): row for row in directory if row.get('username')}
    owners = {}
    for username, row in users.items():
        owners.setdefault(key(row.get('full_name')), set()).add(username)
    enabled_reasons = EARLY | UNEXCUSED
    if policy is not None:
        enabled_reasons = {key(reason) for reason in policy['reasons']} if policy['enabled'] else set()
    candidates = {}
    indexed = sorted(enumerate(leaves), key=lambda pair: (
        pair[1].get('source_row') is None, pair[1].get('source_row') or 0,
        pair[1].get('id') or pair[0]))
    for ordinal, (_, row) in enumerate(indexed, 1):
        kind = return_kind(row.get('leave_reason') or row.get('leave_type'))
        if not kind or key(row.get('leave_reason') or row.get('leave_type')) not in enabled_reasons or str(row.get('leave_date')) != yesterday:
            continue
        name = key(row.get('employee_name'))
        matches = owners.get(name, set())
        username = name if name in users else next(iter(matches)) if len(matches) == 1 else ''
        if not username or username in candidates:
            continue
        explicit = re.match(r'^nguoi thu\s+(\d+)\b', key(row.get('detail')))
        candidates[username] = {'day': yesterday, 'kind': kind,
            'ordinal': max(1, int(explicit.group(1))) if explicit else ordinal,
            'record_id': row.get('id'), 'record_uid': str(row.get('record_uid') or row.get('id') or '')}
    # Expire yesterday's position and legacy pending return markers. A missed
    # day is never accumulated into today's placement.
    for worker in state['employees']:
        worker.pop(MARKER, None)
    ordered = ordered_employees(state['employees'], now, manual_order_active=state.get('manual_order_active', True))
    group = []
    for worker in ordered:
        source = candidates.get(key(worker.get('username') or worker.get('name')))
        if not source or worker.get('roster_eligible') is False:
            continue
        # Do not move an active service when recovery runs late. Its normal
        # start has already advanced the queue; do not penalize it again.
        started = str(worker.get('started_at') or '')
        if started[:10] == now.date().isoformat() and key(worker.get('request')) != 'yc' and worker.get('service'):
            continue
        worker[MARKER] = {**source, 'status': 'queued', 'queue_at': cutoff(now).isoformat(),
                          'returned_day': now.date().isoformat()}
        group.append(worker)
    group.sort(key=lambda worker: (*queue_order(worker), str(worker['id'])))
    if state.get('manual_order_active', True) and any(worker.get('manual_order') for worker in ordered):
        ids = {worker['id'] for worker in group}
        for index, worker in enumerate([row for row in ordered if row['id'] not in ids] + group):
            worker.update(sort_index=index, manual_order=True)
    state[DAILY_MARKER].update(last_day=now.date().isoformat(), scheduled_at=cutoff(now).isoformat(),
        applied_at=now.isoformat(), policy_revision=policy.get('revision', 0) if policy else 0, employee_ids=[worker['id'] for worker in group])

"""Project canonical Chấm công break facts without changing service or money data."""
from copy import deepcopy
from datetime import datetime, timedelta
from threading import Lock
from time import monotonic

from vera_web_v2_live_tour_roster import key


class AttendanceBreakReader:
    """Share one short-lived attendance calculation across this app's viewers."""
    def __init__(self, reader, ttl=10, clock=monotonic):
        self.reader, self.ttl, self.clock = reader, ttl, clock
        self.lock = Lock()
        self.day, self.expires, self.rows = None, 0, []

    def read(self, conn, day, *, force=False):
        with self.lock:
            if force or self.day != day or self.clock() >= self.expires:
                rows = self.reader(conn, day, day)
                # Do not cache unrelated attendance/profile information.
                fields = ('date', 'employee_name', 'break_out', 'break_in',
                          'break_return_deadline_iso', 'break_return_deadline',
                          'break_planned_minutes', 'break_source')
                self.rows = [{field: row.get(field) for field in fields} for row in rows]
                self.day, self.expires = day, self.clock() + self.ttl
            return deepcopy(self.rows)


def _stamp(value, day, tz):
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.combine(day, datetime.strptime(raw, '%H:%M:%S' if raw.count(':') == 2 else '%H:%M').time())
        except ValueError:
            return None
    return parsed.replace(tzinfo=tz) if parsed.tzinfo is None else parsed.astimezone(tz)


def _clear_owned(worker, previous):
    # Clear only fields still owned by the projection, never a later manual break.
    values = {'clock_out': previous['out'], 'clock_in': previous['in'],
              'break_started_at': previous['out'] if not previous['in'] else ''}
    for field, value in values.items():
        if worker.get(field) == value:
            worker[field] = ''
    worker.pop('attendance_break', None)


def sync_breaks(state, records, now):
    day, tz = now.date(), now.tzinfo
    owners = {}
    for worker in state['employees']:
        # Username is canonical; full names are usable only if unambiguous.
        for alias in {key(worker.get('username') or worker.get('name')), key(worker.get('full_name'))} - {''}:
            owners.setdefault(alias, []).append(worker)
    by_worker = {}
    for row in records:
        if row.get('date') not in (day.isoformat(), day.strftime('%d/%m/%Y')):
            continue
        candidates = owners.get(key(row.get('employee_name')), [])
        if len(candidates) == 1:
            by_worker.setdefault(candidates[0]['id'], []).append(row)
    for worker in state['employees']:
        previous = worker.get('attendance_break') or {}
        if previous and previous.get('date') != day.isoformat():
            _clear_owned(worker, previous)
            previous = {}
        matches = by_worker.get(worker['id'], [])
        if len(matches) != 1:
            continue  # Missing/ambiguous source must not erase today's known facts.
        row = matches[0]
        out = _stamp(row.get('break_out'), day, tz)
        entered = _stamp(row.get('break_in'), day, tz)
        deadline = _stamp(row.get('break_return_deadline_iso') or row.get('break_return_deadline'), day, tz)
        if not out or out.date() != day or out > now or not deadline:
            continue
        if row.get('break_in') and entered is None:
            continue
        if entered and entered < out:
            entered += timedelta(days=1)
        if entered and entered > now:
            continue
        fact = {'date': day.isoformat(), 'out': out.isoformat(),
                'in': entered.isoformat() if entered else '', 'deadline': deadline.isoformat(),
                'source': str(row.get('break_source') or 'Chấm công')}
        # A temporarily incomplete cache must not reopen a confirmed return.
        if previous.get('out') == fact['out'] and previous.get('in') and not fact['in']:
            fact['in'] = previous['in']
        if fact == previous:
            continue
        worker['attendance_break'] = fact
        worker['clock_out'], worker['clock_in'] = fact['out'], fact['in']
        worker['break_started_at'] = '' if fact['in'] else fact['out']
        # Booking, room, service clock, order, notes and all ledgers stay intact.

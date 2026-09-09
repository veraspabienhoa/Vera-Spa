"""Booking a place for the next customer never starts overlapping services."""
from datetime import datetime
import math

from vera_web_v2_live_tour_roster import key


def conflicts(room, group, private, other):
    return key(room) == key(other['room']) or (key(group) == key(other['group']) and (private or other['private']))


def place_status(occupancy, *, room, group, private, candidate, now, reserve=True):
    remaining = []
    unknown = False
    own_status = key(candidate.get('status'))
    for other in occupancy:
        if other['employee_id'] == candidate.get('employee_id') or not conflicts(room, group, private, other):
            continue
        old_conflict = bool(candidate.get('room')) and conflicts(candidate['room'], candidate['group'], candidate['private'], other)
        # A reservation made behind the current service does not prevent its
        # operator from editing/completing that original service.
        if own_status in {'dang thuc hien', 'dang su dung'} and key(other['status']) == 'dang cho' and old_conflict:
            continue
        if key(other['status']) == 'dang cho':
            return {'allowed': False, 'can_start': False, 'reason': 'waiting', 'remaining_seconds': None}
        try:
            seconds = (datetime.fromisoformat(other['deadline']) - now).total_seconds()
            if not math.isfinite(seconds):
                raise ValueError()
        except (ValueError, TypeError):
            seconds = None
        held = own_status == 'dang cho' and old_conflict
        if not reserve or (not held and (seconds is None or seconds >= 1800)):
            return {'allowed': False, 'can_start': False, 'reason': 'occupied', 'remaining_seconds': seconds}
        if seconds is None:
            unknown = True
        else:
            remaining.append(seconds)
    if remaining or unknown:
        return {'allowed': True, 'can_start': False, 'reason': 'finishing', 'remaining_seconds': None if unknown else max(remaining)}
    return {'allowed': True, 'can_start': True, 'reason': 'ready', 'remaining_seconds': 0}

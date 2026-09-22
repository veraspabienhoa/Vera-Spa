"""Project today's FaceID check-in and Vera-assigned shift onto the tour directory."""
from datetime import timedelta
from vera_shift_assignment import scheduled_shift

from vera_web_v2_attendance_query_perf import _datasets
from vera_web_v2_attendance_v42 import _canonical_employee, _explicit_work_day, _generic_raw_punch, _parse_datetime, _work_day_for_row
from vera_web_v2_live_tour_roster import key


def _checked_in_shift(row, day, timesoft_shift=None):
    """TimeSoft supplies punches only; never use its assigned shift."""
    return scheduled_shift(row, day)


def project(directory, datasets, now):
    day = now.date()
    owners = {}
    for row in directory:
        for alias in {key(row.get('username')), key(row.get('full_name'))} - {''}:
            owners.setdefault(alias, set()).add(row['username'])
    aliases = {alias: next(iter(names)) for alias, names in owners.items() if len(names) == 1}
    attendance = {}
    for dataset in datasets:
        payload = dataset.get('payload') or []
        if not isinstance(payload, list):
            continue
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            username = _canonical_employee(raw, aliases)
            if not username:
                continue
            work_day = _explicit_work_day(raw)
            # Checkout summaries and schedule-only records are not check-ins.
            values = [value for name, value in raw.items() if name.startswith(('MachineTimeCheckIn', 'LocalTimeCheckIn')) and name.endswith('Str')]
            punches = [parsed for value in values if (parsed := _parse_datetime(value, work_day)) is not None]
            if not punches and not any(name.startswith(('MachineTime', 'LocalTime')) and 'CheckOut' in name for name in raw):
                punches = _generic_raw_punch(raw, work_day)
            if (work_day or _work_day_for_row(raw, punches)) != day:
                continue
            bucket = attendance.setdefault(username, {'checked': False})
            # Midnight exit scans from the preceding workday cannot open today's shift.
            bucket['checked'] |= any(p.date() == day and 3 <= p.hour < 23 and p <= now.replace(tzinfo=None) for p in punches)
    for row in directory:
        data = attendance.get(row['username'], {})
        row['scheduled_week_shift'] = scheduled_shift(row, day)
        row['scheduled_next_shift'] = scheduled_shift(row, day + timedelta(days=7))
        row['daily_shift'] = _checked_in_shift(row, day) if data.get('checked') else ''
        row['shift_checkin_date'] = day.isoformat()
    return directory


def with_checkin(conn, directory, now):
    return project(directory, _datasets(conn, now.date(), now.date()), now) if directory else directory

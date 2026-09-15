"""Project TimeSoft check-in onto Live Tour; each shift day ends at 02:00 VN."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from vera_web_v2_attendance_query_perf import _datasets
from vera_web_v2_attendance_v42 import _canonical_employee, _explicit_work_day, _generic_raw_punch, _parse_date, _parse_datetime, _work_day_for_row
from vera_web_v2_live_tour_roster import key, shift_label


VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
SHIFT_RESET_HOUR = 2


def _local_now(now: datetime) -> datetime:
    # Existing direct callers use naive Vietnam wall time; UTC-aware callers
    # must be converted before comparing dates or the TimeSoft punch clock.
    return now.replace(tzinfo=VN_TZ) if now.tzinfo is None else now.astimezone(VN_TZ)


def shift_day(now: datetime) -> date:
    """The Vào ca day, not the invoice, leave, or attendance-report date.

    [00:00, 02:00) still belongs to yesterday. At exactly 02:00, yesterday's
    Face ID assignment and manual Live Tour shift override both expire.
    """
    return (_local_now(now) - timedelta(hours=SHIFT_RESET_HOUR)).date()


def scheduled_shift(row, day):
    base = shift_label(row.get('work_shift'), row.get('shift_definitions'))
    cycle = key(row.get('rotation_cycle'))
    label = key(row.get('work_shift'))
    if not base or 'co dinh' in label or 'khong doi' in label or 'co dinh' in cycle:
        return base
    anchor = _parse_date(row.get('shift_start_date'))
    monday = day - timedelta(days=day.weekday())
    if not anchor or monday <= anchor:
        return base
    if '14 ngay' in cycle or 'luan phien' in cycle:
        periods = (monday - anchor).days // 14
    elif 'thang' in cycle:
        periods = (monday.year - anchor.year) * 12 + monday.month - anchor.month
    elif '7 ngay' in cycle or 'tuan' in cycle:
        periods = (monday - anchor).days // 7
    else:
        return base
    return ('Ca 2' if base == 'Ca 1' else 'Ca 1') if periods % 2 else base


def _checked_in_shift(row, day, timesoft_shift):
    """Use the effective staff assignment, not a stale TimeSoft schedule label.

    TimeSoft remains the evidence for check-in. Its shift label is only a
    fallback when the directory has no usable assignment for this day. An
    undated legacy assignment applies immediately; a future or invalid date
    must not silently activate the new shift before its effective date.
    Same-day Admin overrides are applied later by roster reconciliation.
    """
    start_value = str(row.get('shift_start_date') or '').strip()
    starts_on = _parse_date(start_value)
    if not start_value or (starts_on is not None and starts_on <= day):
        assigned = scheduled_shift(row, day)
        if assigned:
            return assigned
    return shift_label(timesoft_shift, row.get('shift_definitions'))


def project(directory, datasets, now):
    now = _local_now(now)
    day = shift_day(now)
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
            bucket = attendance.setdefault(username, {'checked': False, 'shift': ''})
            # Midnight exit scans from the preceding workday cannot open today's shift.
            bucket['checked'] |= any(p.date() == day and 3 <= p.hour < 23 and p <= now.replace(tzinfo=None) for p in punches)
            shift = str(raw.get('WorkTimeName') or raw.get('ShiftName') or '').strip()
            if shift and not bucket['shift']:
                bucket['shift'] = shift
    for row in directory:
        data = attendance.get(row['username'], {})
        row['daily_shift'] = _checked_in_shift(row, day, data.get('shift')) if data.get('checked') else ''
        row['shift_checkin_date'] = day.isoformat()
    return directory


def with_checkin(conn, directory, now):
    if not directory:
        return directory
    day = shift_day(now)
    # Read the dated snapshot for yesterday until 02:00 even if the rolling
    # TimeSoft "today" alias has already switched to the new calendar date.
    return project(directory, _datasets(conn, day, day), now)

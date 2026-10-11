"""VERA schedule attendance window, including earlier/later overtime."""
from datetime import datetime, time, timedelta


def attendance_window(row):
    start, end = str(row.get("start_time") or ""), str(row.get("end_time") or "")
    if str(row.get("shift_code") or "").strip().casefold() in {"", "nghỉ", "nghi"}:
        return "", ""
    overtime = str(row.get("overtime_shift") or "")
    left, right = str(row.get("overtime_start_time") or ""), str(row.get("overtime_end_time") or "")
    if not overtime or not left or not right:
        return start, end
    def minutes(value):
        clock = time.fromisoformat(value)
        return clock.hour * 60 + clock.minute
    try:
        a, b, c, d = map(minutes, (start, end, left, right))
    except ValueError:
        return start, end
    if b <= a:
        b += 1440
    if d <= c:
        d += 1440
    if overtime == "Từ giờ tới giờ":
        # Custom after-midnight extensions follow an overnight main shift.
        # Named Ca 1/2 always start on the schedule date.
        offset = _custom_overtime_offset(a, b, c, d)
        c, d = c+offset, d+offset
    a, b = min(a, c), max(b, d)
    if b-a >= 1440:
        return start, end  # Downstream clock-only fields cannot express >=24h.
    def clock(value):
        value %= 1440
        return f"{value//60:02d}:{value%60:02d}"
    return clock(a), clock(b)


def _custom_overtime_offset(main_start, main_end, ot_start, ot_end):
    """Clock-only custom OT follows an overnight shift only when connected.

    A gap after midnight has no date information, so retain the existing
    attendance interpretation rather than guessing a next-day interval.
    """
    return 1440 if main_end >= 1440 and ot_start <= main_end % 1440 and ot_end <= main_start else 0


def scheduled_periods(row, work_day, *, tzinfo=None):
    """Shared wage periods using VERA attendance geometry; main wins overlaps.

    Callers resolve department shift definitions first. Returned buckets are
    anchored to each original period, so an after-midnight split cannot turn
    an evening/main Ca 2 interval into a morning/Ca 1 interval.
    """
    shift = str(row.get('shift_code') or '').strip()
    if shift.casefold() in {'', 'nghỉ', 'nghi'}:
        return []

    def bounds(left, right):
        try:
            a = datetime.combine(work_day, time.fromisoformat(str(left)), tzinfo=tzinfo)
            b = datetime.combine(work_day, time.fromisoformat(str(right)), tzinfo=tzinfo)
        except (TypeError, ValueError):
            return None
        if a == b:
            return None
        return a, b + timedelta(days=1) if b < a else b

    main = bounds(row.get('start_time'), row.get('end_time'))
    if not main:
        return []
    bucket = 'ca1' if shift == 'Ca 1' or (shift != 'Ca 2' and main[0].hour < 12) else 'ca2'
    periods = [(*main, bucket)]
    overtime = str(row.get('overtime_shift') or '')
    if not overtime:
        return periods
    ot = bounds(row.get('overtime_start_time'), row.get('overtime_end_time'))
    if not ot:
        return periods
    offset = 0
    if overtime == 'Từ giờ tới giờ':
        midnight = datetime.combine(work_day, time(), tzinfo=tzinfo)
        minutes = [(point-midnight).total_seconds()/60 for point in (*main, *ot)]
        offset = _custom_overtime_offset(*minutes)
    if offset:
        ot = tuple(point + timedelta(minutes=offset) for point in ot)
    if overtime in {'TC Ca 1', 'TC Ca 2'}:
        bucket = 'ca1' if overtime == 'TC Ca 1' else 'ca2'
    else:
        bucket = 'ca2' if offset or ot[0].hour >= 12 else 'ca1'
    return [*periods, (*ot, bucket)]

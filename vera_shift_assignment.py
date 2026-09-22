"""Vera staff assignments are the sole source of KTV shift rotation."""
import re
from vera_web_v2_attendance_v42 import _parse_date
from vera_web_v2_live_tour_roster import key, shift_label


def scheduled_shift(row, day):
    start_value = str(row.get('shift_start_date') or '').strip()
    starts_on = _parse_date(start_value)
    if start_value and (starts_on is None or starts_on > day):
        return ''
    base = shift_label(row.get('work_shift'), row.get('shift_definitions'))
    cycle = key(row.get('rotation_cycle'))
    label = key(row.get('work_shift'))
    if not base or 'co dinh' in label or 'khong doi' in label or 'co dinh' in cycle:
        return base
    anchor = _parse_date(row.get('shift_start_date'))
    if not anchor or day <= anchor:
        return base
    # Since 21-09-2026 the named weekly cycle switches every 7 days.
    # Custom Admin cycles are encoded in their label, e.g. "Mỗi 2 ngày".
    # Legacy "Luân phiên (14 ngày)" is treated as the renamed weekly cycle so
    # existing employees change correctly without a data migration.
    if 'co dinh' in cycle or 'khong doi' in cycle:
        return base
    if 'luan phien' in cycle or 'theo chu ky tuan' in cycle or cycle == 'tuan':
        switch_days = 7
    else:
        match = re.search(r'(\d+)\s*ngay', cycle)
        if not match:
            return base
        switch_days = max(1, int(match.group(1)))
    periods = max(0, (day - anchor).days // switch_days)
    return ('Ca 2' if base == 'Ca 1' else 'Ca 1') if periods % 2 else base


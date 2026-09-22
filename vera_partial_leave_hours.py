"""Configurable daily late-arrival and early-departure clocks for staff."""
import re
from sqlalchemy import text
import vera_live_tour_resource_store as resource_store
from vera_web_v2_live_tour_roster import key

DEFAULT_HOURS = {'late1': '15:00', 'late2': '17:00', 'early1': '15:00', 'early2': '17:00'}
LATE_REASONS = {key(value) for value in (
    'Đi trễ', 'Đi trễ CÓ phép', 'Đi trễ KHÔNG phép',
    'Đi trễ CUỐI TUẦN CÓ phép', 'Đi trễ CUỐI TUẦN KHÔNG phép',
    'Đi trễ phát sinh', 'Leader đi trễ sớm theo chính sách',
)}
EARLY_REASONS = {key(value) for value in (
    'Về sớm', 'Về sớm CÓ phép', 'Về sớm KHÔNG phép',
    'Về sớm CUỐI TUẦN CÓ phép', 'Về sớm CUỐI TUẦN KHÔNG phép',
    'Về sớm phát sinh', 'Về sớm bệnh có giấy khám hoặc được quản lý duyệt',
    'Leader về sớm về sớm theo chính sách',
)}


def clock_for(shift, kind, settings=None):
    suffix = {'ca 1': '1', 'ca 2': '2'}.get(key(shift))
    if not suffix:
        return None
    name = kind + suffix
    value = (settings or {}).get(name, DEFAULT_HOURS[name])
    return value if isinstance(value, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value) else DEFAULT_HOURS[name]


def daily_clock(conn, day, employee, kind):
    # Use the same weekly rotation and named-shift definitions as the tour.
    from vera_web_v2_live_tour_checkin import scheduled_shift
    rows = conn.execute(text("""
        SELECT username, full_name, role, work_shift, rotation_cycle, shift_start_date,
          (SELECT value_json FROM vera_app_setting WHERE category='shift' AND setting_key='shift_definitions') AS shift_definitions,
          (SELECT value_json->'payment_settings'->'partial_leave_times' FROM vera_app_setting WHERE category='live_tour' AND setting_key='state') AS partial_leave_times
        FROM employees WHERE lower(btrim(role)) IN ('leader', 'nhanvien')
    """), {}).mappings().all()
    matches = [row for row in rows if key(row.get('username')) == key(employee)]
    if not matches:
        matches = [row for row in rows if key(row.get('full_name')) == key(employee)]
    if len(matches) != 1:
        return None
    row = matches[0]
    settings = row.get('partial_leave_times')
    if resource_store.enabled():
        state, _, _ = resource_store.read(conn)
        settings = state.get('payment_settings', {}).get('partial_leave_times')
    return clock_for(scheduled_shift(row, day), kind, settings)

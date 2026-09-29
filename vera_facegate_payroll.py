"""Read-only basic-pay estimate using FaceGate records and saved VERA rates.

No production source change, payslip, benefits, deduction or penalty write.
Incomplete employee periods return null money, never an inferred zero salary.
"""
from collections import defaultdict
from datetime import datetime

from vera_facegate_control_log import VN_TZ
from vera_facegate_attendance import preview
import vera_web_v2_department_payroll as payroll
from vera_web_v2_devices import norm


LABELS = {
    'unmapped': 'Chưa ánh xạ nhân viên',
    'missing_day': 'Thiếu dữ liệu ngày công',
    'missing_punch': 'Chưa đủ giờ vào/ra',
    'missing_shift': 'Chưa có ca VERA',
    'open_day': 'Ngày công chưa kết thúc',
    'archive_incomplete': 'Chưa xác minh đủ log ngày công',
    'unresolved_events': 'Còn sự kiện chưa xử lý trong kỳ',
    'invalid_interval': 'Khoảng giờ làm việc chưa hợp lệ',
    'unsupported_rate': 'Chưa có đơn giá cho giờ công này',
}


def calculate_employee(records, username, config, start, end, report, today):
    selected = [r for r in records if r.get('employee_name') == username]
    pending = set()
    days = defaultdict(list)
    for row in selected:
        try:
            day = datetime.strptime(row['date'], '%d/%m/%Y').date()
        except (KeyError, TypeError, ValueError):
            pending.add('missing_day')
            continue
        if start <= day <= end:
            days[day].append(row)
    if username in report.get('unmapped_employees', []):
        pending.add('unmapped')
    # Unknown-owner issues cannot be safely allocated to a single employee.
    if report.get('blocking_issue_count', 0):
        pending.add('unresolved_events')
    if end >= today:
        pending.add('open_day')
    if report.get('incomplete_days'):
        pending.add('archive_incomplete')
    if len(days) != (end - start).days + 1:
        pending.add('missing_day')
    payable = []
    for day, entries in days.items():
        if len(entries) != 1:
            pending.add('missing_day')
            continue
        row = entries[0]
        if not row.get('attendance_expected', True) and not row.get('check_in'):
            # A non-working day requires a separate leave/payroll policy review.
            pending.add('missing_punch')
            continue
        if not row.get('shift') or not row.get('shift_start') or not row.get('shift_end'):
            pending.add('missing_shift')
        minutes, left, right = payroll._interval_minutes(row, day)
        if left is None or right is None:
            pending.add('missing_punch')
        elif minutes <= 0 or minutes >= 24 * 60:
            pending.add('invalid_interval')
        else:
            payable.append(row)
    totals = payroll._attendance_totals(payable, username, norm, config)
    hours = {name: round(totals[key] / 60, 2) for name, key in (
        ('hours_ca1', 'minutes_ca1'), ('hours_ca2_before_22', 'minutes_ca2_before_22'),
        ('hours_ca2_after_22', 'minutes_ca2_after_22'))}
    if config['calculation_mode'] == 'hourly':
        if any(hours[h] > 0 and config[r] <= 0 for h, r in (
                ('hours_ca1', 'rate_ca1'), ('hours_ca2_before_22', 'rate_ca2_before_22'),
                ('hours_ca2_after_22', 'rate_ca2_after_22'))):
            pending.add('unsupported_rate')
    elif config['default_base_salary'] <= 0:
        pending.add('unsupported_rate')
    calculated = payroll._recalculate({**hours, 'base_salary': config['default_base_salary'],
        'work_days': round(sum(hours.values()) / config['standard_day_hours'], 2)}, config)
    return {'employee_username': username, 'status': 'pending' if pending else 'estimated',
            'pending_reasons': [LABELS[k] for k in sorted(pending)],
            'basic_salary_estimate': None if pending else calculated['salary'],
            'hours': None if pending else round(sum(hours.values()), 2),
            'observed_complete_hours': round(sum(hours.values()), 2),
            'calculation_mode': config['calculation_mode'],
            'rates': {k: config[k] for k in ('rate_ca1', 'rate_ca2_before_22', 'rate_ca2_after_22')},
            'daily_records': [{k: r.get(k) for k in ('date', 'check_in', 'check_out', 'shift',
                              'punch_times', 'break_actual_minutes')} for r in selected]}


def calculate(conn, start, end):
    report = preview(conn, start, end)
    configs = payroll._employee_config_map(conn)
    employees = payroll._salary_employee_catalog(conn)
    department_configs = {d: payroll._settings(conn, d)['config']
                          for d in {e['department'] for e in employees}}
    today = datetime.now(VN_TZ).date()
    rows = []
    for employee in employees:
        username = employee['employee_username']
        config = configs.get(username.casefold(), department_configs[employee['department']])
        row = calculate_employee(report['records'], username, config, start, end, report, today)
        rows.append({**employee, **row})
    return {'ok': True, 'source': 'facegate', 'mode': 'basic_pay_estimate',
            'start': start.isoformat(), 'end': end.isoformat(), 'rows': rows,
            'pending_count': sum(r['status'] == 'pending' for r in rows),
            'estimated_basic_pay_total': sum(r['basic_salary_estimate'] or 0 for r in rows),
            'blockers': report['blockers'],
            'applied_test_scan_reviews': report.get('applied_test_scan_reviews', []),
            'official_payroll_written': False, 'attendance_cutover_ready': False}

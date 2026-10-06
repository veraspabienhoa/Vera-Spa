"""Administrative probation policy; reuse the caller's connection and attendance evidence."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import text
import vera_web_v2_hr as hr
from vera_employee_names import canonical_username, load_identity_index

POLICY = 'hc-probation-first-15-workdays-2026-10-06'
INCOME_FIELDS = ('base_salary', 'full_allowance', 'attendance_bonus', 'responsibility', 'seniority', 'combo_sales')


def qualifying_month(records, username, start, end, identity, minutes):
    days = defaultdict(set)
    wanted = username.strip().casefold()
    for row in records:
        if canonical_username(identity, row.get('employee_name')).casefold() != wanted:
            continue
        if row.get('attendance_pending'):
            continue
        try:
            day = datetime.strptime(str(row.get('date') or ''), '%d/%m/%Y').date()
        except ValueError:
            continue
        if not start <= day <= end or minutes(row, day)[0] <= 0:
            continue
        days[day.strftime('%Y-%m')].add(day)
    return next((month for month in sorted(days) if len(days[month]) >= 15), None)


def policies(conn, month, *, parse_date, records, minutes, period_end, usernames=None, department=None):
    scope = " AND lower(btrim(e.username))=ANY(:usernames)" if usernames is not None else ""
    scope += f" AND {hr.DEPARTMENT_SQL}=:department" if department else ""
    params = {}
    if usernames is not None: params['usernames'] = [str(name or '').strip().casefold() for name in usernames]
    if department: params['department'] = department
    employees = conn.execute(text(f"""
        SELECT e.username, to_jsonb(e)->>'employment_start_date' AS employment_start_date
        FROM employees e
        WHERE {hr.ADMIN_PAY_SQL}
          AND COALESCE(e.payload->>'__deleted','false') <> 'true'
          AND lower(btrim(COALESCE(e.payload->>'Không tính lương','false'))) NOT IN ('1','true','yes','y','có','x','ẩn')
          AND lower(btrim(COALESCE(NULLIF(e.payload->>'Trạng thái làm việc',''),
                    NULLIF(e.payload->>'employment_status',''),'Đang làm việc')))='thử việc'
          {scope}
    """), params).mappings().all()
    if not employees:
        return {}
    starts = {}
    for employee in employees:
        start = parse_date(employee.get('employment_start_date'))
        if not start:
            raise HTTPException(409, 'Nhân viên Thử việc chưa có Ngày bắt đầu làm hợp lệ. Hãy cập nhật hồ sơ trước khi tính lương.')
        starts[str(employee['username']).strip().casefold()] = start
    # Only previous months can release the current month from probation. A single
    # borrowed-connection read covers all probation employees, never one per row.
    month_start = date.fromisoformat(month + '-01')
    end = min(period_end, month_start - timedelta(days=1))
    earliest = min(starts.values())
    evidence = records(conn, earliest, end) if earliest <= end else []
    identity = load_identity_index(conn) if evidence else {}
    result = {}
    for username, start in starts.items():
        qualified = qualifying_month(evidence, username, start, end, identity, minutes)
        result[username] = {'rate': 1 if qualified or month < start.strftime('%Y-%m') else .75, 'start': start.isoformat(),
                            'qualifying_month': qualified, 'policy': POLICY}
    return result


def apply(row, policy=None, *, saved=False):
    result = dict(row)
    rate = (policy or {}).get('rate', 1)
    previous = result.get('probation_rate', 1)
    if saved and 'probation_rate' in result and previous != rate:
        raise HTTPException(409, 'Quy tắc thử việc đã thay đổi. Hãy Tính lại lương trước khi lưu hoặc xuất/gửi bảng lương.')
    if not saved or 'probation_rate' not in result:
        for field in INCOME_FIELDS:
            result[field] = round(max(0, float(result.get(field) or 0)) * rate)
    result['probation_rate'] = rate
    result['probation_policy'] = (policy or {}).get('policy', POLICY)
    result['probation_start'] = (policy or {}).get('start', '')
    result['probation_qualifying_month'] = (policy or {}).get('qualifying_month')
    return result

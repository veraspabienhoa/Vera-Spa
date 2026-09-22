"""Derived monthly allowance: approved sickness can borrow next month's leave.

No mutable counters: edits/deletions automatically rebuild the same balance.
Annual leave, video leave, unpaid leave and generated incidents stay separate.
"""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from vera_leave_registration_shared import norm

SICK_REASONS = frozenset(norm(s) for s in (
    'Nghỉ bệnh có giấy khám hoặc được quản lý duyệt',
    'Về sớm bệnh có giấy khám hoặc được quản lý duyệt',
    'Đi trễ bệnh có giấy khám hoặc được quản lý duyệt',
))


def is_approved_sick(reason):
    return norm(str(reason or '').replace('🔴', '').strip()) in SICK_REASONS


def ordinary_paid(reason):
    key = norm(str(reason or '').replace('🔴', '').strip())
    return not is_approved_sick(reason) and not any(s in key for s in (
        'phep nam', 'quay video', 'khong phep', 'phat sinh', 'ly do khac'))


def parse_date(value):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try: return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError: pass
    return None


def next_month(month):
    return date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)


def balances(rows, through, base=5, since=None):
    """One employee, through an inclusive month. Debt beyond a month stays owed."""
    through = through.replace(day=1)
    buckets = defaultdict(lambda: {'ordinary': Decimal(0), 'sick': Decimal(0)})
    for row in rows:
        day = parse_date(row.get('leave_date', row.get('Ngày')))
        if day is None or day.replace(day=1) > through: continue
        reason = row.get('leave_reason', row.get('Lý do nghỉ', ''))
        days = Decimal(str(row.get('calculated_days', row.get('Số ngày tính', 0)) or 0))
        if not days.is_finite(): continue
        days = max(Decimal(0), days)
        kind = 'sick' if is_approved_sick(reason) else 'ordinary' if ordinary_paid(reason) else None
        if kind and days: buckets[day.replace(day=1)][kind] += days
    month = min([through, (since or through).replace(day=1), *buckets])
    limit = max(Decimal(0), Decimal(str(base)))
    debt = Decimal(0)
    result = {}
    while month <= through:
        ordinary, sick = buckets[month]['ordinary'], buckets[month]['sick']
        available = max(Decimal(0), limit-debt)
        borrowed = max(Decimal(0), sick-max(Decimal(0), available-ordinary))
        outgoing = max(Decimal(0), debt-limit)+borrowed
        result[month.isoformat()[:7]] = {k:float(v) for k,v in {
            'base':limit, 'deducted':debt, 'available':available,
            'ordinary':ordinary, 'sick':sick, 'borrowed':borrowed,
            'remaining':max(Decimal(0), available-ordinary-sick),
            'next_deduction':outgoing, 'ordinary_excess':max(Decimal(0),ordinary-available),
        }.items()}
        debt=outgoing
        month=next_month(month)
    return result

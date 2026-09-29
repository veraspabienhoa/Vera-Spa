"""Versioned operator decisions; no database, network, or employee mutations.

Temporary suspension starts on the Vietnam business date of authorization.
To resume an account, close its interval with effective_until (exclusive).
Do not delete the interval: historical attendance must remain reproducible.
New payroll for an overlapping period omits the whole account, rather than
silently calculating a partial month. Already saved payroll remains untouched.
"""
from datetime import date
import unicodedata

POLICY_ID = 'temporary-attendance-payroll-suspension-2026-09-29'
AUTHORIZED_AT = '2026-09-29T22:07:31+07:00'
SUSPENSIONS = tuple(
    {'username': username, 'effective_from': date(2026, 9, 29), 'effective_until': None}
    for username in ('admin', 'akamen', 'letan', 'Ms Tuyết')
)


def _key(username):
    return unicodedata.normalize('NFC', str(username or '')).strip().casefold()


def suspended(username, start, end=None):
    end = end or start
    return any(_key(username) == _key(item['username'])
               and end >= item['effective_from']
               and (item['effective_until'] is None or start < item['effective_until'])
               for item in SUSPENSIONS)


def eligible(rows, start, end=None, *, key):
    return [row for row in rows if not suspended(row.get(key), start, end)]


def require_payroll_participants(rows, start, end, *, key):
    from fastapi import HTTPException
    if any(suspended(row.get(key), start, end) for row in rows):
        raise HTTPException(409, 'Bảng lương có tài khoản đang tạm ngừng chấm công/tính lương. '
                            'Hãy tính lại bảng lương để loại tài khoản tạm ngừng.')


def preserved_payroll(rows, start, end, *, key):
    """Retain saved money for omitted accounts when updating the same period."""
    return [dict(row) for row in rows if isinstance(row, dict)
            and suspended(row.get(key), start, end)]


def status(day):
    users = [item['username'] for item in SUSPENSIONS
             if suspended(item['username'], day)]
    return {'participation_policy_id': POLICY_ID,
            'excluded_employee_count': len(users), 'excluded_usernames': users}

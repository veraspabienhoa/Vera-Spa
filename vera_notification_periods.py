"""Business-month scope for leave quota notifications, including legacy payloads."""
from datetime import datetime
import re
from zoneinfo import ZoneInfo


def current_month():
    return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m')


def quota_month(payload):
    value = str(payload.get('quota_month') or payload.get('month') or '')
    if re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', value):
        return value
    # Older routed notices stored the ISO month only in their plain-text body.
    match = re.search(r'\b\d{4}-(?:0[1-9]|1[0-2])\b', str(payload.get('body') or ''))
    return match.group(0) if match else None


def current_quota_sql(source='r.source_key', payload='d.payload'):
    """Trusted SQL expressions only; preserve every other notification family."""
    return f"""({source}<>'leave_quota_exceeded' OR
        COALESCE({payload}->>'quota_month', substring({payload}->>'body' FROM '[0-9]{{4}}-[0-9]{{2}}'))
        = to_char(NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh','YYYY-MM'))"""

"""Narrow delete exception for front desk/managers on the creation calendar day."""
from datetime import datetime


def may_delete_created_today(role, row, now):
    if str(role or '').strip().lower() not in {'letan', 'quanly'}:
        return False
    created = row.get('created_at')
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created.replace('Z', '+00:00'))
        except ValueError:
            return False
    # PostgreSQL created_at is timestamptz. Never substitute the last-edit date,
    # the leave date or an ambiguous legacy timestamp to grant this exception.
    if not isinstance(created, datetime) or created.tzinfo is None:
        return False
    return created.astimezone(now.tzinfo).date() == now.date()

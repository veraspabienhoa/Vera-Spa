"""The same accent-insensitive contains filters used by list, totals and Excel."""
import unicodedata


def normalize(value):
    value = unicodedata.normalize('NFD', str(value or '')).replace('đ', 'd').replace('Đ', 'D')
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).casefold().split())


def filter_rows(rows, leave_reason='', leave_type='', detail=''):
    wanted = {'leave_reason': normalize(leave_reason), 'leave_type': normalize(leave_type), 'detail': normalize(detail)}
    return [row for row in rows if all(value in normalize(row.get(key)) for key, value in wanted.items())]

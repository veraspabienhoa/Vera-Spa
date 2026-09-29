"""Shared, hot-readable attendance cutover; no credentials and no network I/O.

Missing configuration preserves the legacy source. Invalid configuration fails
closed, instead of silently resuming TimeSoft after an operator cutover.
"""
from datetime import date, datetime
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
CONFIG_PATH = '/opt/vera-spa/attendance-source.json'


def configuration():
    path = Path(os.environ.get('VERA_ATTENDANCE_SOURCE_FILE', CONFIG_PATH))
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'source': 'timesoft', 'effective_date': None}
    except (OSError, ValueError):
        raise RuntimeError('attendance_source_configuration_invalid') from None
    if not isinstance(value, dict) or value.get('source') != 'facegate' or value.get('version') != 1:
        raise RuntimeError('attendance_source_configuration_invalid')
    try:
        date.fromisoformat(value['effective_date'])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError('attendance_source_configuration_invalid') from None
    return value


def enabled():
    return configuration()['source'] == 'facegate'


def effective_date():
    config = configuration()
    return date.fromisoformat(config['effective_date']) if config['source'] == 'facegate' else None


def source_for(day):
    cutoff = effective_date()
    return 'facegate' if cutoff and day >= cutoff else 'timesoft'


def cache_key(day=None, *, today_alias=False):
    day = day or datetime.now(VN_TZ).date()
    return source_for(day) + '_employee_checkin_' + ('today' if today_alias else day.strftime('%Y%m%d'))


def require_timesoft_enabled():
    if enabled():
        raise RuntimeError('timesoft_disabled_by_facegate_cutover')


def health(conn, *, now=None):
    from sqlalchemy import text
    now = now or datetime.now(VN_TZ)
    config = configuration()
    row = conn.execute(text('''SELECT row_count,updated_at,source_version,expires_at
        FROM vera_dataset_cache WHERE dataset_key=:key'''),
        {'key': cache_key(now.date())}).mappings().first()
    updated = row.get('updated_at') if row else None
    age = (now - updated).total_seconds() if updated and updated.tzinfo else None
    fresh = bool(row and row['source_version'] == now.date().isoformat()
                 and age is not None and 0 <= age <= 300 and row['expires_at'] > now)
    return {'source': config['source'], 'effective_date': config['effective_date'],
            'timesoft_network_enabled': config['source'] != 'facegate',
            'cache_fresh': fresh, 'fresh': fresh, 'age_seconds': age,
            'last_sync_at': updated.isoformat() if updated else None,
            'updated_at': updated.isoformat() if updated else '',
            'row_count': int(row['row_count']) if row else 0}

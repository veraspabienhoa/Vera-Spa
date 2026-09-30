"""Read-only deployment policy check when the operator defers attendance freshness.

No device/database I/O, source switch, cache publication or payroll writes.
"""
from datetime import date, datetime
import json
import vera_attendance_source as source


def verify_policy():
    config = source.configuration()
    today = datetime.now(source.VN_TZ).date()
    cutoff = date.fromisoformat(config['effective_date']) if config['source'] == 'facegate' else None
    if config['source'] != 'facegate' or cutoff is None or cutoff > today:
        raise RuntimeError('active_facegate_policy_required')
    return {'ok': True, 'scope': 'source_policy_only', 'source': 'facegate',
            'effective_date': cutoff.isoformat(), 'timesoft_network_enabled': False,
            'attendance_freshness_verified': False, 'attendance_readiness_verified': False,
            'freshness_check_deferred': True, 'database_writes': False}


def main():
    try:
        print(json.dumps(verify_policy()))
        return 0
    except Exception:
        # Do not expose configuration contents or arbitrary exception messages.
        print(json.dumps({'ok': False, 'scope': 'source_policy_only',
                          'reason': 'active_facegate_policy_unverified', 'database_writes': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

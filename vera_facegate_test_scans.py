"""Versioned operator-confirmed test scans; never delete archived evidence.

The owner confirmed on 29-09-2026 at 14:35:40 +07:00 that both scans were
only a test and the employee continued working, and authorized exclusion again
at 14:38:57. This review affects the shadow calculator, not production cutover.
"""
from datetime import datetime
import json

REVIEW_ID = 'yen-linh-test-scans-2026-09-29'
CONFIRMED_AT = '2026-09-29T14:38:57+07:00'
EXPECTED = {'79329': '2026-09-29T14:21:22+07:00',
            '79330': '2026-09-29T14:21:24+07:00'}
REFERENCE = (0, 0, 14155776)


def exclude_reviewed_test_scans(rows, events, index, address):
    """Exclude the exact reviewed pair, or retain everything and report failure.

    Input rows/events are not mutated. Raw comparisons retain both test scans.
    No name-only matching, time-window exclusion, database writes or device I/O.
    """
    from vera_facegate_readiness import reference
    selected = [e for e in events if str(e.get('event_id')) in EXPECTED]
    if not selected:
        return list(rows), [], []
    failure = [{'reason': 'reviewed_test_scans_invalid', 'review_id': REVIEW_ID}]
    mapping = index.get(REFERENCE)
    if (address != '192.168.1.34' or not mapping
            or mapping.get('username') != 'Yến Linh'
            or str(mapping.get('profile_id')) != '217'
            or not mapping.get('confirmed_by')
            or len(selected) != 2
            or {str(e['event_id']) for e in selected} != set(EXPECTED)):
        return list(rows), failure, []
    try:
        for e in selected:
            p = e['payload_json']
            p = json.loads(p) if isinstance(p, str) else p
            instant = datetime.fromisoformat(str(e['occurred_at']))
            expected = datetime.fromisoformat(EXPECTED[str(e['event_id'])])
            if (instant.utcoffset() is None or instant != expected
                    or reference(p.get('registration_ref')) != REFERENCE
                    or p.get('device_address') != address
                    or p.get('device_name') != 'Yen Linh'
                    or (str(p.get('status_code')), str(p.get('type_code'))) != ('1', '0')):
                return list(rows), failure, []
    except (KeyError, TypeError, ValueError, AttributeError):
        return list(rows), failure, []
    output = [r for r in rows if str(r.get('_vera_event_id')) not in EXPECTED]
    audit = [{'id': REVIEW_ID, 'username': 'Yến Linh', 'profile_id': 217,
              'event_ids': list(EXPECTED), 'confirmed_at': CONFIRMED_AT,
              'reason': 'Operator confirmed test scans; employee continued working.',
              'raw_evidence_preserved': True}]
    return output, [], audit

"""One event-bound, operator-confirmed identity; original evidence stays intact.

The operator confirmed Anh Nguyen -> Gia Anh on 29-09-2026 at 21:21:48 +07.
A subsequent read-only comparison matched event 79335 on the device/archive,
the archive digest and Gia Anh's already-confirmed profile 198. Both versions
of the scan have a null reference. This is not a general name fallback and
does not identify the scan as an arrival, departure or test.
"""
import hashlib
import json
from vera_facegate_readiness import reference

REVIEW_ID = 'gia-anh-identity-2026-09-29-79335'
EVENT_ID = '79335'
OCCURRED_AT = '2026-09-29T16:31:37+07:00'
PAYLOAD_SHA256 = '2ee4c7619c1f4578ab9d70e470823a9f95874443db149eab9f574e99ece1c983'
ADDRESS = '192.168.1.34'
USERNAME = 'Gia Anh'
REFERENCE = (0, 0, 12910592)
MAPPING_CONFIRMED_AT = '2026-09-29T04:27:27.238000+00:00'
OPERATOR_CONFIRMED_AT = '2026-09-29T21:21:48+07:00'


def resolve(events, index, employees, address):
    """Return exact approved bindings, failures and audit metadata; no I/O."""
    selected = [e for e in events if str(e.get('event_id')) == EVENT_ID]
    if not selected:
        return {}, [], []
    invalid = [{'event_id': EVENT_ID, 'reason': 'reviewed_identity_invalid',
                'review_id': REVIEW_ID}]
    mapping = index.get(REFERENCE)
    people = [p for p in employees if p.get('username') == USERNAME]
    if (len(selected) != 1 or address != ADDRESS or not mapping
            or mapping.get('username') != USERNAME
            or str(mapping.get('profile_id')) != '198'
            or mapping.get('device_name') != 'Anh Nguyen'
            or mapping.get('device_address') != ADDRESS
            or reference(mapping.get('registration_ref')) != REFERENCE
            or mapping.get('confirmed_at') != MAPPING_CONFIRMED_AT
            or not mapping.get('confirmed_by')
            or sum(str(m.get('profile_id')) == '198' for m in index.values()) != 1
            or len(people) != 1 or people[0].get('role') != 'letan'):
        return {}, invalid, []
    event = selected[0]
    try:
        payload = event['payload_json']
        payload = json.loads(payload) if isinstance(payload, str) else payload
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                               separators=(',', ':')).encode('utf-8')).hexdigest()
        if (str(event.get('occurred_at')) != OCCURRED_AT
                or digest != PAYLOAD_SHA256
                or event.get('payload_sha256', digest) != digest):
            return {}, invalid, []
    except (KeyError, ValueError, TypeError):
        return {}, invalid, []
    binding = {(EVENT_ID, OCCURRED_AT): {'mapping': dict(mapping), 'review_id': REVIEW_ID}}
    audit = [{'id': REVIEW_ID, 'username': USERNAME, 'profile_id': 198,
              'event_id': EVENT_ID, 'occurred_at': OCCURRED_AT,
              'payload_sha256': PAYLOAD_SHA256, 'confirmed_at': OPERATOR_CONFIRMED_AT,
              'review_type': 'identity_only', 'raw_evidence_preserved': True}]
    return binding, [], audit

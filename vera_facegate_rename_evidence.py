"""Recognize name-only archive drift proven by a verified device rename.

Both immutable payloads stay stored. No name fallback, scan-direction inference
or relaxation for photo references, times, status or device changes is allowed.
"""
import hashlib
import json
from vera_facegate_readiness import reference


def _payload(value):
    value = json.loads(value) if isinstance(value, str) else value
    if not isinstance(value, dict):
        raise ValueError('invalid_payload')
    return value


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def verified_name_drift(event, conflict, index, address, jobs):
    try:
        if (str(event['event_id']) != str(conflict['event_id'])
                or event['occurred_at'] != conflict['occurred_at']):
            return None
        original = _payload(event['payload_json'])
        observed = _payload(conflict['observed_payload_json'])
        if (_digest(original) != event['payload_sha256']
                or _digest(original) != conflict['stored_payload_sha256']
                or _digest(observed) != conflict['observed_payload_sha256']
                or {k for k in set(original) | set(observed)
                    if original.get(k) != observed.get(k)} != {'device_name'}):
            return None
        ref = reference(original.get('registration_ref'))
        owner = index.get(ref) if ref else None
        if (not owner or not owner.get('confirmed_by')
                or reference(owner.get('registration_ref')) != ref
                or reference(observed.get('registration_ref')) != ref
                or original.get('device_address') != address
                or observed.get('device_address') != address
                or owner.get('device_address') != address
                or owner.get('device_name') != observed.get('device_name')):
            return None
        matched = [j for j in jobs if j.get('status') == 'verified'
                   and j.get('employee_username') == owner.get('username')
                   and j.get('device_address') == address
                   and str(j.get('profile_id')) == str(owner.get('profile_id'))
                   and reference(_payload(j.get('registration_ref'))) == ref
                   and j.get('old_name') == original.get('device_name')
                   and j.get('new_name') == observed.get('device_name')]
        if not matched:
            return None
        return {'event_id': str(event['event_id']), 'occurred_at': event['occurred_at'],
                'review_type': 'verified_device_name_only',
                'stored_payload_sha256': conflict['stored_payload_sha256'],
                'observed_payload_sha256': conflict['observed_payload_sha256'],
                'raw_evidence_preserved': True}
    except (KeyError, TypeError, ValueError):
        return None


def review_conflicts(events, conflicts, index, address, jobs):
    retained, reviews = [], []
    by_key = {}
    for event in events:
        by_key.setdefault((str(event['event_id']), event['occurred_at']), []).append(event)
    for conflict in conflicts:
        originals = by_key.get((str(conflict['event_id']), conflict['occurred_at']), [])
        review = (verified_name_drift(originals[0], conflict, index, address, jobs)
                  if len(originals) == 1 else None)
        if review:
            reviews.append(review)
        else:
            retained.append(conflict)
    return retained, reviews

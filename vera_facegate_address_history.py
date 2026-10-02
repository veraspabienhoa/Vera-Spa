"""Read-only acceptance of evidence preceding an explicitly verified IP move.

An IP alone is never an identity. Only the current confirmed mapping's exact
reference can use its own saved reconfirmation, before that confirmation time.
No global address alias, name fallback, archive rewrite or device I/O is used.
"""
from datetime import datetime

from vera_facegate_readiness import reference


def accepts_address(mapping, evidence_address, current_address, occurred_at):
    if evidence_address == current_address:
        return True
    if not isinstance(mapping, dict) or not mapping.get('confirmed_by'):
        return False
    history = mapping.get('ip_reconfirmation')
    if not isinstance(history, dict):
        return False
    if not (mapping.get('device_address') == current_address
            and mapping.get('confirmed_by') == history.get('verified_by', 'vps-admin:ip-reconfirmation')
            and history.get('current_address') == current_address
            and history.get('previous_address') == evidence_address
            and evidence_address and current_address
            and history.get('previous_confirmed_by')
            and history.get('method') == 'exact_profile_reference_and_name'
            and mapping.get('confirmed_at') == history.get('verified_at')):
        return False
    try:
        instant = datetime.fromisoformat(str(occurred_at).replace('Z', '+00:00'))
        verified = datetime.fromisoformat(str(history['verified_at']).replace('Z', '+00:00'))
        return (instant.utcoffset() is not None and verified.utcoffset() is not None
                and instant <= verified)
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def accepts_event(mapping, payload, current_address, occurred_at):
    if payload.get('device_address', '') == current_address:
        return True
    if not isinstance(mapping, dict):
        return False
    ref = reference(payload.get('registration_ref'))
    return bool(ref and ref == reference(mapping.get('registration_ref'))
                and accepts_address(mapping, payload.get('device_address', ''),
                                    current_address, occurred_at))


def merge_verified_profiles(current, selected, address, actor, verified_at):
    """Merge live-verified candidates without reassigning an existing identity.

    Caller locks and rechecks its mapping snapshot and active employees first.
    A stale mapping is restored only by its exact profile, reference, name and
    owner; no TimeSoft code is required or substituted for an existing code.
    """
    value = [dict(row) for row in current]
    applied, skipped = [], []
    for candidate in selected:
        uid, username = candidate['profile_id'], candidate['username']
        owners = [i for i, row in enumerate(value) if row.get('profile_id') == uid
                  or row.get('username') == username
                  or reference(row.get('registration_ref')) == reference(candidate.get('registration_ref'))]
        if not owners:
            value.append(dict(candidate))
            applied.append(candidate)
            continue
        if len(owners) != 1:
            skipped.append({'profile_id': uid, 'reason': 'mapping_conflict'})
            continue
        pos = owners[0]
        old = value[pos]
        if (old.get('profile_id') != uid or old.get('username') != username
                or not reference(old.get('registration_ref'))
                or reference(old.get('registration_ref')) != reference(candidate.get('registration_ref'))
                or old.get('device_name') != candidate.get('device_name')
                or not old.get('confirmed_by') or not old.get('device_address')):
            skipped.append({'profile_id': uid, 'reason': 'existing_identity_changed'})
            continue
        if old['device_address'] == address:
            continue
        restored = {**old, 'device_address': address, 'confirmed_by': actor,
                    'confirmed_at': verified_at, 'ip_reconfirmation': {
                        'previous_address': old['device_address'], 'current_address': address,
                        'previous_confirmed_by': old['confirmed_by'],
                        'previous_confirmed_at': old.get('confirmed_at'),
                        'verified_by': actor, 'verified_at': verified_at,
                        'method': 'exact_profile_reference_and_name'}}
        value[pos] = restored
        applied.append(restored)
    return value, applied, skipped

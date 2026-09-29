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
            and mapping.get('confirmed_by') == 'vps-admin:ip-reconfirmation'
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

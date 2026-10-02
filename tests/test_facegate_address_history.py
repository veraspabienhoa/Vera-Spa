from copy import deepcopy
from datetime import date
import json

import pytest

import vera_facegate_attendance as fg
import vera_facegate_checkout_review as cr

OLD = '192.168.1.26'
NEW = '192.168.1.34'
VERIFIED = '2026-09-29T04:27:00+00:00'
REF = {'file_type': 0, 'file_index': 0, 'file_position': 12345}


def mapping():
    return {'username': 'Test Staff', 'profile_id': 42, 'registration_ref': deepcopy(REF),
            'device_address': NEW, 'confirmed_by': 'vps-admin:ip-reconfirmation',
            'confirmed_at': VERIFIED, 'ip_reconfirmation': {
                'previous_address': OLD, 'current_address': NEW,
                'previous_confirmed_by': 'admin', 'verified_at': VERIFIED,
                'method': 'exact_profile_reference_and_name'}}


def event(address=OLD, stamp='2026-09-28T09:30:00+07:00', ref=REF):
    return {'event_id': '1', 'occurred_at': stamp,
            'payload_json': json.dumps({'device_address': address,
                'registration_ref': ref, 'device_name': 'Test Staff',
                'status_code': '1', 'type_code': '0'})}


def adapt(scan, m):
    return fg.adapt_events([scan], [m], [{'username': 'Test Staff', 'role': 'nhanvien'}],
                           NEW, date(2026, 9, 28), date(2026, 9, 29),
                           lambda *_: ('Ca 1', '09:00', '17:00'))


def test_reconfirmed_exact_reference_reads_immutable_old_evidence():
    scan, m = event(), mapping()
    before = deepcopy((scan, m))
    rows, issues, _ = adapt(scan, m)
    assert len(rows) == 1 and not issues
    assert rows[0]['_vera_identity_resolution'] == 'registration_ref'
    assert (scan, m) == before


@pytest.mark.parametrize('mutation', [
    'no_history', 'wrong_previous', 'wrong_current', 'no_operator', 'wrong_method',
    'naive_time', 'invalid_time', 'reconfirmed_later', 'different_actor',
    'unconfirmed', 'post_move_event', 'third_address', 'missing_reference', 'stale_reference',
])
def test_address_history_never_bypasses_identity_or_transition_guards(mutation):
    m, scan = mapping(), event()
    h = m['ip_reconfirmation']
    if mutation == 'no_history': m.pop('ip_reconfirmation')
    elif mutation == 'wrong_previous': h['previous_address'] = '192.168.1.99'
    elif mutation == 'wrong_current': h['current_address'] = '192.168.1.99'
    elif mutation == 'no_operator': h['previous_confirmed_by'] = ''
    elif mutation == 'wrong_method': h['method'] = 'same_name'
    elif mutation == 'naive_time': h['verified_at'] = m['confirmed_at'] = '2026-09-29T11:27:00'
    elif mutation == 'invalid_time': h['verified_at'] = m['confirmed_at'] = 'bad'
    elif mutation == 'reconfirmed_later': m['confirmed_at'] = '2026-09-30T00:00:00+07:00'
    elif mutation == 'different_actor': m['confirmed_by'] = 'different-admin'
    elif mutation == 'unconfirmed': m['confirmed_by'] = ''
    elif mutation == 'post_move_event': scan = event(stamp='2026-09-29T11:27:01+07:00')
    elif mutation == 'third_address': scan = event(address='192.168.1.99')
    elif mutation == 'missing_reference': scan = event(ref=None)
    elif mutation == 'stale_reference': scan = event(ref={**REF, 'file_position': 999})
    rows, issues, _ = adapt(scan, m)
    assert not rows and issues[0]['reason'] == 'device_address_changed'


def test_new_address_still_uses_existing_reference_guard():
    rows, issues, _ = adapt(event(address=NEW, ref=None), mapping())
    assert not rows and issues[0]['reason'] == 'unmapped_reference'


def test_authenticated_reconfirmation_actor_must_match_saved_verifier():
    m = mapping()
    m['confirmed_by'] = m['ip_reconfirmation']['verified_by'] = 'web-admin'
    rows, issues, _ = adapt(event(), m)
    assert len(rows) == 1 and not issues
    m['confirmed_by'] = 'other-admin'
    rows, issues, _ = adapt(event(), m)
    assert not rows and issues[0]['reason'] == 'device_address_changed'


@pytest.mark.parametrize('changed', ['profile_id', 'username', 'device_name', 'confirmed_by', 'duplicate'])
def test_ip_reconfirmation_does_not_transfer_or_duplicate_identity(changed):
    from vera_facegate_address_history import merge_verified_profiles
    old = mapping()
    old['employee_code'] = ''
    candidate = {**old, 'device_address': OLD}
    current = [deepcopy(old)]
    if changed == 'duplicate': current.append(deepcopy(old))
    elif changed == 'confirmed_by': current[0][changed] = ''
    elif changed == 'profile_id': candidate[changed] = 43
    else: candidate[changed] = 'different'
    before = deepcopy(current)
    value, applied, skipped = merge_verified_profiles(current, [candidate], OLD, 'web-admin', VERIFIED)
    assert value == before and current == before and not applied and skipped


def test_unknown_status_on_old_address_stays_blocking():
    scan = event()
    payload = json.loads(scan['payload_json'])
    payload['status_code'] = '9'
    scan['payload_json'] = json.dumps(payload)
    rows, issues, _ = adapt(scan, mapping())
    assert not rows and issues[0]['reason'] == 'unverified_status_type'


def review_fixture():
    m = {**mapping(), 'username': cr.CASE['username'], 'device_address': OLD,
         'confirmed_by': 'admin'}
    staff = [{'username': cr.CASE['username'], 'role': 'letan'}]
    events = [{**e, 'payload_json': {'device_address': OLD, 'registration_ref': deepcopy(REF),
               'status_code': '1', 'type_code': '0'}} for e in deepcopy(cr.CASE['events'])]
    old_index = {cr.ref(REF): m}
    review = cr.prepare_case(events, old_index, staff, OLD, 'test-device',
                             'admin', '2026-09-28T12:00:00+07:00')
    current = {**mapping(), 'username': cr.CASE['username']}
    return events, review, {cr.ref(REF): current}, staff


def test_saved_checkout_and_readonly_case_rerun_survive_verified_move():
    events, review, index, staff = review_fixture()
    before = deepcopy((events, review, index))
    assert len(cr.validate_review(review, events, index, staff, NEW, 'test-device')) == 5
    proposed = cr.prepare_case(events, index, staff, NEW, 'test-device', 'admin',
                               '2026-09-29T12:00:00+07:00')
    assert cr.stage_review([review], proposed) == ([review], False)
    assert (events, review, index) == before


def test_review_fingerprints_still_reject_rewritten_archive():
    events, review, index, staff = review_fixture()
    events[0]['payload_json']['device_address'] = NEW
    with pytest.raises(cr.ReviewError, match='review_evidence_changed'):
        cr.validate_review(review, events, index, staff, NEW, 'test-device')


def test_review_cannot_claim_an_unverified_old_address():
    events, review, index, staff = review_fixture()
    index[cr.ref(REF)].pop('ip_reconfirmation')
    with pytest.raises(cr.ReviewError, match='review_device_changed'):
        cr.validate_review(review, events, index, staff, NEW, 'test-device')

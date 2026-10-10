from copy import deepcopy
from datetime import date, datetime
import json

import pytest

import vera_facegate_attendance as fg
import vera_facegate_identity_review as review
import vera_facegate_runtime as runtime
from vera_facegate_control_log import VN_TZ

DAY = date(2026, 9, 29)
REF = dict(zip(('file_type', 'file_index', 'file_position'), review.REFERENCE))
STAFF = [{'username': 'Gia Anh', 'full_name': 'Nguyễn Gia Anh', 'role': 'letan'}]
MAPPING = {'username': 'Gia Anh', 'profile_id': 198, 'device_name': 'Anh Nguyen',
           'device_address': review.ADDRESS, 'registration_ref': REF,
           'confirmed_by': 'operator', 'confirmed_at': review.MAPPING_CONFIRMED_AT}


def event():
    return {'event_id': review.EVENT_ID, 'occurred_at': review.OCCURRED_AT,
            'payload_sha256': review.PAYLOAD_SHA256,
            'payload_json': json.dumps({'device_address': review.ADDRESS,
                'device_name': 'Anh Nguyen', 'registration_ref': None,
                'status_code': '1', 'type_code': '0'}, sort_keys=True,
                ensure_ascii=False, separators=(',', ':'))}


def test_only_exact_approved_identity_and_immutable_original_evidence():
    events, index, people = [event()], {review.REFERENCE: deepcopy(MAPPING)}, deepcopy(STAFF)
    before = deepcopy((events, index, people))
    bindings, issues, audit = review.resolve(events, index, people, review.ADDRESS)
    assert not issues
    assert bindings[(review.EVENT_ID, review.OCCURRED_AT)]['mapping']['username'] == 'Gia Anh'
    assert audit[0]['review_type'] == 'identity_only' and audit[0]['raw_evidence_preserved']
    assert (events, index, people) == before
    assert json.loads(events[0]['payload_json'])['registration_ref'] is None


@pytest.mark.parametrize('change', ['timestamp', 'stored_digest', 'malformed_payload',
    'name', 'address', 'status', 'type', 'reference', 'extra_field', 'duplicate',
    'owner', 'profile', 'mapping_address', 'mapping_name', 'mapping_ref',
    'confirmation', 'reconfirmed', 'role', 'missing_employee', 'duplicate_employee',
    'duplicate_profile', 'current_address'])
def test_changed_review_evidence_or_mapping_fails_closed(change):
    events, index, people, address = [event()], {review.REFERENCE: deepcopy(MAPPING)}, deepcopy(STAFF), review.ADDRESS
    mapping = index[review.REFERENCE]
    if change == 'timestamp': events[0]['occurred_at'] = '2026-09-29T16:31:38+07:00'
    elif change == 'stored_digest': events[0]['payload_sha256'] = '0' * 64
    elif change == 'malformed_payload': events[0]['payload_json'] = '{'
    elif change in {'name', 'address', 'status', 'type', 'reference', 'extra_field'}:
        payload = json.loads(events[0]['payload_json'])
        key, value = {'name': ('device_name', 'Gia Anh'),
            'address': ('device_address', '192.168.1.26'), 'status': ('status_code', '0'),
            'type': ('type_code', '1'), 'reference': ('registration_ref', REF),
            'extra_field': ('new_field', True)}[change]
        payload[key] = value
        events[0]['payload_json'] = payload
    elif change == 'duplicate': events.append(deepcopy(events[0]))
    elif change == 'owner': mapping['username'] = 'Other'
    elif change == 'profile': mapping['profile_id'] = 199
    elif change == 'mapping_address': mapping['device_address'] = '192.168.1.26'
    elif change == 'mapping_name': mapping['device_name'] = 'Other'
    elif change == 'mapping_ref': mapping['registration_ref'] = {**REF, 'file_position': 99}
    elif change == 'confirmation': mapping['confirmed_by'] = ''
    elif change == 'reconfirmed': mapping['confirmed_at'] = '2026-09-30T00:00:00+00:00'
    elif change == 'role': people[0]['role'] = 'nhanvien'
    elif change == 'missing_employee': people.clear()
    elif change == 'duplicate_employee': people.append(deepcopy(people[0]))
    elif change == 'duplicate_profile': index[(0, 0, 999)] = {**mapping, 'username': 'Other'}
    else: address = '192.168.1.26'
    before = deepcopy((events, index, people))
    bindings, issues, audit = review.resolve(events, index, people, address)
    assert not bindings and not audit and issues[0]['reason'] == 'reviewed_identity_invalid'
    assert (events, index, people) == before


def projection(monkeypatch, events, *, shift=('Ca 2', '17:00', '22:00')):
    import vera_web_v2_attendance_query_perf as attendance
    import vera_facegate_checkout_review as checkout
    monkeypatch.setattr(fg, 'mapping_device_id', lambda: 'test-device')
    monkeypatch.setattr(checkout, 'read_reviews', lambda *_: [])
    monkeypatch.setattr(fg, 'read_evidence', lambda *_, **__: (review.ADDRESS, [MAPPING], events, [], []))
    monkeypatch.setattr(attendance, '_active_roster', lambda _: STAFF)
    monkeypatch.setattr(attendance.snapshot, '_shift_break_settings', lambda _: ([], {}))
    monkeypatch.setattr(attendance, '_schedule_map', lambda *_: {})
    monkeypatch.setattr(attendance, '_vera_shift_fields', lambda *_: shift)
    return fg.project_evidence(object(), DAY, DAY)


def test_projection_resolves_only_one_scan_and_preserves_real_shift_and_other_blockers(monkeypatch):
    approved, unknown = event(), event()
    unknown['event_id'] = '79336'
    unknown['occurred_at'] = '2026-09-29T16:32:00+07:00'
    events = [approved, unknown]
    before = deepcopy(events)
    data = projection(monkeypatch, events)
    assert len(data['rows']) == 1
    row = data['rows'][0]
    assert row['EmployeeName'] == 'Gia Anh'
    assert row['_vera_identity_resolution'] == 'operator_reviewed_identity'
    assert row['_vera_identity_review_id'] == review.REVIEW_ID
    assert row['_vera_checkin_at'] == review.OCCURRED_AT
    assert (row['StartWorkTime'], row['EndWorkTime']) == ('17:00', '22:00')
    assert data['issues'] == [{'event_id': '79336', 'reason': 'unmapped_reference',
                              'registration_ref': None, 'device_name': 'Anh Nguyen'}]
    assert data['events'] == before == events
    assert data['identity_reviews'][0]['event_id'] == review.EVENT_ID


def test_approved_identity_does_not_invent_a_shift_or_checkout(monkeypatch):
    data = projection(monkeypatch, [event()], shift=('', '', ''))
    assert not data['rows']
    assert data['issues'] == [{'event_id': review.EVENT_ID, 'reason': 'no_vera_shift', 'username': 'Gia Anh'}]
    data = projection(monkeypatch, [event()])
    record = {'employee_name': 'Gia Anh', 'date': '29/09/2026', 'employee_role': 'letan',
              'shift': 'Ca 2', 'shift_start': '17:00', 'shift_end': '22:00',
              'check_in': '16:31:37', 'check_out': '', 'punch_datetimes': ['2026-09-29T16:31:37'],
              'attendance_expected': True}
    rows = runtime.annotate(fg.finish_records([record], []), data,
                            now=datetime(2026, 9, 29, 21, tzinfo=VN_TZ))
    assert rows[0]['check_out'] == '' and rows[0]['attendance_pending']
    assert 'missing_check_out' in rows[0]['attendance_pending_reasons']
    assert 'shift_still_open' in rows[0]['attendance_pending_reasons']
    assert 'unresolved_evidence' not in rows[0]['attendance_pending_reasons']
    assert rows[0]['applied_identity_review_ids'] == [review.REVIEW_ID]
    assert not rows[0]['payable_minutes_verified']


def test_invalid_review_cannot_fall_through_to_an_ordinary_valid_reference(monkeypatch):
    changed = event()
    payload = json.loads(changed['payload_json'])
    payload['registration_ref'] = REF
    changed['payload_json'] = payload
    data = projection(monkeypatch, [changed])
    assert not data['rows'] and not data['identity_reviews']
    assert any(i['reason'] == 'reviewed_identity_invalid' for i in data['issues'])


def test_no_global_name_alias_or_future_event_exception(monkeypatch):
    other = event(); other['event_id'] = '99999'
    assert review.resolve([other], {review.REFERENCE: MAPPING}, STAFF, review.ADDRESS) == ({}, [], [])
    assert projection(monkeypatch, [other])['issues'][0]['reason'] == 'unmapped_reference'
    # The ordinary adapter still refuses null references without a reviewed binding.
    assert fg.adapt_events([event()], [MAPPING], STAFF, review.ADDRESS, DAY, DAY,
                           lambda *_: ('Ca 2', '17:00', '22:00'))[1][0]['reason'] == 'unmapped_reference'


def test_review_removes_global_identity_block_but_retains_missing_evidence(monkeypatch):
    data = projection(monkeypatch, [event()])
    data['index'][(0, 0, 99)] = {'username': 'Other'}
    rows = [{'employee_name': name, 'date': '29/09/2026', 'employee_role': 'letan',
             'shift': 'Ca 2', 'shift_start': '17:00', 'shift_end': '22:00',
             'check_in': '16:31:37', 'check_out': '', 'attendance_expected': True}
            for name in ['Gia Anh', 'Other']]
    annotated = runtime.annotate(rows, data, now=datetime(2026, 9, 29, 21, tzinfo=VN_TZ))
    for row in annotated:
        assert not row['attendance_evidence_issues']
        assert 'unresolved_evidence' not in row['attendance_pending_reasons']
        assert 'missing_check_out' in row['attendance_pending_reasons']
        assert row['attendance_pending'] and not row['payable_minutes_verified']
    assert annotated[1]['applied_identity_review_ids'] == []

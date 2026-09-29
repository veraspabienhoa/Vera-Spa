from copy import deepcopy
from datetime import date
from types import SimpleNamespace
import sys
import pytest
import vera_facegate_test_scans as review
import vera_facegate_attendance as fg

ADDR = '192.168.1.34'
REF = {'file_type': 0, 'file_index': 0, 'file_position': 14155776}
MAPPING = {'username': 'Yến Linh', 'profile_id': 217, 'confirmed_by': 'admin',
           'device_address': ADDR, 'registration_ref': REF}
INDEX = {review.REFERENCE: MAPPING}


def events():
    return [{'event_id': eid, 'occurred_at': stamp, 'payload_json': {
        'device_address': ADDR, 'device_name': 'Yen Linh', 'registration_ref': dict(REF),
        'status_code': '1', 'type_code': '0'}} for eid, stamp in review.EXPECTED.items()]


def test_only_exact_pair_removed_and_raw_evidence_immutable():
    raw = events()
    rows = [{'_vera_event_id': x} for x in ['79258', '79329', '79330', 'later-exit']]
    before = deepcopy((rows, raw, INDEX))
    output, issues, audit = review.exclude_reviewed_test_scans(rows, raw, INDEX, ADDR)
    assert output == [rows[0], rows[-1]] and not issues
    assert audit[0]['event_ids'] == ['79329', '79330']
    assert (rows, raw, INDEX) == before


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'time', 'ref', 'name', 'status', 'address', 'profile', 'owner'])
def test_changed_evidence_keeps_scans_and_blocks_review(change):
    raw, index = events(), deepcopy(INDEX)
    if change == 'missing': raw.pop()
    elif change == 'duplicate': raw.append(deepcopy(raw[0]))
    elif change == 'time': raw[0]['occurred_at'] = '2026-09-29T14:22:22+07:00'
    elif change == 'ref': raw[0]['payload_json']['registration_ref'] = None
    elif change == 'name': raw[0]['payload_json']['device_name'] = 'Other'
    elif change == 'status': raw[0]['payload_json']['status_code'] = '0'
    elif change == 'address': raw[0]['payload_json']['device_address'] = '192.168.1.26'
    elif change == 'profile': index[review.REFERENCE]['profile_id'] = 999
    else: index[review.REFERENCE]['username'] = 'Other'
    rows = [{'_vera_event_id': '79329'}]
    output, issues, audit = review.exclude_reviewed_test_scans(rows, raw, index, ADDR)
    assert output == rows and issues and not audit


def test_preview_excludes_test_checkout_but_preserves_raw_comparison(monkeypatch):
    import vera_facegate_checkout_review as checkout
    monkeypatch.setattr(fg, 'mapping_device_id', lambda: 'test-facegate')
    raw = events()
    morning = deepcopy(raw[0])
    morning.update(event_id='79258', occurred_at='2026-09-29T09:02:57+07:00')
    raw.insert(0, morning)
    staff = [{'username': 'Yến Linh', 'full_name': 'Yến Linh', 'role': 'letan'}]
    conn = object()
    monkeypatch.setattr(checkout, 'read_reviews', lambda *_: [])
    monkeypatch.setattr(fg, 'read_evidence', lambda *_: (ADDR, [MAPPING], raw, []))
    observed = []
    def calculate(c, first, last, *, datasets):
        assert c is conn
        scans = datasets[0]['payload'] if datasets else []
        observed.append(deepcopy(scans))
        if not scans: return []
        return [{'date': '29/09/2026', 'employee_name': 'Yến Linh', 'employee_role': 'letan',
                 'shift_start': '09:00', 'shift_end': '17:00', 'check_in': '09:02:57',
                 'check_out': '', 'punch_datetimes': [s['_vera_checkin_at'] for s in scans],
                 'attendance_expected': True}]
    reader = SimpleNamespace(_active_roster=lambda _: staff,
        snapshot=SimpleNamespace(_shift_break_settings=lambda _: ([], {})),
        _schedule_map=lambda *_: {}, _vera_shift_fields=lambda *_: ('Ca 1', '09:00', '17:00'),
        _timesoft_datasets=lambda *_: [], _records_v42_fast=calculate)
    monkeypatch.setitem(sys.modules, 'vera_web_v2_attendance_query_perf', reader)
    monkeypatch.setattr(fg, 'mapping_candidates', lambda *_: [])
    compared = []
    def compare(left, right, *_):
        compared.extend(right[0]['payload'])
        return []
    monkeypatch.setattr(fg, 'compare_punches', compare)
    report = fg.preview(conn, date(2026, 9, 29), date(2026, 9, 29))
    assert [s['_vera_event_id'] for s in observed[0]] == ['79258']
    assert len(compared) == len(raw) == 3
    assert report['records'][0]['check_out'] == ''
    assert report['applied_test_scan_reviews'][0]['id'] == review.REVIEW_ID
    assert not report['attendance_cutover_ready']
    assert not report['payroll_and_penalties_written']

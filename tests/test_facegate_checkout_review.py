from copy import deepcopy
from datetime import date, timedelta
import json
from types import SimpleNamespace
import sys

import pytest
import vera_facegate_checkout_review as cr

DAY = date(2026, 9, 27)
ADDR = '192.168.1.26'
DEVICE = 'test-facegate'
REF = {'file_type': 0, 'file_index': 0, 'file_position': 14155776}
STAFF = [{'username': 'Yến Linh', 'role': 'letan', 'full_name': 'Yến Linh'}]
MAPPING = {'profile_id': 217, 'username': 'Yến Linh', 'device_address': ADDR,
           'registration_ref': REF, 'confirmed_by': 'admin'}
INDEX = {cr.ref(REF): MAPPING}


def evidence():
    return [{**e, 'payload_json': {'registration_ref': deepcopy(REF),
            'device_address': ADDR, 'device_name': 'Yen Linh',
            'status_code': '1', 'type_code': '0'}} for e in deepcopy(cr.CASE['events'])]


def approved(events=None):
    return cr.prepare_case(evidence() if events is None else events, INDEX, STAFF, ADDR,
                           DEVICE, 'vps-admin:uid=0', '2026-09-28T16:00:00+00:00')


def overlay(events=None, reviews=None, issues=None, start=DAY, rows=None):
    return cr.overlay_rows(rows or [], issues or [], [approved()] if reviews is None else reviews,
                           evidence() if events is None else events, INDEX, STAFF, ADDR,
                           DEVICE, start, DAY + timedelta(days=1), lambda *_: ('Ca 1', '09:00', '17:00'))


def test_five_original_events_preserved_and_explicit_pair_selected():
    events = evidence()
    before = deepcopy(events)
    review = approved(events)
    rows, issues, accepted = overlay(events=events, reviews=[review], issues=[
        {'event_id': '79106', 'reason': 'no_vera_shift'},
        {'event_id': '79107', 'reason': 'no_vera_shift'},
        {'event_id': 'other', 'reason': 'no_vera_shift'}])
    assert len(rows) == 5 and len(accepted) == 1
    assert {r['WorkDateStr'] for r in rows} == {'27/09/2026'}
    assert {r['EndWorkTime'] for r in rows} == {'17:00'}
    assert rows[-1]['_vera_checkin_at'] == '2026-09-28T00:33:58+07:00'
    assert issues == [{'event_id': 'other', 'reason': 'no_vera_shift'}]
    assert events == before


def test_next_day_only_does_not_reuse_exit_as_arrival_or_report_it_unassigned():
    rows, issues, accepted = overlay(start=DAY + timedelta(days=1), issues=[
        {'event_id': '79106', 'reason': 'no_vera_shift'}])
    assert rows == issues == [] and len(accepted) == 1


def test_other_next_day_scans_untouched():
    row = {'WorkDateStr': '28/09/2026', 'EmployeeName': 'Yến Linh',
           '_vera_event_id': '99999', '_vera_checkin_at': '2026-09-28T09:09:21+07:00'}
    rows, _, _ = overlay(rows=[row], start=DAY + timedelta(days=1))
    assert rows == [row]


@pytest.mark.parametrize('mutation', ['missing', 'timestamp', 'payload', 'duplicate_id', 'status', 'address', 'ref'])
def test_changed_evidence_never_consumed(mutation):
    events = evidence()
    if mutation == 'missing': events.pop()
    elif mutation == 'duplicate_id': events.append(deepcopy(events[-1]))
    elif mutation == 'timestamp': events[-1]['occurred_at'] = '2026-09-28T00:34:00+07:00'
    elif mutation == 'payload': events[-1]['payload_json']['device_name'] = 'Other'
    elif mutation == 'status': events[-1]['payload_json']['status_code'] = '0'
    elif mutation == 'address': events[-1]['payload_json']['device_address'] = '192.168.1.27'
    else: events[-1]['payload_json']['registration_ref'] = None
    rows, issues, accepted = overlay(events=events)
    assert rows == accepted == [] and issues[-1]['reason'] == 'reviewed_checkout_invalid'


@pytest.mark.parametrize('field,value', [('device_id', 'other'), ('device_address', '192.168.1.27'),
    ('username', 'Other'), ('profile_id', 999), ('role', 'leader'), ('role', 'nhanvien'),
    ('confirmed_by', ''), ('confirmed_at', '2026-09-28T12:00:00'), ('check_out_event_id', 'missing')])
def test_invalid_review_never_reassigns(field, value):
    review = approved()
    review[field] = value
    assert overlay(reviews=[review])[2] == []


def test_two_reviews_cannot_claim_same_workday_or_events():
    first = approved()
    second = {**first, 'id': 'different-id'}
    rows, issues, accepted = overlay(reviews=[first, second])
    assert not rows and not accepted and len(issues) == 2


def test_unreviewed_middle_scan_blocks_old_confirmation():
    events = evidence()
    events.append({**deepcopy(events[0]), 'event_id': 'extra',
                   'occurred_at': '2026-09-27T15:00:00+07:00'})
    assert overlay(events=events)[1][-1]['detail'] == 'review_additional_employee_evidence'


def test_non_shift_issue_not_cleared_even_on_reviewed_id():
    rows, issues, accepted = overlay(issues=[{'event_id': '79106', 'reason': 'conflicting_duplicate'}])
    assert not rows and not accepted
    assert issues[0]['reason'] == 'conflicting_duplicate'


def test_no_review_no_projection_or_issue_changes():
    raw = {'WorkDateStr': '28/09/2026', 'EmployeeName': 'Other', '_vera_checkin_at': 'time'}
    rows, issues, accepted = overlay(reviews=[], rows=[raw], issues=[{'reason': 'no_vera_shift'}])
    assert rows == [raw] and issues == [{'reason': 'no_vera_shift'}] and not accepted


def test_exact_display_anchors_do_not_overwrite_raw_scans_or_planned_schedule():
    original = {'date': '27/09/2026', 'employee_name': 'Yến Linh', 'employee_role': 'letan',
                'shift_start': '09:00', 'shift_end': '17:00', 'overnight_shift': False,
                'total_minutes': 0, 'attendance_roster_only': False}
    other = {**original, 'date': '28/09/2026', 'check_in': '09:09:21', 'check_out': '18:06:05'}
    actual, unchanged = cr.overlay_records([original, other], [approved()])
    assert actual['check_in_at'] == '2026-09-27T10:08:07+07:00'
    assert actual['check_out_at'] == '2026-09-28T00:33:58+07:00'
    assert actual['punch_times'] == ['10:08:07', '00:33:58']
    assert actual['observed_span_seconds'] == 51951
    assert len(actual['reviewed_raw_events']) == 5
    assert actual['shift_start'] == '09:00' and actual['shift_end'] == '17:00'
    assert actual['overnight_shift'] and not actual['scheduled_overnight_shift']
    assert actual['total_minutes'] == 0 and actual['payable_minutes_verified'] is False
    assert unchanged == other and 'check_out_at' not in original


def test_stage_is_idempotent_and_rejects_a_changed_saved_review():
    review = approved()
    first, changed = cr.stage_review([], review)
    assert changed
    next_review = {**review, 'confirmed_at': '2026-09-28T17:00:00+00:00'}
    assert cr.stage_review(first, next_review) == (first, False)
    with pytest.raises(cr.ReviewError):
        cr.stage_review(first, {**next_review, 'check_out_event_id': '79106'})


def test_previous_day_review_included_only_for_adjacent_range():
    review = approved()
    assert cr.relevant_reviews([review], DAY + timedelta(days=1), DAY + timedelta(days=1)) == [review]
    assert not cr.relevant_reviews([review], DAY + timedelta(days=2), DAY + timedelta(days=2))


def test_saved_review_read_reuses_callers_connection_and_does_not_write():
    calls = []
    class Conn:
        def execute(self, sql, params):
            calls.append(str(sql))
            return SimpleNamespace(scalar=lambda: {'version': 1, 'device_id': DEVICE, 'reviews': [approved()]})
    assert len(cr.read_reviews(Conn(), DEVICE)) == 1
    assert len(calls) == 1 and calls[0].lstrip().startswith('SELECT')


@pytest.mark.parametrize('start', [DAY, DAY + timedelta(days=1)])
def test_preview_integration_reuses_context_day_and_keeps_cutover_closed(monkeypatch, start):
    import vera_facegate_attendance as fg
    review = approved()
    conn = object()
    calls = []
    def read_reviews(connection, device):
        assert connection is conn and device == DEVICE
        return [review]
    monkeypatch.setattr(cr, 'read_reviews', read_reviews)
    monkeypatch.setattr(fg, 'mapping_device_id', lambda: DEVICE)
    def read_evidence(connection, first, last):
        assert connection is conn
        calls.append(first)
        return ADDR, [MAPPING], evidence(), []
    monkeypatch.setattr(fg, 'read_evidence', read_evidence)
    def calculate(connection, first, last, *, datasets):
        assert connection is conn
        grouped = defaultdict(list)
        for r in datasets[0]['payload'] if datasets else []:
            grouped[(r['WorkDateStr'], r['EmployeeName'])].append(r)
        return [{'date': d, 'employee_name': n, 'employee_role': 'letan',
                 'shift_start': '09:00', 'shift_end': '17:00', 'check_in': '', 'check_out': '',
                 'punch_datetimes': [r['_vera_checkin_at'][:19] for r in scans],
                 'attendance_expected': True, 'attendance_roster_only': False}
                for (d, n), scans in grouped.items()]
    from collections import defaultdict
    reader = SimpleNamespace(_active_roster=lambda c: STAFF,
        snapshot=SimpleNamespace(_shift_break_settings=lambda c: ([], {})),
        _schedule_map=lambda *a: {}, _vera_shift_fields=lambda *a: ('Ca 1', '09:00', '17:00'),
        _timesoft_datasets=lambda *a: [], _records_v42_fast=calculate)
    v42 = SimpleNamespace(_norm=lambda s: str(s or '').casefold())
    monkeypatch.setitem(sys.modules, 'vera_web_v2_attendance_query_perf', reader)
    monkeypatch.setitem(sys.modules, 'vera_web_v2_attendance_v42', v42)
    monkeypatch.setattr(fg, 'compare_records', lambda *a: [])
    monkeypatch.setattr(fg, 'compare_punches', lambda *a: [])
    monkeypatch.setattr(fg, 'mapping_candidates', lambda *a: [])
    monkeypatch.setattr(fg, 'raw_punches', lambda *a: {'test_evidence': {}})
    result = fg.preview(conn, start, DAY + timedelta(days=1))
    assert calls == [DAY]
    assert result['applied_checkout_review_ids'] == [review['id']]
    assert result['attendance_cutover_ready'] is False
    assert result['payroll_and_penalties_written'] is False
    assert not result['issues']
    if start == DAY:
        assert result['records'][0]['check_out'] == '00:33:58'
    else:
        assert result['records'] == []

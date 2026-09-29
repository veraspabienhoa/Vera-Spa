"""A missing reference is not a stale, operator-confirmed reference."""
from copy import deepcopy
from datetime import date, timedelta
import json

import pytest

import vera_facegate_attendance as fg

DAY = date(2026, 9, 26)
ADDRESS = '192.168.1.26'
REF = {'file_type': 0, 'file_index': 1, 'file_position': 1420}
STALE = {'file_type': 0, 'file_index': 0, 'file_position': 999999}
STAFF = [{'username': 'Ánh Thử', 'full_name': 'Nguyễn Ánh Thử', 'role': 'nhanvien'}]
MAP = [{'profile_id': 142, 'username': 'Ánh Thử', 'employee_code': '18114968',
        'registration_ref': REF, 'confirmed_by': 'admin', 'device_address': ADDRESS}]


def event(clock='09:59:00', eid=1, day=DAY, **changes):
    return {'event_id': str(eid), 'occurred_at': f'{day}T{clock}+07:00',
            'payload_json': json.dumps({'device_name': 'ANH THU', 'registration_ref': REF,
                'device_address': ADDRESS, 'status_code': '1', 'type_code': '0', **changes})}


def adapt(events, mappings=None, employees=None, shift=('Ca 1', '10:00', '23:00')):
    return fg.adapt_events(events, MAP if mappings is None else mappings,
                          STAFF if employees is None else employees,
                          ADDRESS, DAY, DAY, lambda *_: shift)


@pytest.mark.parametrize('invalid', [
    pytest.param(None, id='null'),
    pytest.param({}, id='empty-object'),
    pytest.param([], id='array'),
    pytest.param('invalid', id='string'),
    pytest.param(0, id='number'),
    pytest.param(False, id='boolean'),
    pytest.param({'file_type': 0}, id='missing-fields'),
    pytest.param({**REF, 'file_position': None}, id='null-position'),
    pytest.param({**REF, 'file_position': 'x'}, id='nonnumeric-position'),
    pytest.param({**REF, 'file_type': 1}, id='wrong-file-type'),
    pytest.param({**REF, 'file_index': -1}, id='negative-index'),
    pytest.param({**REF, 'file_index': 65536}, id='index-out-of-range'),
    pytest.param({**REF, 'file_position': 0}, id='zero-position'),
    pytest.param({**REF, 'file_position': 2**63}, id='position-out-of-range'),
])
def test_invalid_reference_cannot_be_rescued_by_a_confirmed_name(invalid):
    scans = [event(registration_ref=invalid)]
    before = deepcopy((scans, MAP, STAFF))
    rows, issues, _ = adapt(scans)
    assert rows == []
    assert len(issues) == 1 and issues[0]['reason'] == 'unmapped_reference'
    assert (scans, MAP, STAFF) == before


def test_absent_reference_field_cannot_be_rescued_by_a_confirmed_name():
    scan = event()
    payload = json.loads(scan['payload_json'])
    del payload['registration_ref']
    scan['payload_json'] = json.dumps(payload)
    before = deepcopy(scan)
    rows, issues, _ = adapt([scan])
    assert rows == [] and issues[0]['reason'] == 'unmapped_reference'
    assert scan == before


def test_direct_reference_takes_priority_over_a_different_display_name():
    rows, issues, _ = adapt([event(device_name='NOT THE OWNER')])
    assert not issues and len(rows) == 1
    assert rows[0]['EmployeeName'] == STAFF[0]['username']
    assert rows[0]['_vera_identity_resolution'] == 'registration_ref'


@pytest.mark.parametrize('name', ['ANH THU', '  Ánh   Thử  ', 'NGUYEN ANH THU'])
def test_valid_stale_reference_retains_unique_confirmed_name_fallback(name):
    scans = [event(registration_ref=STALE, device_name=name)]
    before = deepcopy((scans, MAP, STAFF))
    rows, issues, _ = adapt(scans)
    assert not issues and len(rows) == 1
    assert rows[0]['EmployeeName'] == 'Ánh Thử'
    assert rows[0]['employeeInfo.EmployeeCode'] == '18114968'
    assert rows[0]['_vera_identity_resolution'] == 'confirmed_unique_device_name'
    assert (scans, MAP, STAFF) == before


@pytest.mark.parametrize('changes,reason', [
    ({'device_address': '192.168.1.27'}, 'device_address_changed'),
    ({'status_code': '0'}, 'unverified_status_type'),
    ({'type_code': '2'}, 'unverified_status_type'),
    ({'device_name': 'ANH TH'}, 'unmapped_reference'),
    ({'device_name': ''}, 'unmapped_reference'),
])
def test_stale_reference_does_not_bypass_other_evidence_guards(changes, reason):
    rows, issues, _ = adapt([event(registration_ref=STALE, **changes)])
    assert rows == [] and issues[0]['reason'] == reason


@pytest.mark.parametrize('mappings', [[], MAP + MAP,
    [{**MAP[0], 'confirmed_by': ''}], [{**MAP[0], 'device_address': '192.168.1.27'}]])
def test_stale_reference_needs_a_unique_confirmed_mapping(mappings):
    rows, issues, _ = adapt([event(registration_ref=STALE)], mappings=mappings)
    assert rows == [] and issues[0]['reason'] == 'unmapped_reference'


def test_ambiguous_confirmed_device_names_remain_unmapped():
    employees = STAFF + [{'username': 'Bình Thử', 'full_name': 'Bình Thử', 'role': 'nhanvien'}]
    mappings = [{**MAP[0], 'device_name': 'SHARED NAME'},
                {**MAP[0], 'username': 'Bình Thử', 'profile_id': 143, 'device_name': 'SHARED NAME',
                 'registration_ref': {**REF, 'file_position': 1430}}]
    rows, issues, _ = adapt([event(registration_ref=STALE, device_name='SHARED NAME')],
                           mappings=mappings, employees=employees)
    assert rows == [] and issues[0]['reason'] == 'unmapped_reference'


def test_name_fallback_never_uses_profile_id_as_timesoft_employee_code():
    rows, issues, _ = adapt([event(registration_ref=STALE)],
                           mappings=[{**MAP[0], 'employee_code': ''}])
    assert not issues and rows[0]['employeeInfo.EmployeeCode'] == ''


def test_reference_guard_does_not_change_overnight_or_duplicate_handling():
    scans = [event('21:58:00'), event('21:58:00'),
             event('00:30:00', 2, DAY + timedelta(days=1))]
    rows, issues, _ = adapt(scans, shift=('Ca đêm', '22:00', '06:00'))
    assert len(rows) == 2 and not issues
    assert {row['WorkDateStr'] for row in rows} == {'26/09/2026'}
    assert rows[-1]['_vera_checkin_at'] == '2026-09-27T00:30:00+07:00'
    rows, issues, _ = adapt([event(), event(status_code='0')])
    assert len(rows) == 1 and issues[0]['reason'] == 'conflicting_duplicate'

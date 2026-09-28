import copy
from datetime import date, datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_facegate_attendance as fg
import vera_web_v2_attendance_query_perf as attendance
import vera_web_v2_attendance_v42 as v42
import vera_web_v2_facegate_attendance as routes

DAY = date(2026, 9, 26)
ADDRESS = '192.168.1.26'
REF = {'file_type': 0, 'file_index': 1, 'file_position': 1420}
STAFF = [{'username': 'Ánh Thử', 'full_name': 'Nguyễn Ánh Thử', 'role': 'nhanvien',
          'work_shift': 'Ca 1', 'shift_start_date': '2026-09-01', 'rotation_cycle': 'Cố định (Không đổi)'}]
MAP = [{'profile_id': 142, 'username': 'Ánh Thử', 'employee_code': '18114968',
        'registration_ref': REF, 'confirmed_by': 'admin', 'device_address': ADDRESS}]


def event(clock='09:59:00', eid=1, day=DAY, **payload):
    return {'event_id': str(eid), 'occurred_at': f'{day}T{clock}+07:00',
            'payload_json': json.dumps({'device_name': 'ANH THU', 'registration_ref': REF,
               'device_address': ADDRESS, 'status_code': '1', 'type_code': '0', **payload})}


def adapt(events, mappings=None, shift=('Ca 1', '10:00', '23:00')):
    return fg.adapt_events(events, MAP if mappings is None else mappings, STAFF,
                           ADDRESS, DAY, DAY, lambda *_: shift)


def test_exact_replay_is_once_but_two_distinct_scans_are_preserved():
    rows, issues, _ = adapt([event(), event(), event('09:59:02', 2)])
    assert len(rows) == 2 and not issues
    assert rows[0]['EmployeeName'] == 'Ánh Thử'
    assert rows[0]['employeeInfo.EmployeeCode'] == '18114968'
    assert 'ANH THU' not in json.dumps(rows)
    assert rows[0]['_vera_checkin_at'] == '2026-09-26T09:59:00+07:00'


@pytest.mark.parametrize('change,reason', [
    ({'registration_ref': None}, 'unmapped_reference'),
    ({'device_address': '192.168.1.27'}, 'device_address_changed'),
    ({'status_code': '0'}, 'unverified_status_type'),
    ({'type_code': '2'}, 'unverified_status_type'),
])
def test_unknown_reference_address_or_status_never_guessed(change, reason):
    rows, issues, _ = adapt([event(**change)])
    assert rows == [] and issues[0]['reason'] == reason


@pytest.mark.parametrize('mappings', [[], MAP + MAP, [{**MAP[0], 'confirmed_by': ''}],
    [{**MAP[0], 'device_address': '192.168.1.27'}], [{**MAP[0], 'username': 'ANH THU'}]])
def test_mapping_requires_exact_existing_vera_identity_and_unique_confirmation(mappings):
    rows, issues, _ = adapt([event()], mappings)
    assert rows == [] and issues[0]['reason'] == 'unmapped_reference'


def test_changed_replay_is_blocked():
    rows, issues, _ = adapt([event(), event(status_code='0')])
    assert len(rows) == 1 and issues[0]['reason'] == 'conflicting_duplicate'


def test_stale_reference_can_use_unique_confirmed_device_name_without_mutating_archive():
    stale = {'file_type': 0, 'file_index': 0, 'file_position': 999999}
    scan = event(registration_ref=stale)
    before = scan['payload_json']
    rows, issues, _ = adapt([scan])
    assert not issues and len(rows) == 1
    assert rows[0]['EmployeeName'] == 'Ánh Thử'
    assert rows[0]['_vera_identity_resolution'] == 'confirmed_unique_device_name'
    assert scan['payload_json'] == before


def test_stale_reference_name_fallback_requires_unique_confirmed_owner():
    employees = STAFF + [{'username': 'ANH THU', 'full_name': 'Khác', 'role': 'nhanvien'}]
    rows, issues, _ = fg.adapt_events([event(registration_ref={'file_type': 0, 'file_index': 0, 'file_position': 999999})],
        MAP, employees, ADDRESS, DAY, DAY, lambda *_: ('Ca 1', '10:00', '23:00'))
    assert rows == [] and issues[0]['reason'] == 'unmapped_reference'


def test_timezone_normalized_before_day_assignment():
    scan = event()
    scan['occurred_at'] = '2026-09-26T02:59:00+00:00'
    assert adapt([scan])[0][0]['MachineTimeCheckInStr'] == '26/09/2026 09:59:00'
    scan['occurred_at'] = '2026-09-26T09:59:00'
    assert adapt([scan])[1][0]['reason'] == 'invalid_timestamp'


def test_overnight_scans_keep_next_day_timestamp_and_previous_workday():
    rows, issues, _ = adapt([event('21:58:00'), event('00:30:00', 2, DAY + timedelta(days=1)),
                             event('05:55:00', 3, DAY + timedelta(days=1))], shift=('Ca đêm', '22:00', '06:00'))
    assert not issues and len(rows) == 3
    assert {row['WorkDateStr'] for row in rows} == {'26/09/2026'}
    assert rows[-1]['_vera_checkin_at'] == '2026-09-27T05:55:00+07:00'
    # An early-morning scan from yesterday's shift cannot check in today.
    rows, issues, _ = adapt([event('00:30:00')], shift=('Ca đêm', '22:00', '06:00'))
    assert not rows and not issues


def test_no_shift_and_overlapping_windows_are_not_calendar_fallbacks():
    assert adapt([event()], shift=('', '', ''))[1][0]['reason'] == 'no_vera_shift'
    instant = datetime(2026, 9, 26, 6)
    windows = {DAY: fg.shift_interval(DAY, '06:00', '18:00'),
               DAY - timedelta(days=1): fg.shift_interval(DAY - timedelta(days=1), '22:00', '06:00')}
    assert fg.business_day(instant, windows) == (None, 'overlapping_shifts')


def test_checkout_role_can_attach_after_midnight_scan_to_previous_overnight_shift():
    instant = datetime(2026, 9, 27, 1, 8)
    windows = {DAY: fg.shift_interval(DAY, '17:30', '01:30'),
               DAY + timedelta(days=1): None}
    assert fg.business_day(instant, windows, allow_checkout=True) == (DAY, '')
    assert fg.business_day(instant, windows, allow_checkout=False) == (DAY, '')


def test_day_shift_does_not_claim_unrelated_after_midnight_checkout():
    instant = datetime(2026, 9, 27, 0, 33)
    windows = {DAY: fg.shift_interval(DAY, '09:00', '17:00')}
    assert fg.business_day(instant, windows, allow_checkout=True) == (None, 'no_vera_shift')


def test_off_shift_scan_remains_unassigned_instead_of_becoming_false_attendance():
    instant = datetime(2026, 9, 27, 1, 9)
    windows = {DAY: fg.shift_interval(DAY, '09:30', '17:30')}
    assert fg.business_day(instant, windows, allow_checkout=True) == (None, 'no_vera_shift')


def test_timestamp_candidates_allow_alias_but_never_infer_device_profile_id():
    rows, _, _ = adapt([event(), event('15:00:00', 2)])
    rows[0]['employeeInfo.Name'] = rows[0]['EmployeeName'] = 'Nguyen Anh Thu'
    output = fg.mapping_candidates([event(), event('15:00:00', 2)], [{'payload': rows}], STAFF, ADDRESS, DAY, DAY)
    assert output[0]['username_candidate'] == 'Ánh Thử'
    assert output[0]['confirmed'] is False
    assert 'profile_id' not in output[0]
    extra = {**rows[0], 'EmployeeName': 'Khác', 'employeeInfo.Name': 'Khác'}
    employees = STAFF + [{'username': 'Khác'}]
    duplicate = [{**r, 'EmployeeName': 'Khác', 'employeeInfo.Name': 'Khác'} for r in rows]
    assert fg.mapping_candidates([event(), event('15:00:00', 2)], [{'payload': rows + duplicate}], employees, ADDRESS, DAY, DAY)[0]['status'] == 'ambiguous'
    assert extra['EmployeeName'] == 'Khác'


def test_raw_comparison_catches_scan_difference_inside_same_five_minute_group():
    a, _, _ = adapt([event(), event('09:59:02', 2)])
    b, _, _ = adapt([event()])
    result = fg.compare_punches([{'payload': a}], [{'payload': b}], STAFF, DAY, DAY)
    assert result[0]['missing_in_facegate'] == ['2026-09-26T09:59:02']


def test_comparison_normalizes_time_format_but_not_real_time_differences():
    a = {'date': '26/09/2026', 'employee_name': 'Ánh Thử', 'check_in': '26/09/2026 09:59:00',
         'shift_start': '10:00', 'punch_times': ['09:59', '15:00:00']}
    b = {**a, 'check_in': '09:59:00', 'shift_start': '10:00:00', 'punch_times': ['09:59:00', '15:00']}
    assert fg.compare_records([a], [b]) == []
    b['check_in'] = '10:00:00'
    assert fg.compare_records([a], [b])[0]['fields'] == ['check_in']


def calculator(monkeypatch, rows, shift=('Ca 1', '10:00', '23:00')):
    definitions = [{'Tên ca': shift[0], 'Giờ bắt đầu': shift[1], 'Giờ kết thúc': shift[2], 'Bộ phận': 'Nhân viên + Leader'}]
    profile = {**STAFF[0], 'work_shift': f'{shift[0]} ({shift[1]}-{shift[2]})'}
    class Result:
        def mappings(self): return self
        def all(self): return [profile]
    class Connection:
        def execute(self, *_args, **_kwargs): return Result()
    monkeypatch.setattr(attendance.snapshot, '_shift_break_settings', lambda _: (definitions, {}))
    monkeypatch.setattr(attendance.department_attendance, 'controls', lambda _: {})
    monkeypatch.setattr(v42, '_eligible_aliases', lambda _: ({'anh thu': 'Ánh Thử'}, {'anh thu': 'nhanvien'}))
    monkeypatch.setattr(attendance, '_schedule_map', lambda *_: {})
    monkeypatch.setattr(attendance, '_append_missing_active_employees', lambda *_: None)
    monkeypatch.setattr(attendance, '_vera_shift_fields', lambda *_: shift)
    monkeypatch.setattr(v42, '_looks_like_final_checkout', lambda *_: False)
    # Exercise actual shared break reconstruction, without importing a web app.
    return attendance._records_v42_fast(Connection(), DAY, DAY, datasets=[{'payload': rows}])[0]


def test_shared_reader_clusters_repeats_and_does_not_invent_normal_checkout(monkeypatch):
    rows, _, _ = adapt([event(), event('09:59:02', 2), event('15:00:00', 3), event('16:30:00', 4)])
    result = calculator(monkeypatch, rows)
    assert result['employee_name'] == 'Ánh Thử'
    assert result['check_in'] == '09:59:00' and result['check_out'] == ''
    assert result['raw_faceid_count'] == 3
    assert result['attendance_preview'] is True
    assert result['payable_minutes_verified'] is False
    assert result['punch_datetimes'][-1] == '2026-09-26T16:30:00'


def test_shared_reader_overnight_first_arrival_after_midnight_is_not_previous_midnight(monkeypatch):
    shift = ('Ca đêm', '22:00', '06:00')
    rows, issues, _ = adapt([event('00:30:00', 1, DAY + timedelta(days=1))], shift=shift)
    assert not issues
    result = calculator(monkeypatch, rows, shift)
    assert result['date'] == '26/09/2026' and result['check_in_at'] == '2026-09-27T00:30:00+07:00'
    assert result['late_minutes'] == 150 and result['overnight_shift'] is True
    assert result['check_out'] == ''


def test_preview_injection_does_not_read_or_change_timesoft_dataset(monkeypatch):
    def forbidden(*_): raise AssertionError('No source read with explicit preview evidence')
    monkeypatch.setattr(attendance, '_datasets', forbidden)
    rows, _, _ = adapt([event()])
    result = calculator(monkeypatch, rows)
    assert result['evidence_source'] == 'facegate'


@pytest.mark.parametrize('role', ['nhanvien', 'leader', 'quanly', 'letan'])
def test_preview_route_is_admin_only_before_connection_checkout(role):
    app = FastAPI()
    def forbidden(): raise AssertionError('Unauthorized database checkout')
    routes.install_facegate_attendance_routes(app, engine_instance=forbidden,
        current_identity=lambda: SimpleNamespace(role=role), identity_type=SimpleNamespace)
    assert TestClient(app).get('/v2/devices/facegate-attendance/preview?start=2026-09-26&end=2026-09-26').status_code == 403


def test_preview_range_is_bounded_before_database_checkout():
    app = FastAPI()
    def forbidden(): raise AssertionError('Invalid range database checkout')
    routes.install_facegate_attendance_routes(app, engine_instance=forbidden,
        current_identity=lambda: SimpleNamespace(role='admin'), identity_type=SimpleNamespace)
    client = TestClient(app)
    for end in ('2026-09-25', '2026-10-03'):
        assert client.get(f'/v2/devices/facegate-attendance/preview?start=2026-09-26&end={end}').status_code == 400

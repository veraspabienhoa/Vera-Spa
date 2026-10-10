"""Synthetic identities only: scoped evidence may never become a global bypass."""
from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

import vera_facegate_attendance as fg
import vera_facegate_runtime as runtime
import vera_attendance_source as source
from vera_facegate_control_log import VN_TZ
from vera_web_v2_break_return_penalty import confirmed_break_return_fact

DAY = date(2026, 10, 10)
NOW = datetime(2026, 10, 10, 19, 50, tzinfo=VN_TZ)
ADDRESS = 'synthetic-device'


def evidence():
    employees = [{'username': name, 'full_name': name, 'role': 'nhanvien'} for name in ('Healthy', 'Affected')]
    mappings = [{'username': p['username'], 'registration_ref': {'file_type': 0, 'file_index': 1, 'file_position': n}, 'confirmed_by': 'synthetic-admin',
                 'device_address': ADDRESS} for n, p in enumerate(employees, 1)]
    def event(n, hour, status='1'):
        return {'event_id': str(n), 'occurred_at': f'2026-10-10T{hour}:00+07:00',
                'payload_json': {'registration_ref': {'file_type': 0, 'file_index': 1, 'file_position': 2 if n == 4 else 1}, 'device_address': ADDRESS,
                                 'status_code': status, 'type_code': '0'}}
    events = [event(1, '10:10'), event(2, '18:00'), event(3, '19:40'), event(4, '10:20', '0')]
    rows, issues, index = fg.adapt_events(events, mappings, employees, ADDRESS, DAY, DAY,
                                        lambda *_: ('Ca 1', '10:00', '23:00'))
    return {'rows': rows, 'issues': issues, 'index': index, 'events': events,
            'syncs': [{'work_date': DAY.isoformat(), 'last_observed_count': 4, 'last_synced_at': NOW.isoformat()}]}


def record(username='Healthy', day=DAY):
    return {'employee_name': username, 'date': day.strftime('%d/%m/%Y'), 'employee_role': 'nhanvien',
            'shift': 'Ca 1', 'shift_start': '10:00', 'shift_end': '23:00',
            'check_in': '10:10:00', 'check_in_at': f'{day}T10:10:00+07:00', 'late_minutes': 10,
            'check_out': '', 'attendance_expected': False, 'break_enabled': True,
            'break_out': '18:00:00', 'break_in': '19:40:00', 'break_planned_minutes': 90}


def test_scoping_is_produced_only_after_confirmed_identity_and_vera_windows():
    data = evidence()
    assert data['issues'][0]['scope'] == 'employee_days'
    assert data['issues'][0]['username'] == 'Affected'
    assert data['issues'][0]['work_dates'] == [DAY.isoformat()]
    assert runtime.blocking_issues(data, DAY, 'Healthy') == []
    assert len(runtime.blocking_issues(data, DAY, 'Affected')) == 1


def test_unaffected_employee_keeps_arrival_and_confirmed_return(monkeypatch):
    data = evidence()
    rows = runtime.annotate([record(), record('Affected')], data, now=NOW)
    good, bad = rows
    assert good['attendance_fine_evidence_ready'] and not good['attendance_evidence_issues']
    assert not bad['attendance_fine_evidence_ready'] and bad['attendance_evidence_issues']
    assert confirmed_break_return_fact(good, DAY)['late_minutes'] == 10
    assert confirmed_break_return_fact(bad, DAY) is None
    monkeypatch.setattr(source, 'source_for', lambda _: 'facegate')
    monkeypatch.setattr(source, 'health', lambda _: {'cache_fresh': True})
    monkeypatch.setattr(runtime, 'records', lambda *_: rows)
    frames = runtime.worker_frames(object(), [DAY])
    assert frames[0][1]['employeeInfo.Name'].tolist() == ['Healthy']
    assert runtime._alert_eligible_users(data, DAY) == {'Healthy'}


@pytest.mark.parametrize('issue', [
    {'reason': 'unmapped_reference'}, {'reason': 'conflicting_duplicate', 'username': 'Affected'},
    {'reason': 'invalid_timestamp'}, {'reason': 'device_address_changed'},
    {'reason': 'reviewed_identity_invalid'}, {'reason': 'overlapping_shifts', 'username': 'Affected'},
    {'reason': 'unverified_status_type', 'scope': 'employee_days', 'username': 'Unknown', 'work_dates': ['2026-10-10']},
    {'reason': 'overlapping_shifts', 'scope': 'employee_days', 'username': 'Affected', 'work_dates': ['not-a-date']},
])
def test_unknown_or_unproven_issue_keeps_global_fail_closed(issue):
    data = evidence(); data['issues'] = [issue]
    rows = runtime.annotate([record(), record('Affected')], data, now=NOW)
    assert all(r['attendance_evidence_issues'] and not r['attendance_fine_evidence_ready'] for r in rows)
    assert all(confirmed_break_return_fact(r, DAY) is None for r in rows)
    assert runtime._alert_eligible_users(data, DAY) == set()


@pytest.mark.parametrize('failure', ['count', 'missing', 'stale', 'future', 'naive_sync', 'naive_event'])
def test_clean_employee_still_needs_complete_fresh_capture(failure):
    data = evidence(); data['issues'] = []
    if failure == 'count': data['syncs'][0]['last_observed_count'] = 5
    if failure == 'missing': data['syncs'] = []
    if failure == 'stale': data['syncs'][0]['last_synced_at'] = (NOW-timedelta(minutes=6)).isoformat()
    if failure == 'future': data['syncs'][0]['last_synced_at'] = (NOW+timedelta(seconds=1)).isoformat()
    if failure == 'naive_sync': data['syncs'][0]['last_synced_at'] = NOW.replace(tzinfo=None).isoformat()
    if failure == 'naive_event': data['events'][0]['occurred_at'] = '2026-10-10T10:10:00'
    row = runtime.annotate([record()], data, now=NOW)[0]
    assert not row['attendance_fine_evidence_ready']
    assert confirmed_break_return_fact(row, DAY) is None


def test_overnight_scope_contains_every_possible_business_day():
    instant = datetime(2026, 10, 11, 1)
    windows = {DAY: fg.shift_interval(DAY, '17:00', '02:00'),
               DAY+timedelta(days=1): fg.shift_interval(DAY+timedelta(days=1), '04:00', '12:00')}
    scope = fg.scoped_issue('overlapping_shifts', 'Affected', instant, windows)
    assert scope['work_dates'] == ['2026-10-10', '2026-10-11']
    data = evidence(); data['issues'] = [{'reason': 'overlapping_shifts', **scope}]
    assert runtime.blocking_issues(data, DAY+timedelta(days=1), 'Affected')
    assert not runtime.blocking_issues(data, DAY+timedelta(days=2), 'Affected')
    assert not runtime.blocking_issues(data, DAY, 'Healthy')


def test_overnight_requires_both_calendar_captures_before_fine():
    now = datetime(2026, 10, 11, 1, tzinfo=VN_TZ)
    data = evidence(); data['issues'] = []
    interval = fg.shift_interval(DAY, '17:00', '02:00')
    data['syncs'][0]['last_synced_at'] = now.isoformat()
    assert 'incomplete_archive' in runtime.fine_evidence_reasons(data, 'Healthy', DAY, now=now, interval=interval)
    data['syncs'].append({'work_date': '2026-10-11', 'last_synced_at': now.isoformat(), 'last_observed_count': 0})
    assert runtime.fine_evidence_reasons(data, 'Healthy', DAY, now=now, interval=interval) == []
    data['syncs'][0]['last_synced_at'] = '2026-10-10T23:59:59+07:00'
    assert 'incomplete_archive' in runtime.fine_evidence_reasons(data, 'Healthy', DAY, now=now, interval=interval)


def test_diagnostics_distinguish_range_global_and_date_scoped_without_identity():
    data = evidence()
    result = runtime.evidence_diagnostics(data, DAY-timedelta(days=1), DAY, now=NOW)
    assert result['scoped_issue_count'] == 1 and result['global_issue_count'] == 0
    assert result['days'][0]['issue_count'] == 0 and result['days'][1]['issue_count'] == 1
    assert result['days'][1]['archive_fresh'] and result['days'][1]['archive_complete']
    assert 'Healthy' not in str(result) and 'Affected' not in str(result)
    data['issues'].append({'reason': 'unmapped_reference'})
    result = runtime.evidence_diagnostics(data, DAY-timedelta(days=1), DAY, now=NOW)
    assert all(d['global_issue_count'] == 1 for d in result['days'])
    assert result['days'][0]['issue_count'] == 1 and result['days'][1]['issue_count'] == 2


def test_financial_guard_is_fail_closed_when_new_evidence_flag_missing():
    row = record(); row['evidence_source'] = 'facegate'
    assert confirmed_break_return_fact(row, DAY) is None



def test_future_prior_day_sync_cannot_authorize_overnight_fine():
    data = evidence(); data['issues'] = []
    now = datetime(2026, 10, 11, 1, tzinfo=VN_TZ)
    data['syncs'][0]['last_synced_at'] = (now+timedelta(days=1)).isoformat()
    data['syncs'].append({'work_date': '2026-10-11', 'last_synced_at': now.isoformat(), 'last_observed_count': 0})
    reasons = runtime.fine_evidence_reasons(data, 'Healthy', DAY, now=now,
                                          interval=fg.shift_interval(DAY, '17:00', '02:00'))
    assert 'stale_archive' in reasons


def test_future_scan_beyond_completed_capture_is_not_complete_evidence():
    data = evidence(); data['issues'] = []
    data['syncs'][0]['last_synced_at'] = '2026-10-10T12:00:00+07:00'
    now = datetime(2026, 10, 10, 12, tzinfo=VN_TZ)
    assert not runtime.archive_complete(data, DAY, before=runtime.archive_sync(data, DAY))
    assert not runtime.annotate([record()], data, now=now)[0]['attendance_fine_evidence_ready']


@pytest.mark.parametrize('paused,fresh,historical', [(True, True, False), (False, False, False),
    (True, True, True), (False, False, True)])
def test_restriction_annotations_survive_pause_or_nonfresh_financial_evidence(monkeypatch, paused, fresh, historical):
    import vera_web_v2_outside_leave_rule as outside
    today = datetime.now(VN_TZ).date()
    day = today-timedelta(days=1) if historical else today
    row = {**record(day=day), 'evidence_source': 'facegate',
           'attendance_evidence_issues': False, 'attendance_fine_evidence_ready': fresh}
    monkeypatch.setattr(outside.auto_check, 'penalties_paused', lambda _: paused)
    monkeypatch.setattr(outside, '_restriction_map', lambda *_: {(day, outside._norm('Healthy')): {'reasons': ['Đi trễ CÓ phép']}})
    monkeypatch.setattr(outside.auto_check, 'load_catalog', lambda *_: pytest.fail('Financial work while paused/stale/historical'))
    output = outside._apply_restrictions_and_penalties(None, object(), [row], day, day)[0]
    assert output['break_alert_suppressed'] is True
    assert output['break_restricted_reason'] == 'Đi trễ CÓ phép'



def test_future_next_calendar_punch_cannot_complete_current_overnight_break():
    data = evidence(); data['issues'] = []
    now = datetime(2026, 10, 10, 22, tzinfo=VN_TZ)
    data['events'].append({'occurred_at': '2026-10-11T00:45:00+07:00'})
    data['syncs'][0]['last_synced_at'] = now.isoformat()
    row = {**record(), 'shift_start': '17:00', 'shift_end': '02:00',
           'break_out': '21:00:00', 'break_in': '00:45:00'}
    result = runtime.annotate([row], data, now=now)[0]
    assert runtime.archive_complete(data, DAY)
    assert 'future_evidence' in result['attendance_fine_evidence_reasons']
    assert not result['attendance_fine_evidence_ready']
    assert confirmed_break_return_fact(result, DAY) is None
    diagnostic = runtime.evidence_diagnostics(data, DAY, DAY, now=now)
    assert diagnostic['global_issue_count'] == 1
    assert diagnostic['reason_counts']['future_or_invalid_event_timestamp'] == 1



def test_long_overnight_window_requires_middle_calendar_capture():
    data = evidence(); data['issues'] = []
    now = datetime(2026, 10, 12, 0, 30, tzinfo=VN_TZ)
    interval = fg.shift_interval(DAY, '23:00', '22:00')
    data['syncs'][0]['last_synced_at'] = now.isoformat()
    data['syncs'].append({'work_date': '2026-10-12', 'last_synced_at': now.isoformat(), 'last_observed_count': 0})
    assert 'incomplete_archive' in runtime.fine_evidence_reasons(data, 'Healthy', DAY, now=now, interval=interval)
    data['syncs'].append({'work_date': '2026-10-11', 'last_synced_at': now.isoformat(), 'last_observed_count': 0})
    assert runtime.fine_evidence_reasons(data, 'Healthy', DAY, now=now, interval=interval) == []

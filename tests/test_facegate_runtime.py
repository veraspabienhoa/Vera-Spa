from copy import deepcopy
from datetime import date, datetime
import json
from types import SimpleNamespace

import pytest

import vera_attendance_source as source
import vera_facegate_runtime as runtime
import vera_facegate_attendance as fg
from vera_facegate_control_log import VN_TZ
from vera_web_v2_department_payroll import _attendance_totals, _recalculate, DEFAULT_CONFIG

DAY = date(2026, 9, 29)


@pytest.fixture
def facegate(monkeypatch, tmp_path):
    path = tmp_path/'source.json'
    monkeypatch.setenv('VERA_ATTENDANCE_SOURCE_FILE', str(path))
    path.write_text(json.dumps({'version': 1, 'source': 'facegate', 'effective_date': DAY.isoformat()}))
    return path


def test_config_missing_keeps_legacy_but_corrupt_config_cannot_reenable_network(monkeypatch, tmp_path):
    path = tmp_path/'source.json'
    monkeypatch.setenv('VERA_ATTENDANCE_SOURCE_FILE', str(path))
    assert source.source_for(DAY) == 'timesoft'
    for value in ('{', '[]', '{"version":1,"source":"facegate","effective_date":"bad"}'):
        path.write_text(value)
        with pytest.raises(RuntimeError): source.require_timesoft_enabled()


def test_cutoff_retains_history_and_disables_all_vendor_logins(facegate):
    assert source.source_for(date(2026, 9, 28)) == 'timesoft'
    assert source.cache_key(DAY) == 'facegate_employee_checkin_20260929'
    with pytest.raises(RuntimeError, match='timesoft_disabled'):
        source.require_timesoft_enabled()
    import timesoft_http_auth
    with pytest.raises(RuntimeError, match='timesoft_disabled'):
        timesoft_http_auth.create_http_authenticated_session(SimpleNamespace())


def evidence():
    return {'index': {1: {'username': 'Employee'}}, 'issues': [],
            'events': [{'occurred_at': '2026-09-29T09:00:00+07:00'},
                       {'occurred_at': '2026-09-29T17:00:00+07:00'}],
            'syncs': [{'work_date': '2026-09-29', 'last_observed_count': 2,
                       'last_synced_at': '2026-09-29T20:00:00+07:00'}]}


def record():
    return {'employee_name': 'Employee', 'date': '29/09/2026', 'employee_role': 'letan',
            'shift_start': '09:00', 'shift_end': '17:00', 'shift': 'Ca 1',
            'check_in': '09:00:00', 'check_out': '17:00:00', 'attendance_expected': True}


def test_payroll_requires_closed_shift_and_complete_identified_evidence(facegate):
    good = runtime.annotate([record()], evidence(), now=datetime(2026, 9, 29, 20, tzinfo=VN_TZ))[0]
    assert good['payable_minutes_verified'] and not good['attendance_preview']
    pending = runtime.annotate([record()], evidence(), now=datetime(2026, 9, 29, 14, tzinfo=VN_TZ))[0]
    assert 'shift_still_open' in pending['attendance_pending_reasons']
    cfg = DEFAULT_CONFIG['letan']
    totals = _attendance_totals([pending], 'Employee', str, cfg)
    assert totals['minutes_ca1'] == 0 and totals['pending_dates'] == ['2026-09-29']
    calculated = _recalculate({'attendance_pending': True, 'hours_ca1': 8}, cfg)
    assert calculated['salary'] is None and calculated['net_salary'] is None
    bad = evidence(); bad['issues'] = [{'reason': 'unmapped_reference'}]
    assert not runtime.annotate([record()], bad, now=datetime(2026, 9, 30, tzinfo=VN_TZ))[0]['payable_minutes_verified']


def test_one_arrival_per_worker_row_keeps_real_date_and_minutes(monkeypatch, facegate):
    conn = object()
    monkeypatch.setattr(source, 'health', lambda c: {'cache_fresh': c is conn})
    monkeypatch.setattr(runtime, 'records', lambda c, a, b: [{**record(),
        'identity_verified': True, 'check_in_at': '2026-09-29T09:02:57+07:00',
        'punch_times': ['09:02:57', '14:21:22', '14:21:24'], 'late_minutes': 2}])
    frames = runtime.worker_frames(conn, [date(2026, 9, 28), DAY])
    assert len(frames) == 1 and len(frames[0][1]) == 1
    row = frames[0][1].iloc[0]
    assert row['MachineTimeCheckInStr'] == '29/09/2026 09:02:57'
    assert row['TotalMinuteInGoLate'] == 2


def test_publish_never_refreshes_from_stale_archive(monkeypatch, facegate):
    data = evidence(); data['rows'] = []
    monkeypatch.setattr(fg, 'project_evidence', lambda *_: data)
    import vera_postgres as vpg
    writes = []
    monkeypatch.setattr(vpg, '_write_dataset_conn', lambda *args: writes.append(args))
    with pytest.raises(fg.EvidenceError, match='stale_archive'):
        runtime.publish(object(), DAY, DAY, now=datetime(2026, 9, 30, tzinfo=VN_TZ))
    assert writes == []


def test_default_reader_routes_through_archive_on_same_connection(monkeypatch, facegate):
    import vera_web_v2_attendance_query_perf as attendance
    conn = object()
    def read(c, start, end):
        assert c is conn and start == end == DAY
        return [{'evidence_source': 'facegate'}]
    monkeypatch.setattr(runtime, 'records', read)
    monkeypatch.setattr(attendance, '_datasets', lambda *_: pytest.fail('Legacy read after cutover'))
    assert attendance._records_v42_fast(conn, DAY, DAY) == [{'evidence_source': 'facegate'}]


def test_live_refresh_never_calls_vendor_and_uses_existing_health(monkeypatch, facegate):
    import vera_web_v2_timesoft_live_refresh as live
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(live.ts.vpg, 'get_engine', lambda: SimpleNamespace(connect=Connection))
    monkeypatch.setattr(source, 'health', lambda _: {'cache_fresh': False, 'source': 'facegate'})
    monkeypatch.setattr(live, '_credentials_ready', lambda: pytest.fail('TimeSoft credentials read'))
    assert live.refresh_today(force=True)['ok'] is False


def test_atomic_policy_file_and_preserved_active_date(tmp_path, facegate):
    from vera_facegate_cutover import atomic_write
    policy = source.configuration()
    atomic_write(facegate, policy)
    assert source.configuration() == policy
    assert facegate.stat().st_mode & 0o777 == 0o644
    assert not list(tmp_path.glob('.attendance-source-*'))


@pytest.mark.parametrize('available', [True, False])
def test_background_keeps_outbox_without_any_timesoft_calls(monkeypatch, facegate, available):
    import timesoft_sync_job as ts
    import vera_web_v2_hr_enhancements as hr
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args, **kwargs): return SimpleNamespace(scalar=lambda: True)
        def commit(self): pass
        def close(self): pass
    engine = SimpleNamespace(connect=Connection, begin=Connection)
    monkeypatch.setattr(ts.vpg, 'is_enabled', lambda: True)
    monkeypatch.setattr(ts.vpg, 'get_engine', lambda: engine)
    monkeypatch.setattr(ts, '_log', lambda *_: None)
    monkeypatch.setattr(ts, 'load_employee_name_map', lambda: {})
    def forbidden(*args, **kwargs): pytest.fail('TimeSoft network or invoice backfill after cutover')
    for name in ('create_authenticated_session', 'fetch_summary', 'fetch_checkin', 'backfill_missing_payroll_snapshots'):
        monkeypatch.setattr(ts, name, forbidden)
    def frames(*_):
        if not available: raise fg.EvidenceError('stale_facegate_source')
        return []
    monkeypatch.setattr(runtime, 'worker_frames', frames)
    monkeypatch.setattr(hr, 'sync_attendance_records', lambda *_: {})
    monkeypatch.setattr(ts.auto_check, 'load_config', lambda *_: {'status': ts.AUTO_PENALTY_PAUSED})
    monkeypatch.setattr(ts.auto_check, 'revoke_grace_period_penalties', lambda *_: 0)
    monkeypatch.setattr(ts.auto_check, 'start_run', lambda *_: 1)
    monkeypatch.setattr(ts.auto_check, 'finish_run', lambda *_, **__: None)
    calls = []
    monkeypatch.setattr(ts.penalty_notifications, 'notify_pending', lambda e: calls.append('outbox') or {})
    monkeypatch.setattr(ts, 'write_status', lambda status, *a, **k: calls.append(status))
    assert ts.run_sync() == (0 if available else 1)
    assert calls == ['outbox', 'success' if available else 'error']


def test_payroll_finalization_rechecks_server_evidence_not_client_flags(monkeypatch, facegate):
    import vera_web_v2_department_payroll as payroll
    from fastapi import HTTPException
    monkeypatch.setattr(payroll.attendance, '_records', lambda *_: [{**record(), 'attendance_pending': True}])
    with pytest.raises(HTTPException) as error:
        payroll._require_complete_attendance(object(), '2026-09', [{'employee_username': 'Employee'}], str)
    assert error.value.status_code == 409

"""Popup decisions use committed FaceGate evidence, including cutoff races."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

import vera_attendance_source as source
import vera_facegate_attendance as fg
import vera_facegate_runtime as runtime
import vera_missing_checkin_notifications as alerts
from vera_facegate_control_log import VN_TZ

DAY = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 15, 0, 10, tzinfo=VN_TZ)
USER = 'Test Worker'


def evidence(*, scan=None, synced=NOW):
    rows = [] if scan is None else [{'EmployeeName': USER, 'WorkDateStr': '08/10/2026',
                                    'MachineTimeCheckInStr': f'08/10/2026 {scan}'}]
    return {'index': {1: {'username': USER}}, 'issues': [], 'rows': rows,
            'events': [] if scan is None else [{'occurred_at': f'2026-10-08T{scan}+07:00'}],
            'syncs': [{'work_date': DAY.isoformat(), 'last_observed_count': len(rows),
                       'last_synced_at': synced.isoformat()}]}


class Connection:
    def __init__(self, leave='Đi trễ CÓ phép'):
        self.leave = leave
        self.reads = []

    def execute(self, sql, params):
        self.reads.append(str(sql))
        assert 'FROM leave_records' in str(sql), 'must not read attendance cache or write'
        rows = [{'employee_name': USER, 'leave_reason': self.leave}] if self.leave else []
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))


@pytest.fixture
def popup(monkeypatch):
    state = SimpleNamespace(data=evidence(), conn=Connection(), projections=0,
                            schedules=[dict(employee_username=USER, employee_name=USER,
                                            employee_role='nhanvien', shift_code='Ca 1', start_time='10:00')])
    def projection(conn, start, end):
        assert conn is state.conn and start == end == DAY
        state.projections += 1
        return state.data
    monkeypatch.setattr(source, 'source_for', lambda day: 'facegate')
    monkeypatch.setattr(fg, 'project_evidence', projection)
    monkeypatch.setattr(alerts, '_staff_scheduled_rows', lambda *args: state.schedules)
    monkeypatch.setattr(alerts, '_scheduled_rows', lambda *args: [])
    def read(now=NOW, role='admin', username='Admin'):
        return alerts.current_missing_checkins(state.conn, SimpleNamespace(role=role, employee_username=username),
                                              now, include_expiry=True)
    state.read = read
    return state


def test_latest_archived_scan_clears_popup_without_cache_publication(popup):
    assert len(popup.read()) == 1
    popup.data = evidence(scan='14:59:40')
    assert popup.read() == []
    assert popup.projections == 2  # One projection for identity and punches per feed.
    assert len(popup.conn.reads) == 2


@pytest.mark.parametrize('hour,shift', [(15, 'Ca 1'), (17, 'Ca 2')])
def test_registered_late_waits_for_post_cutoff_sync(popup, hour, shift):
    now = NOW.replace(hour=hour)
    popup.schedules[0]['shift_code'] = shift
    popup.data = evidence(synced=now.replace(minute=0, second=0)-timedelta(seconds=1))
    assert popup.read(now) == []
    popup.data = evidence(synced=now)
    rows = popup.read(now)
    assert len(rows) == 1 and f'{hour}:00' in rows[0]['body']
    assert rows[0]['expires_at'] == (now+timedelta(minutes=5)).isoformat()


def test_ordinary_shift_also_waits_for_fresh_evidence_past_grace(popup):
    popup.conn.leave = ''
    now = NOW.replace(hour=10, minute=15, second=1)
    popup.data = evidence(synced=now-timedelta(seconds=2))
    assert popup.read(now) == []
    popup.data = evidence(synced=now)
    assert len(popup.read(now)) == 1
    assert popup.read(now.replace(second=0)) == []


@pytest.mark.parametrize('condition', ['stale', 'future', 'naive', 'bad_time', 'incomplete', 'unmapped', 'ambiguous', 'suspended'])
def test_unreliable_evidence_does_not_create_absence_claim(popup, monkeypatch, condition):
    if condition == 'stale': popup.data = evidence(synced=NOW-timedelta(minutes=5, seconds=1))
    if condition == 'future': popup.data = evidence(synced=NOW+timedelta(seconds=1))
    if condition == 'naive': popup.data['syncs'][0]['last_synced_at'] = NOW.replace(tzinfo=None).isoformat()
    if condition == 'bad_time': popup.data['syncs'][0]['last_synced_at'] = 'invalid'
    if condition == 'incomplete': popup.data['syncs'][0]['last_observed_count'] = 1
    if condition == 'unmapped': popup.data['index'] = {}
    if condition == 'ambiguous': popup.data['issues'] = [{'reason': 'unmapped_reference'}]
    if condition == 'suspended': monkeypatch.setattr(runtime.participation, 'suspended', lambda *args: True)
    assert popup.read() == []


def test_scope_and_leave_rules_still_filter_the_authoritative_snapshot(popup):
    assert popup.read(role='nhanvien', username='Another') == []
    assert len(popup.read(role='nhanvien', username=USER)) == 1
    assert popup.read(role='giamdoc', username=USER) == []
    popup.schedules[0]['employee_role'] = 'locker'
    assert popup.read(role='letan') == []
    assert len(popup.read(role='admin')) == 1
    popup.conn.leave = 'Nghỉ CÓ phép'
    assert popup.read() == []


@pytest.mark.parametrize('clock', ['00:30:00', '23:30:00', '16:00:00'])
def test_midnight_exit_or_future_scan_does_not_hide_current_absence(popup, clock):
    popup.data = evidence(scan=clock)
    assert len(popup.read()) == 1


def test_snapshot_does_not_mutate_archived_data(popup):
    before = deepcopy(popup.data)
    popup.read()
    assert popup.data == before

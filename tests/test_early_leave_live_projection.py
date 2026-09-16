from copy import deepcopy

import pytest

import vera_web_v2_live_tour as live
from vera_web_v2_live_tour_attendance import sync_breaks
from vera_web_v2_live_tour_daily import sync_daily
from test_live_tour_attendance_breaktime import NOW, board, record


def project(state, attendance, reason='Về sớm không phép'):
    sync_breaks(state, attendance, NOW)
    return sync_daily(state, [{'username': 'An', 'full_name': 'Nguyễn An'}],
                      [{'employee_name': 'An', 'leave_reason': reason}] if reason else [],
                      automatic=True, today=NOW.date().isoformat())


@pytest.mark.parametrize('reason', ['Về sớm CÓ phép', 'Về sớm không phép',
                                   'Về sớm CUỐI TUẦN KHÔNG phép', 'Về sớm phát sinh'])
def test_early_leave_without_return_clears_shift_and_keeps_service(reason):
    state = board()
    worker = state['employees'][0]
    worker.update(shift='Ca 1', assigned_shift='Ca 1', service='Body', room='1.1',
                  status='Đang thực hiện', started_at=NOW.isoformat())
    original = deepcopy(worker)
    project(state, [record()], reason)
    assert worker['work_status'] == 'Nghỉ phép'
    assert worker['shift'] == ''
    assert live._employee_record(worker, NOW)['Vào ca'] == ''
    for field in ('service', 'room', 'status', 'started_at', 'sort_index'):
        assert worker[field] == original[field]
    saved = deepcopy(state)
    project(state, [record()], reason)
    assert state == saved


@pytest.mark.parametrize('attendance', [[], [record(break_in='15:59:00')],
                                       [record(date='11/09/2026')]])
def test_registration_alone_or_confirmed_return_does_not_mark_absent(attendance):
    state = board()
    project(state, attendance)
    assert state['employees'][0]['work_status'] == 'Đi làm'


def test_later_return_or_removed_leave_restores_daily_shift():
    state = board()
    worker = state['employees'][0]
    worker.update(shift='Ca 1', assigned_shift='Ca 1')
    project(state, [record()])
    project(state, [record(break_in='15:59:00')])
    assert worker['work_status'] == 'Đi làm' and worker['shift'] == 'Ca 1'
    # A stale incomplete attendance cache cannot reverse the confirmed return.
    project(state, [record()])
    assert worker['work_status'] == 'Đi làm'
    state = board()
    project(state, [record()])
    project(state, [record()], reason='')
    assert state['employees'][0]['work_status'] == 'Đi làm'


def test_final_checkout_and_manual_working_status_do_not_mask_early_leave():
    state = board()
    worker = state['employees'][0]
    worker['manual_work_status_date'] = NOW.date().isoformat()
    project(state, [record(break_out='', break_return_deadline_iso='',
                           break_final_early_checkout=True, check_out='15:30:00')])
    assert worker['work_status'] == 'Nghỉ phép' and worker['shift'] == ''
    assert worker['break_started_at'] == ''


def test_route_uses_fresh_break_before_daily_projection_and_persists_once(monkeypatch):
    from datetime import datetime
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from test_live_tour_backend import RouteIdentity
    from test_live_tour_server_only import SettingsDatabase

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(live, 'datetime', Clock)
    db = SettingsDatabase(board())
    db.leaves = [{'employee_name': 'An', 'leave_reason': 'Về sớm không phép'}]
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda: db,
        current_identity=lambda: RouteIdentity(), require_feature=lambda *_: None,
        feature_allowed=lambda *_: True, identity_type=RouteIdentity,
        attendance_reader=lambda conn, *_: [record()])
    client = TestClient(app)
    with db.begin() as conn:
        live._read_state(conn, NOW, for_update=True, attendance_records=[record()])
    first = client.get('/v2/live-tour')
    assert first.status_code == 200
    assert first.json()['records'][0]['Đi làm'] == 'Nghỉ phép'
    assert first.json()['records'][0]['Vào ca'] == ''
    assert db.stored['employees'][0]['work_status'] == 'Nghỉ phép'
    revision = first.json()['revision']
    assert client.get('/v2/live-tour').json()['revision'] == revision

from copy import deepcopy
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import vera_web_v2_live_tour as live
from test_live_tour_backend import RouteEngine, RouteIdentity, employee, state_with

class Identity(RouteIdentity):
    role: str

@pytest.mark.parametrize('action', ['booking', 'multi_booking'])
@pytest.mark.parametrize('role,granted,stamp,expected', [
    ('admin', False, '2026-10-08T17:00:00+00:00', 200),
    ('quanly', True, '2026-10-08T18:59:59+00:00', 200),
    ('letan', True, '2026-10-08T18:00:00+00:00', 200),
    ('admin', True, '2026-10-08T19:00:00+00:00', 409),
    ('letan', True, '2026-10-08T16:59:59+00:00', 409),
    ('quanly', False, '2026-10-08T18:00:00+00:00', 409),
    ('letan', False, '2026-10-08T18:00:00+00:00', 409),
    ('nhanvien', True, '2026-10-08T18:00:00+00:00', 409),
    ('locker', True, '2026-10-08T18:00:00+00:00', 409),
])
def test_booking_exception_uses_role_grant_and_server_clock(monkeypatch, action, role, granted, stamp, expected):
    fixed = datetime.fromisoformat(stamp)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return fixed.astimezone(tz)
    monkeypatch.setattr(live, 'datetime', Clock)
    worker = employee('e1', 'An')
    worker.update(work_status='Nghỉ phép', shift='', shift_checkin_date='2026-10-08', assigned_shift='')
    state = state_with(worker)
    monkeypatch.setattr(live, '_read_state', lambda *a, **kw: (deepcopy(state), 1))
    written = []
    monkeypatch.setattr(live, '_write_state', lambda conn, value, revision, actor: written.append(deepcopy(value)) or 2)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine,
        current_identity=lambda: Identity(role=role), require_feature=lambda *a: None,
        feature_allowed=lambda conn, ident, key: granted if key == 'live_tour_booking_outside_shift' else True,
        identity_type=Identity)
    row = dict(employee_id='e1', room='1.1', service='Body 90', _booking_outside_shift=True)
    payload = dict(row) if action == 'booking' else {'bookings': [row], '_booking_outside_shift': True}
    payload['now'] = '2026-10-09T01:00:00+07:00'
    response = TestClient(app).post('/v2/live-tour/action', json={
        'action': action, 'payload': payload, 'expected_revision': 1, 'idempotency_key': 'overnight-booking-test'})
    assert response.status_code == expected, response.text
    assert bool(written) == (expected == 200)
    if written:
        saved = written[-1]['employees'][0]
        assert saved['status'] == 'Đang chờ'
        for key in ['shift', 'work_status', 'shift_checkin_date', 'assigned_shift']:
            assert saved[key] == worker[key]

@pytest.mark.parametrize('overrides', [
    {'break_started_at': '2026-10-09T00:10:00+07:00'},
    {'roster_eligible': False}, {'service': 'Body 90', 'status': 'CHO THANH TOÁN'},
])
def test_exception_preserves_other_booking_guards(overrides):
    worker = employee('e1', 'An', shift='')
    worker.update(work_status='Nghỉ phép', **overrides)
    with pytest.raises(live.HTTPException):
        live._booking(state_with(worker), {'employee_id': 'e1', 'room': '1.1', 'service': 'Body 90'},
                      datetime.fromisoformat('2026-10-09T01:00:00+07:00'), outside_shift=True)

def test_exception_preserves_collision_and_multi_booking_atomicity():
    workers = [employee('e1', 'An', shift=''), employee('e2', 'Binh', shift='')]
    state = live._empty_state(datetime.fromisoformat('2026-10-09T01:00:00+07:00'))
    state['employees'] = workers
    before = deepcopy(state)
    with pytest.raises(live.HTTPException):
        live._apply_action(state, 'multi_booking', {'_booking_outside_shift': True, 'bookings': [
            {'employee_id': w['id'], 'room': '1.1', 'service': 'Body 90'} for w in workers]}, 'admin',
            datetime.fromisoformat('2026-10-09T01:00:00+07:00'))
    assert state == before

def test_permission_is_explicit_and_separate_from_start():
    import vera_web_v2_permissions as permissions
    from vera_web_v2_live_tour_permissions import LEGACY_FEATURE_INHERITANCE
    key = 'live_tour_booking_outside_shift'
    assert key in permissions.FEATURES
    assert key in next(p for p in permissions.PERMISSION_PAGE_LAYOUT if p['id'] == 'live-tour')['features']
    assert {'live_tour_booking', 'live_tour_view'} <= permissions.permission_closure({key})
    assert 'live_tour_operate' not in permissions.permission_closure({key})
    assert key not in LEGACY_FEATURE_INHERITANCE
    for role, features in permissions.DEFAULT_ROLE_FEATURES.items():
        assert (key in features) == (role == 'admin')

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import RouteEngine, RouteIdentity, employee, state_with


class Identity(RouteIdentity):
    role: str


@pytest.mark.parametrize('role,expected', [('admin', 200), ('letan', 409), ('quanly', 409)])
@pytest.mark.parametrize('action', ['start', 'start_room'])
def test_only_admin_can_start_leave_employee_without_shift(monkeypatch, role, expected, action):
    state = state_with(employee('e1', 'An'))
    state['employees'][0].update(work_status='Nghỉ phép', shift='', status='Đang chờ',
                                 room='1.1', service='Body 90', duration=90)
    monkeypatch.setattr(live, '_read_state', lambda *args, **kwargs: (deepcopy(state), 1))
    written = []
    monkeypatch.setattr(live, '_write_state', lambda conn, value, revision, actor: written.append(deepcopy(value)) or 2)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine,
        current_identity=lambda: Identity(role=role), require_feature=lambda *args: None,
        feature_allowed=lambda conn, ident, feature: feature != "live_tour_start_outside_shift", identity_type=Identity)
    payload = {'_admin_start': True, **({'employee_id': 'e1'} if action == 'start' else {'room': '1'})}
    response = TestClient(app).post('/v2/live-tour/action', json={
        'action': action, 'payload': payload, 'expected_revision': 1, 'idempotency_key': f'{role}-{action}'})
    assert response.status_code == expected, response.text
    if expected == 200:
        worker = written[-1]['employees'][0]
        assert worker['status'] == 'Đang thực hiện'
        assert worker['tour_count'] == 1
        assert worker['shift'] == '' and worker['work_status'] == 'Nghỉ phép'
    else:
        assert not written


@pytest.mark.parametrize('action', ['start', 'start_room'])
@pytest.mark.parametrize('role,granted,stamp,expected', [
    ('letan', True, '2026-09-22T17:00:00+00:00', 200),  # next day 00:00 VN
    ('quanly', True, '2026-09-22T18:59:59+00:00', 200),
    ('locker', True, '2026-09-22T19:00:00+00:00', 409),
    ('letan', True, '2026-09-22T16:59:59+00:00', 409),
    ('letan', False, '2026-09-22T18:00:00+00:00', 409),
    ('admin', False, '2026-09-22T10:00:00+00:00', 200),
])
def test_delegated_start_window_is_enforced_at_api(monkeypatch, action, role, granted, stamp, expected):
    from datetime import datetime
    fixed = datetime.fromisoformat(stamp)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz)
    monkeypatch.setattr(live, 'datetime', Clock)
    state = state_with(employee('e1', 'An'))
    state['employees'][0].update(work_status='Nghỉ phép', shift='', status='Đang chờ',
                                 room='1.1', service='Body 90', duration=90)
    monkeypatch.setattr(live, '_read_state', lambda *args, **kwargs: (deepcopy(state), 1))
    written = []
    monkeypatch.setattr(live, '_write_state', lambda conn, value, revision, actor: written.append(deepcopy(value)) or 2)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine,
        current_identity=lambda: Identity(role=role), require_feature=lambda *args: None,
        feature_allowed=lambda conn, ident, feature: granted if feature == 'live_tour_start_outside_shift' else True,
        identity_type=Identity)
    # Forged internal flags/time must never confer an exception.
    payload = {'_admin_start': True, 'now': '2026-09-23T01:00:00+07:00',
               **({'employee_id': 'e1'} if action == 'start' else {'room': '1'})}
    response = TestClient(app).post('/v2/live-tour/action', json={
        'action': action, 'payload': payload, 'expected_revision': 1, 'idempotency_key': f'delegated-{action}'})
    assert response.status_code == expected, response.text
    assert bool(written) == (expected == 200)
    if written:
        assert written[-1]['employees'][0]['work_status'] == 'Nghỉ phép'
        assert written[-1]['employees'][0]['shift'] == ''


def test_delegated_start_does_not_skip_break_or_booking_checks():
    from datetime import datetime
    now = datetime.fromisoformat('2026-09-23T01:00:00+07:00')
    for overrides, expected in [({'break_started_at': now.isoformat()}, 409),
                                ({'service': ''}, 400), ({'status': 'Đang thực hiện'}, 409)]:
        worker = employee('e1', 'An')
        worker.update(work_status='Nghỉ phép', shift='', status='Đang chờ', room='1.1', service='Body 90', duration=90)
        worker.update(overrides)
        with pytest.raises(live.HTTPException) as error:
            live._start_employee(state_with(worker), worker, now, admin_start=True)
        assert error.value.status_code == expected


def test_new_grant_is_explicit_and_in_permission_ui():
    import vera_web_v2_permissions as permissions
    from vera_web_v2_live_tour_permissions import LEGACY_FEATURE_INHERITANCE
    key = 'live_tour_start_outside_shift'
    assert key in permissions.FEATURES
    assert key in next(page for page in permissions.PERMISSION_PAGE_LAYOUT if page['id'] == 'live-tour')['features']
    assert {'live_tour_view', 'live_tour_operate'} <= permissions.permission_closure({key})
    assert key not in LEGACY_FEATURE_INHERITANCE
    for role, features in permissions.DEFAULT_ROLE_FEATURES.items():
        assert (key in features) == (role == 'admin')

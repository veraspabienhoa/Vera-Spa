from datetime import timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteEngine, RouteIdentity, employee, state_with


def test_personal_tip_projection_is_account_scoped_and_never_exposes_service_money():
    username = "leader.an"
    own_id = live._stable_id("employee", username)
    state = state_with()
    state["reports"] = [
        {"id": "r1", "invoice_id": "i1", "employee_id": own_id, "employee_name": username,
         "bill_no": "HD-1", "service": "Body 90", "room": "1.1", "tip": 70_000,
         "subtotal": 900_000, "total": 970_000, "effective_at": NOW.isoformat()},
        {"id": "r2", "invoice_id": "i2", "employee_id": "other", "employee_name": "other",
         "bill_no": "HD-2", "service": "Foot", "tip": 900_000, "total": 1_000_000},
    ]
    rows = live._personal_tip_rows(state, username)
    assert len(rows) == 1 and rows[0]["tip"] == 70_000
    assert rows[0]["services"] == ["Body 90"] and rows[0]["bill_no"] == "HD-1"
    assert not ({"subtotal", "discount", "total", "price"} & set(rows[0]))


def test_service_performance_reports_early_late_and_steam_time_from_preserved_timestamps():
    worker = employee("e1", "An")
    worker.update({
        "service": "Body 90", "room": "1.1", "request": "YC", "duration": 90,
        "status": "CHO THANH TOÁN", "payment_status": "CHO THANH TOÁN", "service_price": 500_000,
        "booked_at": (NOW - timedelta(minutes=20)).isoformat(),
        "started_at": NOW.isoformat(), "board_yc_started_at": NOW.isoformat(),
        "completed_at": (NOW + timedelta(minutes=75)).isoformat(),
        "completion_delta_minutes": -15, "completion_note": "Sớm 15 phút",
    })
    state = state_with(worker)
    pending = live._apply_action(state, "move_pending", {"employee_id": "e1"}, "admin", NOW + timedelta(minutes=75))["pending"]
    assert pending["entries"][0]["board_yc_started_at"] == NOW.isoformat()
    rows = live._service_performance_rows(state)
    assert len(rows) == 1
    assert rows[0]["actual_duration_minutes"] == 75
    assert rows[0]["completion_delta_minutes"] == -15
    assert rows[0]["completion_result"] == "Sớm 15 phút"
    assert rows[0]["steam_minutes"] == 20


def test_performance_export_uses_exactly_one_start_column_and_employee_export_counts_tour_request():
    requested = employee("e1", "An")
    requested.update({
        "service": "Body 90", "room": "1.1", "request": "YC", "duration": 90,
        "started_at": NOW.isoformat(), "board_started_at": (NOW - timedelta(minutes=1)).isoformat(),
        "board_yc_started_at": NOW.isoformat(), "completed_at": (NOW + timedelta(minutes=90)).isoformat(),
    })
    state = state_with(requested)
    state["reports"] = [
        {"employee_name": "An", "request": "", "total": 120_000, "tip": 20_000, "effective_at": NOW.isoformat()},
        {"employee_name": "An", "request": "YC", "total": 230_000, "tip": 30_000, "effective_at": NOW.isoformat()},
    ]
    _, headers, rows = live._export_rows(state, "performance", NOW)
    normal_index, requested_index = headers.index("TG bắt đầu thực hiện"), headers.index("TG bắt đầu thực hiện YC")
    assert rows[0][normal_index] == ""
    assert rows[0][requested_index] == NOW.isoformat()

    _, employee_headers, employee_rows = live._export_rows(state, "employee", NOW)
    assert employee_headers[1:4] == ["Số dòng theo tour", "Số dòng theo yêu cầu", "Số dòng dịch vụ"]
    assert employee_rows == [["An", 1, 1, 2, 300_000.0, 50_000.0, 350_000.0]]


def test_my_tips_route_allows_employee_roles_only_and_returns_no_invoice_money(monkeypatch):
    username = "leader.an"
    state = state_with()
    state["reports"] = [{
        "id": "r1", "invoice_id": "i1", "employee_id": live._stable_id("employee", username),
        "employee_name": username, "bill_no": "HD-1", "service": "Body 90", "tip": 50_000,
        "total": 800_000, "effective_at": NOW.isoformat(),
    }]
    monkeypatch.setattr(live, "_read_state", lambda *_args, **_kwargs: (state, 7))

    def client_for(role):
        app = FastAPI()
        identity = lambda: SimpleNamespace(employee_username=username, full_name="An", role=role)
        live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=identity,
            require_feature=lambda *_args: None, feature_allowed=lambda *_args: True, identity_type=RouteIdentity)
        return TestClient(app)

    response = client_for("leader").get("/v2/live-tour/my-tips")
    assert response.status_code == 200 and response.json()["rows"][0]["tip"] == 50_000
    assert "total" not in response.json()["rows"][0]
    assert client_for("admin").get("/v2/live-tour/my-tips").status_code == 403


def test_execution_actors_survive_finish_pending_and_invoice():
    from vera_live_tour_early_completion import completion_events
    worker = employee('e1', 'An')
    worker.update(service='Body 90', room='1.1', duration=90, status='Đang chờ', booked_at=NOW.isoformat(), service_price=100)
    state = state_with(worker)
    live._apply_action(state, 'start', {'employee_id': 'e1'}, 'reception.start', NOW)
    result = live._apply_action(state, 'finish_to_pending', {'employee_id': 'e1'}, 'reception.finish', NOW + timedelta(minutes=85))
    row = live._service_performance_rows(state)[0]
    assert (row['started_by'], row['completed_by']) == ('reception.start', 'reception.finish')
    events = completion_events(result)
    assert len(events) == 1 and events[0]['username'] == 'An'
    assert 'Sớm 5 phút' in events[0]['payload']['body']
    assert completion_events({'items': [result, result]}) == events
    pending = result['pending']
    live._apply_action(state, 'checkout', {'pending_id': pending['id'], 'payment_method': 'Tiền mặt'}, 'cashier', NOW + timedelta(minutes=86))
    row = live._service_performance_rows(state)[0]
    assert (row['started_by'], row['completed_by']) == ('reception.start', 'reception.finish')
    assert state['employees'][0].get('started_by') == ''


def test_early_completion_threshold_and_no_history_guessing():
    from vera_live_tour_early_completion import completion_events
    for delta, count in [(-4, 0), (-5, 1), (-30, 1), (0, 0), (3, 0), (None, 0)]:
        result = {'employee': {'id':'e1','name':'An','started_at':NOW.isoformat(), 'completed_at':(NOW+timedelta(minutes=85)).isoformat(), 'completion_delta_minutes':delta}}
        assert len(completion_events(result)) == count


def test_performance_share_matches_export_filters_and_rechecks_admin(monkeypatch):
    import vera_performance_report_export as renderer
    worker = employee('e1','An')
    worker.update(service='Body 90',room='1.1',duration=90,started_at=NOW.isoformat(),completed_at=(NOW+timedelta(minutes=80)).isoformat())
    state = state_with(worker)
    monkeypatch.setattr(live, '_read_state', lambda *a, **kw: (state, 7))
    captured = []
    monkeypatch.setattr(renderer, 'render_performance_report', lambda headers, rows, bounds, fmt: captured.append((rows,bounds,fmt)) or b'pdf')
    app = FastAPI()
    identity = SimpleNamespace(employee_username='admin', full_name='Admin', role='admin')
    live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=lambda:identity,
        require_feature=lambda *args:None, feature_allowed=lambda *args:True, identity_type=RouteIdentity)
    with TestClient(app) as client:
        response = client.get('/v2/live-tour/report-share', params={'kind':'performance','format':'pdf','preset':'all','employee':'An','performance_timing':'early'})
        assert response.status_code == 200, response.text
        assert len(captured[-1][0]) == 1
        assert response.headers['cache-control'] == 'no-store'
        assert client.get('/v2/live-tour/report-share', params={'kind':'performance','format':'png','preset':'all','employee':'Other'}).status_code == 200
        assert captured[-1][0] == []
        identity.role = 'letan'
        assert client.get('/v2/live-tour/report-share', params={'kind':'performance','format':'pdf'}).status_code == 403

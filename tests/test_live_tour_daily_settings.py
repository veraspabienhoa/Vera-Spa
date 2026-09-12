from copy import deepcopy
from datetime import timedelta

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from vera_web_v2_live_tour_daily import sync_daily
from vera_web_v2_live_tour_roster import shift_label
from vera_web_v2_live_tour_payment import profile_bank, selected_bank, settings_update, default_settings
from vera_web_v2_permissions import DEFAULT_ROLE_FEATURES
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_change_employee import running, change


def test_configured_window_is_captured_and_cannot_be_extended_by_replacement():
    state, source, target = running()
    # Existing sessions retain the rule in force when they started.
    state['payment_settings']['employee_change_minutes'] = 20
    with pytest.raises(HTTPException):
        change(state, 601)
    source['employee_change_minutes'] = 20
    change(state, 1100)
    assert target['employee_change_minutes'] == 20
    assert live._employee_change_until(target) == NOW + timedelta(minutes=20)
    with pytest.raises(HTTPException):
        change(state, 1201, source='e2', target='e3')


def test_new_start_uses_configured_window():
    state, source, _ = running()
    source.update(status='Đang chờ', started_at='')
    state['payment_settings']['employee_change_minutes'] = 5
    live._apply_action(state, 'start', {'employee_id': source['id']}, 'admin', NOW)
    assert live._employee_change_until(source) == NOW + timedelta(minutes=5)


def test_restore_exact_manual_position_after_other_reorder():
    state, source, target = running()
    live._apply_action(state, 'admin_reorder', {'employee_id': 'e1', 'direction': 'bottom'}, 'letan', NOW)
    original_index = source['pre_start_tour_position']['board_index']
    change(state)
    assert [row['id'] for row in live._ordered_employees(state['employees'], NOW)].index('e1') == original_index
    assert len({row['sort_index'] for row in state['employees']}) == len(state['employees'])


@pytest.mark.parametrize('value', [0, -1, 181, True, '10', 1.5])
def test_invalid_window_rejected(value):
    with pytest.raises(HTTPException):
        settings_update({**default_settings(), 'employee_change_minutes': value}, live._bounded_money)


@pytest.mark.parametrize('role', ['letan', 'quanly'])
def test_reorder_is_independent_grant_enabled_for_frontdesk(role):
    assert 'live_tour_reorder' in DEFAULT_ROLE_FEATURES[role]
    assert live._required_action_feature('admin_reorder') == 'live_tour_reorder'
    assert live._required_action_feature('reorder') == 'live_tour_reorder'
    response = live._state_response(state_with(employee('e1','An')), 1, NOW, can_reorder=False, can_operate=True)
    assert response['capabilities']['reorder'] is False


def test_daily_leave_is_idempotent_preserves_booking_and_manual_appointment():
    worker = employee('e1', 'An')
    worker.update(username='An', appointment='Khách 15h', service='Body', started_at=live._iso(NOW), status='Đang thực hiện')
    state = state_with(worker)
    directory = [{'username':'An', 'full_name':'Nguyễn An'}]
    leaves = [{'employee_name':'An','leave_reason':'Nghỉ CÓ phép'}]
    sync_daily(state, directory, leaves)
    assert worker['work_status'] == 'Nghỉ phép'
    assert worker['appointment'] == 'Khách 15h · Nghỉ CÓ phép'
    assert worker['service'] == 'Body' and worker['started_at'] == live._iso(NOW)
    assert sync_daily(state, directory, leaves)['updated'] == 0
    sync_daily(state, directory, [])
    assert worker['work_status'] == 'Đi làm' and worker['appointment'] == 'Khách 15h'


def test_partial_day_does_not_become_full_day_absence():
    state = state_with(employee('e1','An'))
    sync_daily(state, [{'username':'An','full_name':'Nguyễn An'}], [{'employee_name':'Nguyễn An','leave_reason':'Đi trễ CÓ phép'}])
    assert state['employees'][0]['work_status'] == 'Đi làm'
    assert state['employees'][0]['appointment'] == 'Đi trễ CÓ phép'


@pytest.mark.parametrize('label,expected', [('Ca 1 (09:00-17:00)','Ca 1'),('Ca 2 - Không đổi','Ca 2'),('Ca 12',''),('', '')])
def test_system_shift_label(label, expected):
    assert shift_label(label) == expected


def test_bank_selection_uses_profile_and_default_without_shared_mutation():
    profile = profile_bank({'bank_name':'Vietcombank', 'bank_account':'0123456789', 'full_name':'Nguyễn An'})
    settings = default_settings()
    settings['bank'] = {'enabled':True,'bank_id':'ACB','account_no':'987654321','account_name':'VERA'}
    assert selected_bank(settings, profile)['account_no'] == '0123456789'
    snapshot = selected_bank(settings, profile, 'default')
    assert snapshot['account_no'] == '987654321'
    settings['bank']['account_no'] = '111111111'
    assert snapshot['account_no'] == '987654321'
    assert profile_bank({'bank_name':'VCB', 'bank_account':'invalid', 'full_name':'An'}) is None
    with pytest.raises(HTTPException): selected_bank(settings, None, 'user')


def route_client(db, role='letan', denied=()):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from test_live_tour_backend import RouteIdentity
    class Identity(RouteIdentity):
        role: str = 'letan'
    ident = Identity(role=role, employee_username='reception')
    def require(conn, identity, feature):
        if feature in denied:
            raise HTTPException(403, 'Permission denied')
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda: db, current_identity=lambda: ident,
        require_feature=require, feature_allowed=lambda conn, ident, feature: feature not in denied,
        identity_type=Identity)
    return TestClient(app)


@pytest.mark.parametrize('role', ['letan', 'quanly'])
@pytest.mark.parametrize('denied', [(), ('live_tour_reorder',)])
def test_reorder_route_honors_grant_and_denial(role, denied):
    from test_live_tour_server_only import SettingsDatabase
    db = SettingsDatabase(state_with(employee('e1','An'), employee('e2','Bình')))
    client = route_client(db, role, denied)
    current = client.get('/v2/live-tour').json()
    response = client.post('/v2/live-tour/action', json={'action':'admin_reorder', 'expected_revision':current['revision'],
        'idempotency_key':'reorder-permission', 'payload':{'employee_id':'e1','direction':'bottom'}})
    assert response.status_code == (403 if denied else 200), response.text
    if not denied:
        assert response.json()['records'][-1]['_id'] == 'e1'


@pytest.mark.parametrize('selection,account', [('auto','0123456789'),('default','987654321')])
def test_checkout_bank_snapshot_is_persisted_and_retry_is_stable(selection, account):
    from test_live_tour_server_only import SettingsDatabase
    from test_live_tour_safety import payable_state
    class BankDatabase(SettingsDatabase):
        def execute(self, statement, params=None):
            if 'SELECT full_name, bank_name, bank_account' in str(statement):
                class Result:
                    def mappings(self): return self
                    def first(self): return {'full_name':'Lễ Tân A', 'bank_name':'VCB', 'bank_account': '0123456789'}
                return Result()
            return super().execute(statement, params)
    state = payable_state()
    state['payment_settings']['bank'] = {'enabled':True, 'bank_id':'ACB', 'account_no':'987654321', 'account_name':'VERA'}
    db = BankDatabase(state)
    client = route_client(db)
    current = client.get('/v2/live-tour').json()
    assert current['payment_settings']['user_bank']['account_no'] == '0123456789'
    body = {'action':'checkout','expected_revision':current['revision'], 'idempotency_key':'bank-snapshot-checkout',
            'payload':{'employee_id':'e1','payment_method':'CHUYỂN KHOẢN','bank_selection':selection}}
    response = client.post('/v2/live-tour/action',json=body)
    assert response.status_code == 200, response.text
    invoice = response.json()['result']['invoice']
    assert invoice['payment_bank']['account_no'] == account
    db.stored['payment_settings']['bank']['account_no'] = '111111111'
    replay = client.post('/v2/live-tour/action', json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()['result']['invoice']['payment_bank']['account_no'] == account
    assert len(db.stored['invoices']) == 1


def test_daily_route_uses_server_leaves_and_rejects_stale_revision():
    from test_live_tour_server_only import SettingsDatabase
    class DailyDatabase(SettingsDatabase):
        def execute(self, statement, params=None):
            if 'FROM leave_records' in str(statement):
                assert params['day'] == live.datetime.now(live.VN_TZ).date()
                class Result:
                    def mappings(self): return self
                    def all(self): return [{'employee_name':'An', 'leave_reason':'Leader nghỉ phép theo chính sách'}]
                return Result()
            return super().execute(statement, params)
    db = DailyDatabase(state_with(employee('e1','An')))
    client = route_client(db, 'quanly')
    current = client.get('/v2/live-tour').json()
    body = {'action':'sync_daily_status', 'expected_revision':current['revision'],'idempotency_key':'daily-status-server',
        'payload':{'leaves':[], 'directory':[]}}
    response = client.post('/v2/live-tour/action',json=body)
    assert response.status_code == 200, response.text
    assert db.stored['employees'][0]['work_status'] == 'Nghỉ phép'
    assert db.stored['employees'][0]['appointment'] == 'Leader nghỉ phép theo chính sách'
    body['idempotency_key'] = 'daily-status-stale'
    assert client.post('/v2/live-tour/action',json=body).status_code == 409


def test_directory_shift_refreshes_board_without_resetting_service():
    from test_live_tour_server_only import SettingsDatabase, app_client
    worker = employee('e1', 'An')
    worker.update(service='Body', status='Đang thực hiện', started_at=live._iso(NOW))
    db = SettingsDatabase(state_with(worker), directory=[{'username':'An','role':'nhanvien','full_name':'An','payload':{},'work_shift':'Ca 2 (14:00-22:00)'}])
    _, client = app_client(db)
    current = client.get('/v2/live-tour').json()
    assert current['records'][0]['Vào ca'] == 'Ca 2'
    assert current['records'][0]['Dịch vụ'] == 'Body'
    db.directory[0]['work_shift'] = 'Ca 1 (10:00-18:00)'
    assert client.get('/v2/live-tour').json()['records'][0]['Vào ca'] == 'Ca 1'

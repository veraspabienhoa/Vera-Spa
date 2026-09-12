"""Employee-directory reconciliation and the room/name booking-to-receipt workflow."""
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_server_only import SettingsDatabase, app_client
from test_live_tour_safety import api_client


def person(username, role='nhanvien', full_name=None, **payload):
    return {'username': username, 'role': role, 'full_name': full_name or f'Họ tên đầy đủ {username}', 'payload': payload}


def act(state, action, payload, now=NOW):
    return live._apply_action(state, action, payload, 'admin', now)


def services(state):
    a = act(state, 'service_upsert', {'name': 'Da & Body', 'duration': 30, 'price': 100001, 'ticket_units': 2})['service']
    b = act(state, 'service_upsert', {'name': 'Massage', 'duration': 60, 'price': 200000, 'ticket_units': 1})['service']
    return a, b


def prepare():
    state = state_with(employee('e1', 'An'), employee('e2', 'Bình'))
    a, b = services(state)
    return state, a, b


def book(state, a, b=None, start=True):
    return act(state, 'booking', {'employee_id': 'e1', 'room': '1.1', 'start_now': start,
        'service_items': [{'service_id': a['id'], 'quantity': 2}] + ([{'service_id': b['id'], 'quantity': 1}] if b else [])})['employee']


def test_first_boot_only_uses_username_and_allowed_roles():
    directory = [person('Linh Đan', 'leader'), person('Thiên Kim'), person('Lễ Tân', 'letan'), person('Locker', 'locker'), person('Admin', 'admin'), person('Quản Lý', 'quanly'), person('Tạp vụ', 'tapvu'), person('Đã xóa', __deleted=True), person('Đã nghỉ', employment_status='Đã nghỉ việc')]
    db = SettingsDatabase(directory=directory)
    _, client = app_client(db)
    data = client.get('/v2/live-tour').json()
    assert {row['Tên nhân viên'] for row in data['records']} == {'Linh Đan', 'Thiên Kim'}
    assert {row['role'] for row in data['employee_directory']} == {'leader', 'nhanvien'}
    assert all(row['name'] == row['username'] and row['work_status'] == 'Nghỉ' for row in db.stored['employees'])
    revision = db.revision
    client.get('/v2/live-tour')
    assert db.revision == revision  # Reads do not write or reorder an unchanged directory.


def test_retired_manual_exclusions_do_not_hide_eligible_directory_employees():
    state = state_with(employee('e1', 'An'))
    state['roster_excluded_usernames'] = ['Bình']
    db = SettingsDatabase(state, directory=[person('An'), person('Bình'), person('Lễ Tân', 'letan')])
    _, client = app_client(db)
    data = client.get('/v2/live-tour').json()
    assert {row['Tên nhân viên'] for row in data['records']} == {'An', 'Bình'}
    assert next(row for row in data['records'] if row['Tên nhân viên'] == 'An')['_id'] == 'e1'
    assert 'roster_excluded_usernames' not in db.stored


def test_existing_names_migrate_without_losing_assignments_or_history():
    state, a, b = prepare()
    book(state, a, b)
    state['employees'][0].update(username='An', name='Nguyễn Văn An', vip=True, hidden=True, sort_index=4)
    state['employees'][1].update(username='Lễ Tân', name='Trần Thị Tân', service='Massage', room='2.1', status='Đang thực hiện')
    state['invoices'] = [{'id': 'paid', 'entries': [{'employee_id': 'e1', 'employee_name': 'Nguyễn Văn An'}], 'total': 100000}]
    before = deepcopy(state)
    db = SettingsDatabase(state, directory=[person('An', full_name='Nguyễn Văn An'), person('Lễ Tân', 'letan', full_name='Trần Thị Tân')])
    _, client = app_client(db)
    data = client.get('/v2/live-tour?include_hidden=true').json()
    assert [row['Tên nhân viên'] for row in data['records']] == ['An']
    actual = db.stored['employees'][0]
    for key in ['id', 'service', 'service_items', 'started_at', 'room', 'tour_count', 'vip', 'hidden', 'sort_index']:
        assert actual[key] == (False if key == 'hidden' else before['employees'][0][key])
    assert data['retained_assignments'][0]['name'] == 'Lễ Tân'
    assert '2.1' not in data['available_beds']
    assert db.stored['invoices'] == before['invoices']


def test_legacy_unambiguous_full_name_matches_but_duplicate_full_names_do_not():
    state = state_with(employee('e1', 'Nguyễn Văn An'), employee('e2', 'Trần Văn Nam'))
    db = SettingsDatabase(state, directory=[person('An', full_name='Nguyễn Văn An'), person('Nam 1', full_name='Trần Văn Nam'), person('Nam 2', full_name='Trần Văn Nam')])
    _, client = app_client(db)
    client.get('/v2/live-tour')
    assert db.stored['employees'][0]['id'] == 'e1' and db.stored['employees'][0]['username'] == 'An'
    assert db.stored['employees'][1]['roster_eligible'] is False
    assert len([row for row in db.stored['employees'] if row['roster_eligible']]) == 3


def test_role_change_refreshes_existing_state_and_directory_failure_is_atomic():
    db = SettingsDatabase(directory=[person('An')])
    _, client = app_client(db)
    first = client.get('/v2/live-tour').json()
    db.directory[0]['role'] = 'locker'
    second = client.get('/v2/live-tour').json()
    assert second['records'] == [] and second['revision'] > first['revision']
    before = deepcopy(db.stored), db.revision
    db.fail_employee_read = True
    assert client.get('/v2/live-tour').status_code == 500
    assert (db.stored, db.revision) == before
    db.fail_employee_read = False
    db.directory[0]['role'] = 'leader'
    assert client.get('/v2/live-tour').json()['records'][0]['Tên nhân viên'] == 'An'





def test_multiple_services_use_catalog_prices_quantities_and_release_employee_on_finish():
    state, a, b = prepare()
    worker = book(state, a, b)
    assert worker['service_price'] == 400002 and worker['duration'] == 120
    assert worker['tour_count'] == 1 and worker['status'] == 'Đang thực hiện'
    snapshot = deepcopy(worker['service_items'])
    pending = act(state, 'finish_to_pending', {'employee_id': 'e1'})['pending']
    assert state['employees'][0]['service'] == '' and state['employees'][0]['tour_count'] == 1
    assert pending['entries'][0]['service_items'] == snapshot
    assert live._room_available(state, '1.1')
    # The same employee can take a new booking before the previous customer pays.
    book(state, a, start=False)
    invoice = act(state, 'checkout', {'pending_id': pending['id'], 'payment_method': 'TIỀN MẶT', 'discount_mode': 'percent', 'discount_percent': 12.5, 'tip_card_ids': ['tip-50000', 'tip-100000']})['invoice']
    assert invoice['subtotal'] == 400002 and invoice['discount'] == 50000 and invoice['tip'] == 150000
    assert invoice['total'] == 500002 and len(invoice['tip_cards']) == 2
    assert state['employees'][0]['status'] == 'Đang chờ'
    assert not state['pending']
    assert state['reports'][-1]['total'] == invoice['total']


def test_service_edit_preserves_start_and_tour_count_and_checks_room_collisions():
    state, a, b = prepare()
    worker = book(state, a)
    started, count = worker['started_at'], worker['tour_count']
    act(state, 'update_booking', {'employee_id': 'e1', 'room': '1.1', 'service_items': [{'service_id': b['id'], 'quantity': 1}]})
    assert worker['service'] == 'Massage' and worker['service_price'] == 200000 and worker['duration'] == 60
    assert (worker['started_at'], worker['tour_count']) == (started, count)
    act(state, 'booking', {'employee_id': 'e2', 'room': '2.1', 'service': b['name']})
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'update_booking', {'employee_id': 'e1', 'room': '2.1', 'service_items': [{'service_id': b['id'], 'quantity': 1}]})
    assert state == before


@pytest.mark.parametrize('items', [[], 'bad', [{'service_id': []}], [{'service_id': 'missing'}], [{'service_id': 's', 'quantity': True}], [{'service_id': 's', 'quantity': -1}]])
def test_invalid_service_selection_is_rejected_without_assigning(items):
    state, a, _ = prepare()
    items = [{**row, 'service_id': a['id'] if row.get('service_id') == 's' else row.get('service_id')} for row in items] if isinstance(items, list) else items
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'booking', {'employee_id': 'e1', 'room': '1.1', 'service_items': items})
    assert state == before


def test_multiple_services_respect_private_room_lock_even_with_ampersand_name():
    state, a, b = prepare()
    a['private'] = True
    book(state, a, b)
    with pytest.raises(HTTPException):
        act(state, 'booking', {'employee_id': 'e2', 'room': '1.2', 'service': b['name']})
    with pytest.raises(HTTPException):
        act(state, 'service_upsert', {**a, 'name': 'Changed'})


def test_composed_combo_debits_structured_quantities_without_splitting_names():
    state, a, b = prepare()
    combo = act(state, 'combo_upsert', {'name': 'Gói A', 'price': 500000, 'components': [{'service_id': a['id'], 'quantity': 3}, {'service_id': b['id'], 'quantity': 2}]})['combo']
    purchase = act(state, 'combo_purchase', {'combo_id': combo['id'], 'customer_name': 'Khách A'})['purchase']
    book(state, a, b)
    pending = act(state, 'finish_to_pending', {'employee_id': 'e1'})['pending']
    invoice = act(state, 'checkout', {'pending_id': pending['id'], 'customer_id': state['customers'][0]['id'], 'payment_method': 'COMBO', 'combo_purchase_id': purchase['id']})['invoice']
    assert invoice['combo_units'] == 3 and invoice['total'] == 0
    assert [row['remaining'] for row in state['customers'][0]['combo_purchases'][0]['component_balances']] == [1, 1]
    assert state['reports'][-1]['combo_units'] == 3


def test_finish_saves_service_edits_atomically_and_preserves_counted_tour():
    state, a, b = prepare()
    book(state, a)
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'finish_to_pending', {'employee_id': 'e1', 'service_items': [{'service_id': 'missing', 'quantity': 1}]})
    assert state == before
    pending = act(state, 'finish_to_pending', {'employee_id': 'e1', 'room': '1.1', 'service_items': [{'service_id': b['id'], 'quantity': 3}]})['pending']
    assert pending['entries'][0]['price'] == 600000
    assert pending['entries'][0]['service_items'][0]['quantity'] == 3
    assert pending['entries'][0]['service_items'][0]['service_id'] == b['id']
    assert state['employees'][0]['service'] == '' and state['employees'][0]['tour_count'] == 1


def test_finish_retry_and_batch_failure_never_duplicate_pending_or_clear_new_work(monkeypatch):
    state, a, b = prepare()
    book(state, a, b)
    client, shared = api_client(monkeypatch, state)
    body = {'action': 'finish_to_pending', 'payload': {'employee_id': 'e1'}, 'expected_revision': 1, 'idempotency_key': 'finish-request-once'}
    first = client.post('/v2/live-tour/action', json=body)
    assert first.status_code == 200, first.text
    book(shared['state'], a)
    shared['revision'] += 1
    snapshot = deepcopy(shared)
    assert client.post('/v2/live-tour/action', json=body).json()['duplicate'] is True
    assert shared == snapshot and len(shared['state']['pending']) == 1
    assert shared['state']['employees'][0]['service']
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'finish_to_pending', {'employee_ids': ['e1', 'e2']})
    assert state == before


@pytest.mark.parametrize('value', [-1, 101, True, 'nan', 'inf', '10.123'])
def test_invalid_percent_discount_is_atomic(value):
    state, a, _ = prepare()
    book(state, a)
    pending = act(state, 'finish_to_pending', {'employee_id': 'e1'})['pending']
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'checkout', {'pending_id': pending['id'], 'payment_method': 'TIỀN MẶT', 'discount_mode': 'percent', 'discount_percent': value})
    assert state == before


def test_tip_presets_require_admin_and_receipts_keep_original_values(monkeypatch):
    state, a, _ = prepare()
    assert state['payment_settings']['auto_print'] is False
    assert live._required_action_feature('payment_settings_update') == 'live_tour_admin'
    act(state, 'payment_settings_update', {'auto_print': True, 'tip_cards': [{'id': 'tip-custom', 'name': 'TIP 80k', 'amount': 80000}]})
    book(state, a)
    pending = act(state, 'finish_to_pending', {'employee_id': 'e1'})['pending']
    before = deepcopy(state)
    for extra in [{'tip_card_ids': ['missing']}, {'tip_card_ids': ['tip-custom', 'tip-custom']}, {'tip_card_ids': ['tip-custom'], 'tip': 1}]:
        with pytest.raises(HTTPException):
            act(state, 'checkout', {'pending_id': pending['id'], 'payment_method': 'TIỀN MẶT', **extra})
        assert state == before
    invoice = act(state, 'checkout', {'pending_id': pending['id'], 'payment_method': 'TIỀN MẶT', 'tip_card_ids': ['tip-custom']})['invoice']
    act(state, 'payment_settings_update', {'auto_print': False, 'tip_cards': []})
    assert invoice['tip'] == 80000 and invoice['tip_cards'][0]['name'] == 'TIP 80k'
    client, _ = api_client(monkeypatch, state)
    assert client.get('/v2/live-tour').json()['payment_settings'] == {**live._default_payment_settings(), 'tip_cards': []}


def test_browser_helpers_rank_by_standard_start_and_preserve_service_ids():
    uri = (Path(__file__).parents[1] / 'web-v2/src/lib/liveTourBooking.js').as_uri()
    script = '''
import assert from 'node:assert/strict';
const {bookingEmployees, bookingServiceItems, bookingTotal, discountAmount, tourNameKey} = await import(MODULE);
const now = Date.parse('2026-09-09T05:00:00Z');
const worker = {work_status:'Đi làm',shift:'Ca 1',started_at:new Date(now-600000).toISOString(),service:'Massage',duration:60};
const rows = [{...worker,id:'long',name:'Long',started_at:new Date(now-3600000).toISOString()},{...worker,id:'short',name:'Short',duration:11},{...worker,id:'idle',name:'Idle',service:'',started_at:''},{...worker,id:'break',break_started_at:'x'},{...worker,id:'off',work_status:'Nghỉ'},{...worker,id:'other-role',roster_eligible:false}];
assert.deepEqual(bookingEmployees(rows,now).map(row=>row.id),['idle','long','short']);
assert.equal(tourNameKey('  Linh Đan  '),'linh dan');
const catalog=[{id:'s',name:'Da & Body',price:100000}];
assert.deepEqual(bookingServiceItems({service:'Da & Body'},catalog),[{service_id:'s',quantity:1}]);
assert.deepEqual(bookingServiceItems({service_items:[{service_id:'s',quantity:2}]},catalog),[{service_id:'s',quantity:2}]);
assert.equal(bookingTotal([{service_id:'s',quantity:2}],catalog),200000);
assert.equal(discountAmount(400002,'percent',12.5),50000);
assert.equal(discountAmount(400002,'amount',10000),10000);
'''.replace('MODULE', repr(uri))
    result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_outside_roster_is_excluded_from_board_exports_but_keeps_paid_history():
    state = state_with(employee('e1', 'An'), employee('e2', 'Locker'))
    state['employees'][1]['roster_eligible'] = False
    for hidden in (False, True):
        _, headers, rows = live._export_rows(state, 'board', NOW, include_hidden=hidden)
        assert [row[headers.index('Tên nhân viên')] for row in rows] == ['An']


def test_http_permissions_protect_tip_settings_and_customer_booking_edits(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from test_live_tour_backend import RouteIdentity, RouteEngine
    state, a, _ = prepare()
    book(state, a)
    _, shared = api_client(monkeypatch, state)
    grants = {'live_tour_operate', 'live_tour_view'}
    def require(_conn, _identity, feature):
        if feature not in grants:
            raise HTTPException(403, 'Permission denied')
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=RouteEngine, current_identity=lambda: RouteIdentity(),
        require_feature=require, feature_allowed=lambda _conn, _ident, feature: feature in grants, identity_type=RouteIdentity)
    client = TestClient(app)
    def post(action, payload):
        return client.post('/v2/live-tour/action', json={'action': action, 'payload': payload, 'expected_revision': shared['revision'], 'idempotency_key': 'permission-' + action})
    assert post('payment_settings_update', {'auto_print': True, 'tip_cards': []}).status_code == 403
    assert post('update_booking', {'employee_id': 'e1', 'customer_name': 'Private customer', 'room': '1.1', 'service_items': [{'service_id': a['id'], 'quantity': 1}]}).status_code == 403
    assert post('finish_to_pending', {'employee_id': 'e1', 'customer_name': 'Private customer', 'room': '1.1', 'service_items': [{'service_id': a['id'], 'quantity': 1}]}).status_code == 403
    completed = post('finish_to_pending', {'employee_id': 'e1'})
    assert completed.status_code == 200 and shared['state']['employees'][0]['service'] == ''
    assert client.get('/v2/live-tour').json()['pending_payments'] == []
    grants.add('live_tour_admin')
    assert post('payment_settings_update', {'auto_print': True, 'tip_cards': []}).status_code == 200


def test_payment_settings_bank_validation_open_receipt_and_tip_order():
    payload = {'auto_print': True, 'open_receipt': False,
               'bank': {'enabled': True, 'bank_id': '970436', 'account_no': '00123456789', 'account_name': 'VERA SPA'},
               'tip_cards': [{'id': 'high', 'name': '50.000 đ', 'amount': 50000}, {'id': 'low', 'name': '10.000 đ', 'amount': 10000}]}
    result = live._payment_settings_update(payload, live._bounded_money)
    assert result['auto_print'] is False
    assert result['open_receipt'] is False
    assert result['bank']['account_no'] == '00123456789'
    assert [card['amount'] for card in result['tip_cards']] == [10000, 50000]
    for bank in [None, {'enabled': True, 'bank_id': '../x', 'account_no': '123456', 'account_name': 'A'}, {'enabled': 'yes'}]:
        with pytest.raises(HTTPException):
            live._payment_settings_update({**payload, 'bank': bank}, live._bounded_money)


def test_vera_invoice_sequence_continues_after_legacy_live_numbers():
    state = state_with(employee('e1', 'An'))
    state['invoices'] = [{'bill_no': 'LIVE-20260905-0042'}]
    state['bill_counters'] = {}
    assert live._next_bill_no(state, {}, NOW) == 'VERA-20260905-0043'
    assert state['invoices'][0]['bill_no'] == 'LIVE-20260905-0042'


@pytest.mark.parametrize('direction,steps,target', [('up',1,3),('up',3,1),('up',5,0),('down',1,5),('down',3,7),('down',5,8),('bottom',1,8),('top',1,0)])
def test_admin_reorder_moves_across_start_times_and_leave_to_actual_position(direction, steps, target):
    workers = [employee(f'e{i}', f'Worker {i}') for i in range(9)]
    for i, worker in enumerate(workers):
        worker.update(sort_index=i, service='Body', status='Đang thực hiện', started_at=f'2026-09-05T{10+i:02d}:00:00+07:00')
    workers[-1]['work_status'] = 'Nghỉ phép'
    state = state_with(*workers)
    act(state, 'admin_reorder', {'employee_id':'e4','direction':direction,'steps':steps})
    ordered = live._ordered_employees(state['employees'], NOW)
    assert ordered[target]['id'] == 'e4'
    assert all(worker['manual_order'] for worker in ordered)
    assert [row['sort_index'] for row in ordered] == list(range(9))
    restored = deepcopy(state)
    assert [r['id'] for r in live._ordered_employees(restored['employees'], NOW)] == [r['id'] for r in ordered]


def test_admin_direct_stt_and_cancel_waiting_booking_release_reservations():
    state = state_with(employee('e1','An'), employee('e2','Bình'))
    act(state, 'admin_reorder', {'employee_id':'e1','direction':'position','position':2})
    assert live._ordered_employees(state['employees'], NOW)[-1]['id'] == 'e1'
    worker = next(row for row in state['employees'] if row['id']=='e1')
    worker.update(status='Đang chờ', service='Body', room='1.1', combo_purchase_id='combo1', combo_reserved_units=1)
    act(state, 'cancel_booking', {'employee_id':'e1'})
    assert worker['room'] == '' and worker['service'] == ''
    assert 'combo_reserved_units' not in worker
    assert not state['invoices'] and not state['pending']
    worker.update(status='Đang thực hiện', service='Body')
    next(row for row in state['employees'] if row['id']=='e2').update(status='Đang chờ', service='Body', room='1.2')
    before = deepcopy(state)
    with pytest.raises(HTTPException):
        act(state, 'cancel_booking', {'employee_ids':['e2','e1']})
    assert state == before
    assert live._required_action_feature('admin_reorder') == 'live_tour_admin'


def test_admin_reorder_rejects_non_admin_even_with_feature_grants(monkeypatch):
    client, shared = api_client(monkeypatch)
    result = client.post('/v2/live-tour/action', json={'action':'admin_reorder','expected_revision':1,'idempotency_key':'admin-order-test','payload':{'employee_id':'e1','direction':'bottom'}})
    assert result.status_code == 403
    assert shared['revision'] == 1

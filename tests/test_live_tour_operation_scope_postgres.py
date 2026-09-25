"""Partial operational snapshots preserve all omitted history and replay receipts."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee
from test_live_tour_resource_postgres import database
from test_live_tour_payment_scope_postgres import payments, saved


@pytest.mark.parametrize('action,payload,status', [
    ('update_appointment', {'appointment':'Test appointment'}, ''),
    ('set_vip', {}, ''),
    ('booking', {'room':'1.1','service':'Body 90'}, ''),
    ('start', {}, 'Đang chờ'),
    ('complete', {}, 'Đang thực hiện'),
    ('finish_to_pending', {}, 'Đang thực hiện'),
    ('end_break', {}, 'break'),
])
def test_operations_do_not_read_financial_history_or_other_receipts(database, payments, monkeypatch, action, payload, status):
    client, body, _ = payments
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        prepared = deepcopy(before)
        worker = employee('e1', 'Test 1')
        if status and status != 'break':
            worker.update(status=status, service='Body 90', room='1.1', duration=90,
                          service_price=100, booked_at='2026-09-05T12:00:00+07:00',
                          started_at='2026-09-05T13:00:00+07:00')
        if status == 'break':
            worker['break_started_at'] = '2026-09-05T14:00:00+07:00'
            prepared['break_events'] = [{'id':'break-start','event_type':'start','employee_id':'e1',
                                         'started_at':worker['break_started_at']}]
        prepared['employees'][0] = worker
        body['expected_revision'] = store.write(conn, before, prepared, 'fixture')
    original = store.read
    observed = []
    def bounded(conn, collections=None, **kwargs):
        assert collections is not None or kwargs.get('profile') == 'operational'
        result = original(conn, collections, **kwargs)
        assert not result[0]['invoices'] and not result[0]['audit'] and not result[0]['reports']
        assert set(result[0].get('idempotency', {})) <= {body['idempotency_key']}
        observed.append(kwargs.get('profile'))
        return result
    monkeypatch.setattr(store, 'read', bounded)
    body.update(action=action, payload={'employee_id':'e1', **payload}, response_view='board')
    response = client.post('/v2/live-tour/action', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['view'] == 'board' and 'operational' in observed
    replay = client.post('/v2/live-tour/action', json=body)
    assert replay.status_code == 200 and replay.json()['duplicate'], replay.text
    monkeypatch.setattr(store, 'read', original)
    actual, revision = saved(database)
    assert revision == body['expected_revision'] + 1
    for key in ('invoices','reports','combo_usage','invoice_changes'):
        assert actual[key] == prepared[key]
    assert all(actual['idempotency'][k] == v for k,v in prepared['idempotency'].items())
    assert actual['audit'][:-1] == prepared['audit'][1:]
    if action == 'start':
        assert actual['employees'][0]['tour_count'] == 1
    if action == 'end_break':
        assert actual['break_events'][-1]['start_event_id'] == 'break-start'
    if action == 'finish_to_pending':
        assert len(actual['pending']) == 1


@pytest.mark.parametrize('action', ['paid_invoice_update', 'paid_invoice_delete'])
def test_invoice_corrections_keep_other_ledger_rows_and_retry_once(database, payments, monkeypatch, action):
    client, body, _ = payments
    paid = client.post('/v2/live-tour/action', json=body)
    assert paid.status_code == 200, paid.text
    invoice = paid.json()['result']['invoice']
    before, revision = saved(database)
    correction = {'action':action,'payload':{'invoice_id':invoice['id'],'reason':'Test correction'},
                  'expected_revision':revision,'idempotency_key':'adjust-once','response_view':'receipt'}
    if action.endswith('update'):
        correction['payload'].update(tip=22, note='Corrected')
    original = store.read
    def bounded(conn, collections=None, **kwargs):
        assert collections is not None or kwargs.get('profile') == 'adjustment'
        state, version, versions = original(conn, collections, **kwargs)
        assert not state['audit'] and not state['invoice_changes']
        assert set(state.get('idempotency', {})) <= {'adjust-once'}
        return state, version, versions
    monkeypatch.setattr(store, 'read', bounded)
    response = client.post('/v2/live-tour/action', json=correction)
    assert response.status_code == 200, response.text
    assert response.json()['refresh_board'] and 'records' not in response.json()
    replay = client.post('/v2/live-tour/action', json=correction)
    assert replay.status_code == 200 and replay.json()['duplicate'], replay.text
    monkeypatch.setattr(store, 'read', original)
    after, next_revision = saved(database)
    assert next_revision == revision + 1
    assert [x for x in after['invoices'] if x['id'] != invoice['id']] == before['invoices'][:-1]
    assert [x for x in after['reports'] if x['invoice_id'] != invoice['id']] == before['reports'][:-1]
    assert after['invoice_changes'][:-1] == before['invoice_changes']
    assert all(after['idempotency'][k] == v for k,v in before['idempotency'].items())
    assert after['invoice_changes'][-1]['before'] == invoice
    if action.endswith('delete'):
        assert response.json()['result']['voided'] is True
        assert all(x['id'] != invoice['id'] for x in after['invoices'])
    else:
        assert after['invoices'][-1]['tip'] == after['reports'][-1]['tip'] == 22


def test_correction_rollback_and_prior_day_rule_remain_enforced(database, payments, monkeypatch):
    client, body, _ = payments
    paid = client.post('/v2/live-tour/action', json=body).json()
    before, revision = saved(database)
    correction = {'action':'paid_invoice_delete','payload':{'invoice_id':paid['result']['invoice']['id'],'reason':'Test rollback'},
                  'expected_revision':revision,'idempotency_key':'rollback-adjust','response_view':'receipt'}
    original = store.write
    def abort(*args):
        original(*args)
        raise HTTPException(503, 'Injected rollback')
    monkeypatch.setattr(store, 'write', abort)
    assert client.post('/v2/live-tour/action', json=correction).status_code == 503
    assert saved(database) == (before, revision)
    monkeypatch.setattr(store, 'write', original)
    with database.begin() as conn:
        store.lock(conn)
        prepared = deepcopy(before)
        prepared['invoices'][-1]['business_date'] = '2026-09-04'
        correction['expected_revision'] = store.write(conn, before, prepared, 'fixture')
    prior = saved(database)
    response = client.post('/v2/live-tour/action', json=correction)
    assert response.status_code == 403, response.text
    assert saved(database) == prior


def test_projection_updates_roster_without_touching_history_or_receipts(database, payments, monkeypatch):
    before, _ = saved(database)
    original = store.read
    def bounded(conn, collections=None, **kwargs):
        assert kwargs == {'profile':'operational'}
        result = original(conn, collections, **kwargs)
        assert not result[0].get('idempotency') and not result[0]['audit']
        return result
    monkeypatch.setattr(store, 'read', bounded)
    directory = [{'username':'Test 1','role':'nhanvien','work_shift':'Ca 1','full_name':'Test 1',
                  'employment_status':'Đang làm việc','payload':{}}]
    with database.begin() as conn:
        store.lock(conn)
        projected, _ = live._read_state(conn, NOW, for_update=True, attendance_records=[],
                                       directory_records=directory, leave_records=[])
        assert isinstance(projected, store._OperationalSnapshot)
    monkeypatch.setattr(store, 'read', original)
    after, _ = saved(database)
    for key in ('idempotency','invoices','reports','combo_usage','invoice_changes','audit'):
        assert after[key] == before[key]
    assert after['employee_directory']


def test_compact_disjoint_writes_append_history_without_lost_updates(database, payments):
    before, version = saved(database)
    barrier = Barrier(2)
    def edit(identifier):
        with database.begin() as conn:
            payload = {'employee_id':identifier,'appointment':identifier}
            state, _, fresh = store.begin_action(conn, 'update_appointment', payload, version,
                                                'scoped-'+identifier, live._counter_business_date(NOW).isoformat(), compact=True)
            assert fresh
            changed = deepcopy(state)
            result = live._apply_action(changed,'update_appointment',payload,'admin',NOW)
            live._remember_idempotency(changed,'scoped-'+identifier,action='update_appointment',actor='admin',payload_hash=live._canonical_payload_hash('update_appointment',payload),result=result,now=NOW)
            barrier.wait(timeout=5)
            store.write(conn,state,changed,'admin')
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(edit, ['e1','e2']))
    after, revision = saved(database)
    assert revision == version + 2
    assert len(after['audit']) == 8 and len({x['id'] for x in after['audit']}) == 8
    assert all(x['appointment'] == x['id'] for x in after['employees'])
    assert all(after['idempotency'][k] == v for k,v in before['idempotency'].items())
    assert {'scoped-e1','scoped-e2'} <= set(after['idempotency'])


def test_partial_snapshot_rejects_uncertified_writes(database, payments):
    before = saved(database)
    with database.begin() as conn:
        store.lock(conn)
        snapshot, _, _ = store.read(conn, profile='operational')
        changed = deepcopy(snapshot)
        changed['invoices'].append({'id':'forbidden','bill_no':'forbidden'})
        with pytest.raises(RuntimeError, match='certified write set'):
            store.write(conn, snapshot, changed, 'test')
    assert saved(database) == before

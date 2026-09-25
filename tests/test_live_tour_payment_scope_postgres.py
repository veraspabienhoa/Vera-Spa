"""Checkout uses a bounded read set without weakening the financial ledger."""
from copy import deepcopy

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import text

import vera_live_tour_resource_store as store
import vera_live_tour_relational as relational
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, payable_employee
from test_live_tour_resource_postgres import database


@pytest.fixture
def payments(database, monkeypatch):
    class Identity(BaseModel):
        employee_username: str = 'admin'
        full_name: str = 'Test operator'
        role: str = 'admin'
    class FixedDateTime(live.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(live, 'datetime', FixedDateTime)
    monkeypatch.setattr(live, 'MAX_AUDIT', 8)
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        seeded = deepcopy(before)
        seeded['employees'] = [payable_employee('e1', 'Test 1'), payable_employee('e2', 'Test 2', room='2.1')]
        next(row for row in seeded['services'] if row['name'] == 'Body 90')['price'] = 100
        seeded['customers'] = [{'id':'c1','name':'Khách c1','phone':'0901','combo_purchases':[]}]
        seeded['invoices'] = [{'id':f'old-{i}', 'bill_no':f'VERA-20260905-{i+1:04d}',
                               'total':100, 'entries':[{'note':'historical data '*100}]} for i in range(20)]
        seeded['invoice_changes'] = [{'id':'void-history','before':{'id':'void','bill_no':'VOID-USED','entries':[{'note':'private'}]}}]
        seeded['reports'] = [{'id':f'report-{i}','invoice_id':f'old-{i}','total':100} for i in range(20)]
        seeded['audit'] = [{'id':f'audit-{i}','detail':{'note':'unchanged'}} for i in range(8)]
        seeded['idempotency'] = {f'old-key-{i}':{'action':'checkout','status':'completed','result':{'invoice':deepcopy(row)}} for i,row in enumerate(seeded['invoices'])}
        revision = store.write(conn, before, seeded, 'fixture')
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda:database,
        current_identity=lambda:Identity(), require_feature=lambda *args:None,
        feature_allowed=lambda *args:True, identity_type=Identity)
    body = {'action':'checkout','expected_revision':revision,'idempotency_key':'compact-payment-key',
            'response_view':'receipt','payload':{'employee_id':'e1','payment_method':'TIỀN MẶT','tip':11}}
    return TestClient(app), body, seeded


def saved(database):
    with database.connect() as conn:
        return store.read(conn)[:2]


def test_compact_payment_preserves_history_and_receipts_without_full_or_postcommit_reads(database, payments, monkeypatch):
    client, body, seeded = payments
    original = store.read
    reads = []
    def bounded_read(conn, collections=None, *, payment_key=None):
        assert collections is not None or payment_key is not None, 'unexpected full snapshot'
        assert collections != relational.RESOURCE_COLLECTIONS, 'post-commit full board read'
        result = original(conn, collections, payment_key=payment_key)
        if payment_key is not None:
            state = result[0]
            assert isinstance(state, store._PaymentSnapshot)
            assert state['audit'] == state['reports'] == state['backups'] == []
            assert set(state['idempotency']) <= {body['idempotency_key']}
            assert all(set(row) == {'id','bill_no'} for row in state['invoices'])
        reads.append((collections,payment_key))
        return result
    monkeypatch.setattr(store, 'read', bounded_read)
    response = client.post('/v2/live-tour/action', json=body)
    assert response.status_code == 200, response.text
    invoice = response.json()['result']['invoice']
    assert invoice['bill_no'] == 'VERA-20260905-0021'
    assert invoice['total'] == 111 and invoice['tip'] == 11
    assert response.json()['refresh_board'] and 'records' not in response.json()
    assert len(reads) == 2
    monkeypatch.setattr(store, 'read', original)
    state, revision = saved(database)
    assert state['invoices'][:-1] == seeded['invoices']
    assert state['reports'][:-1] == seeded['reports']
    assert state['invoice_changes'] == seeded['invoice_changes']
    assert state['audit'][:-1] == seeded['audit'][1:]
    assert len(state['audit']) == 8 and len(state['reports']) == 21
    assert all(state['idempotency'][key] == value for key,value in seeded['idempotency'].items())
    replay = client.post('/v2/live-tour/action', json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()['duplicate'] is True
    assert replay.json()['result']['invoice'] == invoice
    assert saved(database)[1] == revision
    changed = {**body, 'payload':{**body['payload'],'tip':12}}
    assert client.post('/v2/live-tour/action',json=changed).status_code == 409
    assert saved(database)[1] == revision


@pytest.mark.parametrize('bill_no', ['VERA-20260905-0001', 'VOID-USED'])
def test_manual_number_cannot_reuse_existing_or_voided_invoice(database, payments, bill_no):
    client, body, _ = payments
    before = saved(database)
    body['payload']['bill_no'] = bill_no
    response = client.post('/v2/live-tour/action', json=body)
    assert response.status_code == 409, response.text
    assert saved(database) == before


def test_compact_payment_rollback_is_atomic_and_same_ledger_fails_fast(database, payments, monkeypatch):
    client, body, _ = payments
    before = saved(database)
    with database.begin() as held:
        store.begin_action(held, body['action'], body['payload'], body['expected_revision'],
                           body['idempotency_key'], live._counter_business_date(NOW).isoformat(), compact=True)
        busy = client.post('/v2/live-tour/action',json=body)
        assert busy.status_code == 503
    original = store.write
    def abort_after_write(*args):
        original(*args)
        raise HTTPException(503, 'Injected rollback')
    monkeypatch.setattr(store,'write',abort_after_write)
    assert client.post('/v2/live-tour/action',json=body).status_code == 503
    assert saved(database) == before
    monkeypatch.setattr(store,'write',original)
    assert client.post('/v2/live-tour/action',json=body).status_code == 200
    assert len(saved(database)[0]['invoices']) == len(before[0]['invoices'])+1


def test_replay_reads_current_invoice_and_does_not_revive_voided_receipt(database, payments):
    client, body, _ = payments
    first = client.post('/v2/live-tour/action',json=body)
    assert first.status_code == 200, first.text
    identifier = first.json()['result']['invoice']['id']
    with database.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_invoice SET payload=jsonb_set(payload,'{note}','\"corrected\"') WHERE resource_id=:id"),{'id':identifier})
    replay = client.post('/v2/live-tour/action',json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()['result']['invoice']['note'] == 'corrected'
    with database.begin() as conn:
        conn.execute(text('UPDATE vera_live_tour_invoice SET deleted_at=NOW() WHERE resource_id=:id'),{'id':identifier})
    voided = client.post('/v2/live-tour/action',json=body)
    assert voided.status_code == 200 and voided.json()['duplicate']
    assert voided.json()['result']['invoice'] is None and voided.json()['result']['voided']


def test_quick_backdated_payment_and_report_allocation_use_same_business_rules(database, payments):
    client, body, seeded = payments
    service_id = next(row['id'] for row in seeded['services'] if row['name'] == 'Body 90')
    body['action'] = 'quick_checkout'
    body['payload'] = {'quick_booking':{'employee_id':'e1','service_items':[{'service_id':service_id,'quantity':1}],'room':'1.1',
        'booked_at':'2026-09-04T14:00:00+07:00','correction_reason':'Test prior booking'},
        'payment_method':'TIỀN MẶT','tip':11}
    before, _ = saved(database)
    expected = deepcopy(before)
    # Compare accounting and dates to the existing full-state domain function.
    result = live._apply_action(expected, body['action'], body['payload'], 'admin', NOW)
    response = client.post('/v2/live-tour/action',json=body)
    assert response.status_code == 200, response.text
    actual = response.json()['result']['invoice']
    for key in ('subtotal','discount','tip','total','business_date','effective_at','bill_no','entries'):
        assert actual[key] == result['invoice'][key]
    state, _ = saved(database)
    assert state['employees'] == before['employees']
    assert state['reports'][-1]['total'] == actual['total']
    assert state['reports'][-1]['tip'] == actual['tip']


@pytest.mark.parametrize('remaining', [0, 2])
def test_compact_combo_payment_preserves_balance_on_failure_and_retry(database, payments, remaining):
    client, body, _ = payments
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        prepared = deepcopy(before)
        prepared['customers'][0]['combo_purchases'] = [{
            'id':'purchase-1','combo_name':'Test combo','total':2,'used':2-remaining,
            'remaining':remaining,'unlimited':True,
        }]
        body['expected_revision'] = store.write(conn,before,prepared,'fixture')
    body['payload'].update(payment_method='COMBO',combo_purchase_id='purchase-1',customer_id='c1')
    initial = saved(database)
    response = client.post('/v2/live-tour/action',json=body)
    if remaining == 0:
        assert response.status_code == 409, response.text
        assert saved(database) == initial
    else:
        assert response.status_code == 200, response.text
        first = saved(database)
        assert first[0]['customers'][0]['combo_purchases'][0]['remaining'] == 1
        assert len(first[0]['combo_usage']) == 1
        assert client.post('/v2/live-tour/action',json=body).json()['duplicate'] is True
        assert saved(database) == first

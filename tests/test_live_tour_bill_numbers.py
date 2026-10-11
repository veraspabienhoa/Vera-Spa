"""Number registry invariants use disposable real PostgreSQL, never business data."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import vera_live_tour_bill_numbers as numbers
import vera_live_tour_relational as relational
import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW
from test_live_tour_resource_postgres import database
from test_live_tour_payment_scope_postgres import payments, saved


def activate(database):
    with database.begin() as conn:
        result = numbers.activate(conn)
        assert result['ok'] and result['active']
    return saved(database)[1]


def test_schema_install_is_inert_and_legacy_checkout_keeps_working(database, payments):
    client, body, _ = payments
    with database.begin() as conn:
        numbers.ensure_schema(conn)
        assert numbers.schema_ready(conn)
        assert conn.execute(text("SELECT coll.collname FROM pg_attribute att JOIN pg_collation coll ON coll.oid=att.attcollation WHERE att.attrelid='vera_live_tour_bill_number'::regclass AND att.attname='normalized'")).scalar_one()=='C'
        assert not numbers.enabled_in(store.read(conn)[0])
    response = client.post('/v2/live-tour/action',json=body)
    assert response.status_code == 200, response.text
    assert response.json()['result']['invoice']['bill_no']=='VERA-20260905-0021'


def test_activated_checkout_reads_no_history_preserves_amounts_replay_and_voids(database, payments, monkeypatch):
    client, body, seed = payments
    body['expected_revision'] = activate(database)
    original = store.read
    counts = []
    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get('payment_key'):
            counts.append((len(result[0]['invoices']),len(result[0]['invoice_changes'])))
        return result
    monkeypatch.setattr(store,'read',observe)
    response = client.post('/v2/live-tour/action',json=body)
    assert response.status_code==200,response.text
    invoice = response.json()['result']['invoice']
    assert invoice['bill_no']=='VERA-20260905-0021'
    assert invoice['total']==111 and invoice['tip']==11
    assert counts==[(0,0)]
    snapshot, revision = saved(database)
    assert snapshot['invoices'][:-1]==seed['invoices']
    assert snapshot['reports'][:-1]==seed['reports']
    assert snapshot['invoice_changes']==seed['invoice_changes']
    response = client.post('/v2/live-tour/action',json=body)
    assert response.status_code==200 and response.json()['duplicate']
    assert response.json()['result']['invoice']==invoice
    assert counts[-1]==(1,0)
    assert saved(database)[1]==revision
    # Actual void route keeps the number even after the canonical invoice disappears.
    void = client.post('/v2/live-tour/action',json={
        'action':'paid_invoice_delete','expected_revision':revision,'idempotency_key':'void-number-123',
        'response_view':'receipt','payload':{'invoice_id':invoice['id'],'reason':'Synthetic void'},
    })
    assert void.status_code==200,void.text
    response = client.post('/v2/live-tour/action',json=body)
    assert response.json()['duplicate'] and response.json()['result']['voided']
    assert response.json()['result']['invoice'] is None
    with database.begin() as conn:
        with pytest.raises(HTTPException) as exc:
            numbers.allocate(conn,{},invoice['bill_no'],'2026-09-05','different-owner')
        assert exc.value.status_code==409
        assert numbers.verify(conn)['ok']


@pytest.mark.parametrize('number', ['VERA-20260905-0001','  vera-20260905-0001 ', 'VOID-USED'])
def test_manual_normalized_collisions_rollback_everything(database,payments,number):
    client,body,_=payments
    body['expected_revision']=activate(database)
    initial=saved(database)
    body['payload']['bill_no']=number
    response=client.post('/v2/live-tour/action',json=body)
    assert response.status_code==409,response.text
    assert saved(database)==initial


def test_unicode_normalization_and_live_alias_floor_are_identical(database):
    with database.begin() as conn:
        store.lock(conn)
        before,_,_=store.read(conn); after=deepcopy(before)
        after['invoices']=[{'id':'i1','bill_no':'ĐẶC_BIỆT  01'}, {'id':'i2','bill_no':'LIVE-20260905-0088'}]
        after['invoice_changes']=[{'id':'void','before':{'id':'voided','bill_no':'VERA-20260905-0090'}}]
        after['bill_counters']={'2026-09-04':121}
        store.write(conn,before,after,'fixture')
    activate(database)
    with database.begin() as conn:
        for raw in ('dac biet 01','Đặc_biệt 01','ĐẶC BIỆT 01'):
            with pytest.raises(HTTPException):
                numbers.allocate(conn,{},raw,'2026-09-05','new')
        assert numbers.allocate(conn,{},'', '2026-09-05','new-a')=='VERA-20260905-0091'
        assert numbers.allocate(conn,{},'', '2026-09-04','new-b')=='VERA-20260904-0122'


def test_backdated_quick_checkout_matches_legacy_business_rules(database,payments):
    client,body,seed=payments
    service=next(row['id'] for row in seed['services'] if row['name']=='Body 90')
    body['action']='quick_checkout'
    body['payload']={'quick_booking':{'employee_id':'e1','service_items':[{'service_id':service,'quantity':1}],
        'room':'1.1','booked_at':'2026-09-04T14:00:00+07:00','correction_reason':'Synthetic previous date'},
        'payment_method':'TIỀN MẶT','tip':11}
    expected=live._apply_action(deepcopy(saved(database)[0]),body['action'],body['payload'],'admin',NOW)
    body['expected_revision']=activate(database)
    response=client.post('/v2/live-tour/action',json=body)
    assert response.status_code==200,response.text
    actual=response.json()['result']['invoice']
    for field in ('bill_no','subtotal','discount','tip','total','business_date','effective_at','entries'):
        assert actual[field]==expected['invoice'][field]


def test_failure_after_reservation_and_write_rolls_back_counter_receipt_and_money(database,payments,monkeypatch):
    client,body,_=payments
    body['expected_revision']=activate(database)
    initial=saved(database)
    with database.connect() as conn:
        initial_numbers=conn.execute(text(f'SELECT count(*) FROM {numbers.NUMBER_TABLE}')).scalar_one()
        initial_counter=conn.execute(text(f'SELECT value FROM {numbers.COUNTER_TABLE} WHERE day=\'2026-09-05\'')).scalar_one()
    original=store.write
    def fail(*args):
        original(*args)
        raise HTTPException(503,'Synthetic commit failure')
    monkeypatch.setattr(store,'write',fail)
    assert client.post('/v2/live-tour/action',json=body).status_code==503
    assert saved(database)==initial
    with database.connect() as conn:
        assert conn.execute(text(f'SELECT count(*) FROM {numbers.NUMBER_TABLE}')).scalar_one()==initial_numbers
        assert conn.execute(text(f'SELECT value FROM {numbers.COUNTER_TABLE} WHERE day=\'2026-09-05\'')).scalar_one()==initial_counter
    monkeypatch.setattr(store,'write',original)
    response=client.post('/v2/live-tour/action',json=body)
    assert response.status_code==200,response.text
    assert response.json()['result']['invoice']['bill_no']=='VERA-20260905-0021'


def test_activation_collision_and_transaction_abort_never_publish_partial_readiness(database):
    with database.begin() as conn:
        store.lock(conn); before,_,_=store.read(conn); after=deepcopy(before)
        after['invoices']=[{'id':'a','bill_no':'ĐẶC 01'},{'id':'b','bill_no':'dac_01'}]
        store.write(conn,before,after,'fixture')
    initial=saved(database)
    with pytest.raises(RuntimeError,match='Conflicting legacy'):
        with database.begin() as conn:
            numbers.activate(conn)
    assert saved(database)==initial
    with database.connect() as conn:
        assert not numbers.schema_ready(conn)
    with database.begin() as conn:
        conn.execute(text("DELETE FROM vera_live_tour_invoice WHERE resource_id='b'"))
    with pytest.raises(RuntimeError,match='abort'):
        with database.begin() as conn:
            numbers.activate(conn)
            raise RuntimeError('abort activation')
    with database.connect() as conn:
        assert not numbers.schema_ready(conn)
        assert not numbers.enabled_in(store.read(conn)[0])


def test_migration_waits_for_all_resource_writers_then_old_number_writes_fail_closed(database,payments):
    _,body,_=payments
    with database.begin() as held:
        store.begin_action(held,'checkout',body['payload'],body['expected_revision'],'held-writer',live._counter_business_date(NOW).isoformat(),compact=True)
        with database.begin() as other:
            with pytest.raises(HTTPException) as exc:
                numbers.activate(other)
            assert exc.value.status_code==503
    activate(database)
    with pytest.raises(DBAPIError):
        with database.begin() as conn:
            conn.execute(text("INSERT INTO vera_live_tour_invoice(resource_id,ordinal,payload,payload_hash) VALUES('old-writer',99,'{\"id\":\"old-writer\",\"bill_no\":\"VERA-20260905-0021\"}','old')"))
    with database.begin() as conn:
        # Existing receipt edits keep their immutable bill number and remain valid.
        conn.execute(text("UPDATE vera_live_tour_invoice SET payload=payload||'{\"note\":\"synthetic note\"}' WHERE resource_id='old-0'"))
    with pytest.raises(DBAPIError):
        with database.begin() as conn:
            conn.execute(text(f"UPDATE vera_live_tour_meta SET payload=payload-'{numbers.MARKER}' WHERE singleton=1"))


def test_concurrent_auto_and_manual_reservations_are_unique_and_transactional(database):
    activate(database)
    barrier=Barrier(2)
    def reserve(manual):
        with database.begin() as conn:
            barrier.wait(timeout=5)
            try:
                return numbers.allocate(conn,{},manual,'2026-09-05','manual' if manual else 'auto')
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(reserve,value) for value in ('','VERA-20260905-0001')]
        results=[f.result(timeout=10) for f in futures]
    assert results[0] in {'VERA-20260905-0001','VERA-20260905-0002'}
    assert results[1] in {'VERA-20260905-0001',409}
    strings=[value for value in results if isinstance(value,str)]
    assert len(strings)==len(set(strings))
    assert numbers.current_connection() is None


def test_deactivation_preserves_floors_tombstones_and_refuses_unsafe_old_release(database,payments):
    _,_,_=payments
    activate(database)
    with database.begin() as conn:
        assert numbers.deactivate(conn)['active'] is False
        assert not numbers.enabled_in(store.read(conn)[0])
    activate(database)
    with database.begin() as conn:
        numbers.allocate(conn,{},'unrepresented-permanent-number','2026-09-05','orphan')
    with pytest.raises(RuntimeError,match='Legacy history'):
        with database.begin() as conn:
            numbers.deactivate(conn)
    with database.connect() as conn:
        assert numbers.enabled_in(store.read(conn)[0])
    with pytest.raises(DBAPIError):
        with database.begin() as conn:
            conn.execute(text(f'DELETE FROM {numbers.NUMBER_TABLE}'))


def test_context_scope_does_not_leak_after_error_or_cross_thread(database):
    with database.begin() as conn:
        with pytest.raises(ValueError):
            with numbers.allocation_scope(conn,{numbers.MARKER:True}):
                assert numbers.current_connection() is conn
                with ThreadPoolExecutor(max_workers=1) as pool:
                    assert pool.submit(numbers.current_connection).result() is None
                raise ValueError('reset')
        assert numbers.current_connection() is None


@pytest.mark.parametrize('replay_present',[False,True])
def test_active_payment_read_plan_never_scans_old_invoice_or_change_rows(database,payments,replay_present):
    client,body,_=payments
    with database.begin() as conn:
        store.lock(conn); before,_,_=store.read(conn); seeded=deepcopy(before)
        seeded['invoices'].extend({'id':f'explain-{i}','bill_no':f'VERA-20260905-{i:04d}'} for i in range(100,2100))
        store.write(conn,before,seeded,'fixture')
    body['expected_revision']=activate(database)
    invoice_id=None
    if replay_present:
        response=client.post('/v2/live-tour/action',json=body)
        assert response.status_code==200,response.text
        invoice_id=response.json()['result']['invoice']['id']
    from sqlalchemy import event
    plans=[]
    with database.begin() as conn:
        conn.execute(text('ANALYZE'))
        def capture(_conn,_cursor,statement,params,_context,_executemany):
            if statement.lstrip().startswith('SELECT') and " AS kind" in statement and 'payment_key' in params:
                plans.append((statement,params))
        event.listen(conn,'before_cursor_execute',capture)
        state,_,_=store.read(conn,payment_key=body['idempotency_key'])
        event.remove(conn,'before_cursor_execute',capture)
        assert len(state['invoices'])==int(replay_present) and state['invoice_changes']==[]
        if replay_present:
            assert state['invoices'][0]['id']==invoice_id
        assert len(plans)==1
        statement,params=plans[0]
        plan=conn.exec_driver_sql('EXPLAIN (ANALYZE,FORMAT JSON) '+statement,params).scalar_one()[0]['Plan']
    def flatten(node):
        yield node
        for child in node.get('Plans',[]):
            yield from flatten(child)
    nodes=list(flatten(plan))
    # Small synthetic tables may choose a seq scan for the keyed replay; it
    # must execute zero loops when no replay invoice exists, and the legacy
    # all-history branches always execute zero loops after activation.
    invoice_scans=[node for node in nodes if node.get('Relation Name') in {'vera_live_tour_invoice','vera_live_tour_invoice_change'}]
    assert invoice_scans
    assert sum(node['Actual Rows'] for node in invoice_scans)==int(replay_present)
    assert all(node['Actual Loops']==0 for node in invoice_scans if node['Node Type']=='Seq Scan')
    if replay_present:
        assert any(node.get('Index Name')=='vera_live_tour_invoice_pkey' and node['Actual Rows']==1 for node in invoice_scans)
        with database.connect() as conn:
            guard_plan=conn.execute(text(f'''EXPLAIN (ANALYZE,FORMAT JSON)
                SELECT 1 FROM {numbers.NUMBER_TABLE} WHERE invoice_id=:owner AND :number=ANY(raw_numbers)'''),
                {'owner':invoice_id,'number':state['invoices'][0]['bill_no']}).scalar_one()[0]['Plan']
        assert any(node.get('Index Name')=='idx_vera_bill_owner' for node in flatten(guard_plan))


def test_aggregate_rollback_uses_verified_number_deactivation(database,payments):
    from vera_live_tour_cutover import run
    client,body,_=payments
    body['expected_revision']=activate(database)
    assert client.post('/v2/live-tour/action',json=body).status_code==200
    with database.begin() as conn:
        result=run(conn,rollback=True)
        assert result['ok'] and result['mode']=='aggregate'
        payload=conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='live_tour' AND setting_key='state'")).scalar_one()
        assert numbers.MARKER not in payload
        assert payload['bill_counters']['2026-09-05']==21
        assert live._next_bill_no(payload,{},NOW,calendar_day=True)=='VERA-20260905-0022'


def test_pool_reuse_after_number_collision_does_not_keep_an_allocator(database,payments):
    client,body,_=payments
    body['expected_revision']=activate(database)
    body['payload']['bill_no']='VOID-USED'
    assert client.post('/v2/live-tour/action',json=body).status_code==409
    body['payload'].pop('bill_no')
    assert client.post('/v2/live-tour/action',json=body).status_code==200
    assert numbers.current_connection() is None


def test_spoofed_deactivation_marker_cannot_bypass_database_parity(database,payments):
    activate(database)
    with database.begin() as conn:
        numbers.allocate(conn,{},'unrepresented-number','2026-09-05','missing-owner')
    with pytest.raises(DBAPIError):
        with database.begin() as conn:
            conn.execute(text("SET LOCAL vera.live_tour_bill_cutover='allow-legacy'"))
            conn.execute(text(f"UPDATE vera_live_tour_meta SET payload=payload-'{numbers.MARKER}'-'_resource_ready' WHERE singleton=1"))
    with database.connect() as conn:
        assert numbers.enabled_in(store.read(conn)[0])


def test_spoofed_deactivation_cannot_discard_durable_counter_floor(database,payments):
    activate(database)
    with database.begin() as conn:
        numbers._raise_floor(conn,'2026-09-05',100)
    with pytest.raises(DBAPIError):
        with database.begin() as conn:
            conn.execute(text("SET LOCAL vera.live_tour_bill_cutover='allow-legacy'"))
            conn.execute(text(f"UPDATE vera_live_tour_meta SET payload=payload-'{numbers.MARKER}' WHERE singleton=1"))
    with database.connect() as conn:
        assert numbers.enabled_in(store.read(conn)[0])


def test_combo_sale_registry_uses_existing_business_day_rule_and_retry(database,payments):
    client,body,_=payments
    with database.begin() as conn:
        store.lock(conn); before,_,_=store.read(conn); seeded=deepcopy(before)
        seeded['combos']=[{'id':'combo-sale','name':'Synthetic 10 tickets','tickets':10,'price':1000,'unlimited':True}]
        store.write(conn,before,seeded,'fixture')
    body.update(action='combo_purchase',expected_revision=activate(database),
                payload={'combo_id':'combo-sale','customer_id':'c1','quantity':2,'payment_method':'TIỀN MẶT'})
    response=client.post('/v2/live-tour/action',json=body)
    assert response.status_code==200,response.text
    invoice=response.json()['result']['invoice']
    assert invoice['total']==2000 and invoice['combo_purchased_units']==20
    assert invoice['bill_no']=='VERA-20260905-0021'
    before=saved(database)
    replay=client.post('/v2/live-tour/action',json=body)
    assert replay.status_code==200 and replay.json()['duplicate']
    assert saved(database)==before
    with database.connect() as conn:
        assert numbers.verify(conn)['ok']


@pytest.mark.parametrize('attempt',range(5))
def test_simultaneous_activation_is_idempotent_and_advances_publication_once(database,payments,attempt):
    before,revision=saved(database)
    barrier=Barrier(2)
    def migrate():
        with database.begin() as conn:
            barrier.wait(timeout=5)
            return numbers.activate(conn)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:migrate(),range(2)))
    assert all(result['ok'] and result['active'] for result in results)
    state,current=saved(database)
    assert current==revision+1
    assert state['invoices']==before['invoices'] and state['invoice_changes']==before['invoice_changes']
    with database.connect() as conn:
        assert conn.execute(text(f'SELECT count(*) FROM {numbers.NUMBER_TABLE}')).scalar_one()==21


def test_schema_migration_can_repeat_without_releasing_number_guards(database):
    with database.begin() as conn:
        numbers.ensure_schema(conn)
        conn.execute(text(f"INSERT INTO {numbers.NUMBER_TABLE}(normalized,invoice_id,raw_numbers) VALUES('reserved','owner',ARRAY['RESERVED'])"))
        # A missing readiness row must not make additive recovery DDL fail or
        # remove the immutable reservation constraint.
        conn.execute(text("DELETE FROM vera_read_path_schema WHERE component=:component"), {'component':numbers.COMPONENT})
        numbers.ensure_schema(conn)
        assert numbers.schema_ready(conn)
    with pytest.raises(DBAPIError):
        with database.begin() as conn:
            conn.execute(text(f"UPDATE {numbers.NUMBER_TABLE} SET invoice_id='other' WHERE normalized='reserved'"))
    with database.connect() as conn:
        assert conn.execute(text(f"SELECT invoice_id FROM {numbers.NUMBER_TABLE} WHERE normalized='reserved'")).scalar_one()=='owner'

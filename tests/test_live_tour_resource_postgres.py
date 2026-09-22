"""Real PostgreSQL transaction tests; CI provisions an isolated service database."""
import os
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from fastapi import HTTPException
import vera_live_tour_resource_store as store
import vera_live_tour_relational as relational
import vera_web_v2_live_tour as live
from vera_live_tour_cutover import run as cutover
from test_live_tour_backend import NOW, employee, payable_employee, state_with


@pytest.fixture
def database(monkeypatch):
    url=os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('VERA_TEST_POSTGRES_URL is required for real PostgreSQL tests')
    schema='tour_test_'+uuid4().hex
    admin=create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine=create_engine(url,connect_args={'options':f'-csearch_path={schema}'})
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE','shadow')
    initial=state_with(employee('e1','An'),employee('e2','Bình'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE vera_app_setting(category text,setting_key text,value_json jsonb,revision bigint,updated_at timestamptz,PRIMARY KEY(category,setting_key))'))
        conn.execute(text('CREATE TABLE employees(username text,full_name text,bank_name text,bank_account text)'))
        conn.execute(text("INSERT INTO vera_app_setting VALUES('live_tour','state',CAST(:state AS jsonb),7,NOW())"),{'state':relational._json(initial)})
        assert cutover(conn)['ok']
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE','active')
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
    admin.dispose()


def begin(conn, employee_id, key='test-key-1234', revision=7, action='set_vip', **payload):
    return store.begin_action(conn,action,{'employee_id':employee_id,**payload},revision,key,live._counter_business_date(NOW).isoformat())


def test_disjoint_edits_commit_without_lost_updates_and_old_client_can_edit_untouched_row(database):
    barrier=Barrier(2)
    def edit(identifier):
        with database.begin() as conn:
            state,revision,fresh=begin(conn,identifier,key='request-'+identifier)
            assert fresh
            working=deepcopy(state)
            live._apply_action(working,'set_vip',{'employee_id':identifier},'admin',NOW)
            working['idempotency']['request-'+identifier]={'status':'completed','result':{'employee_id':identifier}}
            barrier.wait(timeout=5)
            return store.write(conn,state,working,'admin')
    with ThreadPoolExecutor(max_workers=2) as pool:
        revisions=list(pool.map(edit,['e1','e2']))
    assert sorted(revisions)==[8,9]
    with database.begin() as conn:
        state,revision,_=store.read(conn)
        assert revision==9 and all(row['vip'] for row in state['employees'])
        assert len(state['audit'])==2 and len(state['idempotency'])==2
        # Legacy aggregate is frozen after cutover: no giant JSON writes.
        assert conn.execute(text("SELECT revision FROM vera_app_setting WHERE category='live_tour'")).scalar_one()==7


def test_same_employee_and_same_physical_room_fail_fast(database):
    with database.begin() as first:
        begin(first,'e1')
        with database.begin() as second:
            with pytest.raises(HTTPException) as exc:
                begin(second,'e1',key='other-request')
            assert exc.value.status_code==503
    with database.begin() as first:
        begin(first,'e1',action='booking',room='1.1')
        with database.begin() as second:
            with pytest.raises(HTTPException) as exc:
                begin(second,'e2',key='room-request',action='booking',room='1.2')
            assert exc.value.status_code==503


def test_stale_row_rejected_and_failed_write_rolls_back(database):
    with database.begin() as conn:
        state,_,_=begin(conn,'e1')
        changed=deepcopy(state);changed['employees'][0]['vip']=True
        store.write(conn,state,changed,'admin')
    with database.begin() as conn:
        _,_,fresh=begin(conn,'e1')
        assert not fresh
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            state,_,fresh=begin(conn,'e2',key='rollback-request')
            assert fresh
            changed=deepcopy(state);changed['employees'][1]['vip']=True
            store.write(conn,state,changed,'admin')
            raise RuntimeError('abort transaction')
    with database.begin() as conn:
        state,revision,_=store.read(conn)
        assert revision==8 and not state['employees'][1]['vip']


def test_exclusive_operations_block_scoped_edits_and_rollback_exports_current_rows(database):
    with database.begin() as first:
        store.lock(first)
        with database.begin() as second:
            with pytest.raises(HTTPException):
                begin(second,'e1')
    with database.begin() as conn:
        state,_,_=begin(conn,'e1')
        changed=deepcopy(state);changed['employees'][0]['vip']=True
        store.write(conn,state,changed,'admin')
    with database.begin() as conn:
        assert cutover(conn,rollback=True)['ok']
        restored=conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='live_tour'")).scalar_one()
        assert restored['employees'][0]['vip']
        assert '_resource_ready' not in restored


def test_checkout_retry_is_idempotent_and_lists_read_current_canonical_storage(database, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    class Identity(BaseModel):
        employee_username: str='admin'
        full_name: str='Admin'
        role: str='admin'
    class FixedDateTime(live.datetime):
        @classmethod
        def now(cls,tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(live,'datetime',FixedDateTime)
    with database.begin() as conn:
        store.lock(conn)
        before,_,_=store.read(conn)
        state=deepcopy(before)
        state['employees'][0]=payable_employee('e1','An')
        state['customers']=[{'id':'c1','name':'Khách c1','phone':'0901','combo_purchases':[]}]
        revision=store.write(conn,before,state,'admin')
    app=FastAPI()
    live.install_live_tour_routes(app,engine_instance=lambda:database,current_identity=lambda:Identity(),require_feature=lambda *args:None,feature_allowed=lambda *args:True,identity_type=Identity)
    client=TestClient(app)
    body={'action':'checkout','expected_revision':revision,'idempotency_key':'payment-once-123','response_view':'board','payload':{'employee_id':'e1','payment_method':'TIỀN MẶT'}}
    first=client.post('/v2/live-tour/action',json=body)
    assert first.status_code==200,first.text
    replay=client.post('/v2/live-tour/action',json=body)
    assert replay.status_code==200,replay.text
    assert replay.json()['duplicate'] is True
    invoices=client.get('/v2/live-tour/collections/invoices').json()
    assert invoices['total']==1 and len(invoices['data']['state']['invoices'])==1
    assert client.get('/v2/live-tour?view=board').json()['state']['invoices']==[]

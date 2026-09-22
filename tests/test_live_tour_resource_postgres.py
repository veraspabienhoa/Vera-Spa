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


def test_customer_reservation_lock_is_shared_across_distinct_employees(database):
    with database.begin() as first:
        begin(first, 'e1', action='booking', customer_id='shared-customer', room='1.1')
        with database.begin() as second:
            with pytest.raises(HTTPException) as exc:
                begin(second, 'e2', key='second-combo-booking', action='booking', customer_id='shared-customer', room='2.1')
            assert exc.value.status_code == 503


def test_receipt_pruning_removes_only_keys_from_its_snapshot(database):
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        after = deepcopy(before)
        after['idempotency'] = {'old': {'action': 'set_vip'}, 'payment': {'action': 'checkout'}}
        revision = store.write(conn, before, after, 'admin')
    with database.begin() as conn:
        before, _, _ = begin(conn, 'e1', revision=revision)
        after = deepcopy(before)
        after['idempotency'].pop('old')
        after['idempotency']['new'] = {'action': 'set_vip'}
        store.write(conn, before, after, 'admin')
    with database.begin() as conn:
        state, _, _ = store.read(conn)
        assert set(state['idempotency']) == {'payment', 'new'}


def prepare_starts(database, *, same_room=False, second_on_break=False):
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        state = deepcopy(before)
        state['employees'].append(employee('e3', 'Chưa thực hiện'))
        for index, row in enumerate(state['employees'][:2], 1):
            row.update(service='Body 90', room=f'1.{index}' if same_room else f'{index}.1',
                       status='Đang chờ', duration=90, booked_at=live._iso(NOW),
                       booking_id=f'booking-{index}', service_price=220000)
        if second_on_break:
            state['employees'][1]['break_started_at'] = live._iso(NOW)
        live._apply_action(state, 'admin_reorder', {'employee_id':'e1','direction':'top'}, 'admin', NOW)
        return store.write(conn, before, state, 'admin')


def test_two_starts_on_distinct_rooms_commit_together_without_other_employee_writes(database):
    revision = prepare_starts(database)
    with database.begin() as conn:
        initial, _, versions = store.read(conn)
    barrier = Barrier(2)
    def start(identifier):
        with database.begin() as conn:
            state, _, fresh = begin(conn, identifier, key='start-'+identifier, revision=revision, action='start')
            assert fresh and conn.info['live_tour_exclusive'] is False
            working = deepcopy(state)
            live._apply_action(working, 'start', {'employee_id':identifier}, 'admin', NOW)
            barrier.wait(timeout=5)
            return store.write(conn, state, working, 'admin')
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(start, ['e1','e2'])) == [revision+1, revision+2]
    with database.begin() as conn:
        final, _, final_versions = store.read(conn)
    assert [row['tour_count'] for row in final['employees'][:2]] == [1,1]
    assert all(row['status'] == 'Đang thực hiện' for row in final['employees'][:2])
    assert final['employees'][2] == initial['employees'][2]
    assert final_versions[('employees','e3')] == versions[('employees','e3')]
    assert final['manual_order_active'] is False
    assert not any(row['_manual_order'] for row in live._state_response(final, revision+2, NOW)['records'])
    assert live._state_response(final, revision+2, NOW)['records'][0]['_employee_id'] == 'e3'


def test_start_room_locks_all_its_members_and_conflicts_with_same_room_start(database):
    revision = prepare_starts(database, same_room=True)
    with database.begin() as first:
        state, _, fresh = begin(first, '', action='start_room', room='1', revision=revision)
        assert fresh and first.info['live_tour_exclusive'] is False
        assert {('live_tour_employee','e1'),('live_tour_employee','e2')} <= set(first.info['live_tour_resources'])
        with database.begin() as second:
            with pytest.raises(HTTPException) as exc:
                begin(second, 'e2', action='start', revision=revision, key='conflicting-start')
            assert exc.value.status_code == 503
        # An unrelated employee edit can still hold its own locks concurrently.
        with database.begin() as unrelated:
            _, _, fresh = begin(unrelated, 'e3', revision=revision, key='unrelated-edit')
            assert fresh
        changed = deepcopy(state)
        result = live._apply_action(changed, 'start_room', {'room':'1'}, 'admin', NOW)
        assert result['count'] == 2
        store.write(first, state, changed, 'admin')


def test_start_same_physical_room_serializes_even_for_different_employees(database):
    revision = prepare_starts(database, same_room=True)
    with database.begin() as first:
        begin(first, 'e1', action='start', revision=revision)
        with database.begin() as second:
            with pytest.raises(HTTPException) as exc:
                begin(second, 'e2', action='start', revision=revision, key='same-room-start')
            assert exc.value.status_code == 503


def test_failed_room_start_does_not_change_any_member_or_manual_order(database):
    revision = prepare_starts(database, same_room=True, second_on_break=True)
    with database.begin() as conn:
        original, _, _ = store.read(conn)
    with pytest.raises(HTTPException):
        with database.begin() as conn:
            state, _, _ = begin(conn, '', action='start_room', room='1', revision=revision)
            changed = deepcopy(state)
            live._apply_action(changed, 'start_room', {'room':'1'}, 'admin', NOW)
            store.write(conn, state, changed, 'admin')
    with database.begin() as conn:
        current, current_revision, _ = store.read(conn)
    assert current == original and current_revision == revision


def test_start_excludes_reorder_and_rollback_materializes_effective_order(database):
    revision = prepare_starts(database)
    with database.begin() as conn:
        before, _, _ = begin(conn, 'e1', action='start', revision=revision)
        with database.begin() as other:
            with pytest.raises(HTTPException):
                store.lock(other)
        after = deepcopy(before)
        live._apply_action(after, 'start', {'employee_id':'e1'}, 'admin', NOW)
        store.write(conn, before, after, 'admin')
    with database.begin() as conn:
        cutover(conn, rollback=True)
        restored = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='live_tour'")).scalar_one()
    assert 'manual_order_active' not in restored
    assert not any(row.get('manual_order') for row in restored['employees'])
    assert restored['employees'][0]['tour_count'] == 1


def test_start_retry_counts_tour_once_and_stale_new_request_is_rejected(database, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    class Identity(BaseModel):
        employee_username: str = 'admin'
        full_name: str = 'Admin'
        role: str = 'admin'
    class FixedDateTime(live.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(live, 'datetime', FixedDateTime)
    revision = prepare_starts(database)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda:database, current_identity=lambda:Identity(),
                                 require_feature=lambda *args:None, feature_allowed=lambda *args:True, identity_type=Identity)
    client = TestClient(app)
    body = {'action':'start','expected_revision':revision,'idempotency_key':'start-once-1234',
            'response_view':'board','payload':{'employee_id':'e1'}}
    first = client.post('/v2/live-tour/action', json=body)
    assert first.status_code == 200, first.text
    retry = client.post('/v2/live-tour/action', json=body)
    assert retry.status_code == 200 and retry.json()['duplicate'] is True
    stale = client.post('/v2/live-tour/action', json={**body,'idempotency_key':'new-stale-start'})
    assert stale.status_code == 409
    with database.begin() as conn:
        state, current_revision, _ = store.read(conn)
    assert state['employees'][0]['tour_count'] == 1
    assert current_revision == revision + 1
    assert not any(row['_manual_order'] for row in retry.json()['records'])

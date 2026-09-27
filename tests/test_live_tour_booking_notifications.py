"""Real booking commits and the shared outbox: recipient, cost and failure isolation."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import event, text

import vera_live_tour_resource_store as store
import vera_live_tour_relational as relational
import vera_web_v2_live_tour as live
from vera_live_tour_cutover import run as cutover
from test_notification_schema_locking import database
from test_unified_notifications_postgres import notices, subscribe, dispatch
from test_notification_routing import Identity
from test_live_tour_backend import NOW, employee, state_with


@pytest.fixture
def booking_api(database, booking_state, monkeypatch):
    clock = [NOW.replace(hour=11,minute=10,second=0)]
    class Operator(BaseModel):
        employee_username: str = 'admin'
        full_name: str = 'Test operator'
        role: str = 'admin'
    class Clock(live.datetime):
        @classmethod
        def now(cls,tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
    monkeypatch.setattr(live,'datetime',Clock)
    app=FastAPI()
    live.install_live_tour_routes(app,engine_instance=lambda:database,
        current_identity=lambda:Operator(),require_feature=lambda *args:None,
        feature_allowed=lambda *args:True,identity_type=Operator)
    # Measure the real HTTP transaction without unrelated projection scheduler
    # threads checking out connections. Dispatch is exercised explicitly below;
    # existing lifespan/queue tests cover the background scheduler independently.
    client=TestClient(app)
    try:yield client,clock
    finally:client.close()


@pytest.fixture
def booking_state(database, notices, monkeypatch):
    accounts, _, _ = notices
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE','shadow')
    state = state_with(employee('e1','Minh Anh'),employee('e2','Bình'))
    for worker in state['employees']:
        worker['username'] = worker['name']
    service = next(row for row in state['services'] if row['name'] in {'VIP 90 PR','90 PR VIP'})
    service.update(name='90 PR Tiêu chuẩn',duration=90,price=350000)
    with database.begin() as conn:
        conn.execute(text('''ALTER TABLE vera_app_setting ADD PRIMARY KEY(category,setting_key);
            ALTER TABLE vera_app_setting ADD COLUMN revision bigint, ADD COLUMN updated_at timestamptz, ADD COLUMN source text, ADD COLUMN updated_by text;
            CREATE TABLE employees(username text,full_name text,bank_name text,bank_account text);'''))
        conn.execute(text("INSERT INTO vera_app_setting(category,setting_key,value_json,revision,updated_at) VALUES('live_tour','state',CAST(:state AS jsonb),7,NOW())"), {'state':relational._json(state)})
        for role, name in [('nhanvien','Minh Anh'),('leader','Bình')]:
            conn.execute(text('UPDATE vera_v2_user_profile SET employee_username=:name WHERE auth_user_id=CAST(:id AS uuid)'), {'name':name,'id':accounts[role]})
        assert cutover(conn)['ok']
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE','active')
    return accounts


def booking(revision=7, **overrides):
    return {'action':'booking','payload':{'employee_id':'e1','service':'90 PR Tiêu chuẩn','room':'2.1','request':'YC'},
            'expected_revision':revision,'idempotency_key':'booking-notice-once','response_view':'board',**overrides}


def stored(database):
    with database.connect() as conn:
        return list(conn.execute(text('SELECT * FROM vera_notification_delivery ORDER BY id')).mappings())


@pytest.mark.parametrize('mode',['active','off'])
def test_booking_commits_exact_employee_notice_once_without_sending_in_transaction(database, booking_state, booking_api, notices, monkeypatch, mode):
    if mode=='off':
        with database.begin() as conn:
            assert cutover(conn,rollback=True)['ok']
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE',mode)
    client, _ = booking_api
    statements, connections = [], []
    def capture(conn,cursor,statement,parameters,context,executemany):
        statements.append(statement)
        connections.append(id(conn))
    event.listen(database,'before_cursor_execute',capture)
    try:
        response = client.post('/v2/live-tour/action',json=booking())
        assert response.status_code == 200, response.text
    finally:
        event.remove(database,'before_cursor_execute',capture)
    inserts = [sql for sql in statements if 'INSERT INTO vera_notification_delivery' in sql]
    assert len(inserts) == 1, 'all recipients/channels must use one SQL INSERT'
    assert not any('CREATE' in sql or 'ALTER TABLE' in sql for sql in statements)
    # Production resource mode has its existing post-commit response read; this
    # notification does not acquire another connection or load subscriptions.
    assert len(set(connections)) <= (2 if mode=='active' else 1)
    assert not any('vera_v2_push_subscription' in sql for sql in statements)
    rows = stored(database)
    assert len(rows)==3 and {row['channel'] for row in rows}=={'in_app','push','popup'}
    assert {row['recipient'] for row in rows}=={booking_state['nhanvien']}
    assert {row['payload']['body'] for row in rows}=={'Minh Anh | 90 PR Tiêu chuẩn | YC | 2.1'}
    assert client.post('/v2/live-tour/action',json=booking()).json()['duplicate']
    assert len(stored(database))==3
    subscribe(database,booking_state['nhanvien'])
    subscribe(database,booking_state['leader'])
    sent=dispatch(database)  # helper asserts zero checked-out DB connections at send
    assert len(sent)==1 and sent[0]['recipient_id']==booking_state['nhanvien']
    assert not any(key.startswith('_') for key in sent[0])
    accounts, identity, inbox = notices
    identity[0]=Identity(role='nhanvien',auth_user_id=accounts['nhanvien'])
    visible=inbox.get('/v2/notification-inbox').json()['notifications']
    assert len(visible)==1 and str(visible[0]['id'])==sent[0]['notification_id']
    feed=inbox.get('/v2/notification-feed').json()
    assert len(feed['popup'])==1
    popup=feed['popup'][0]
    assert popup['payload']['body']==visible[0]['payload']['body']
    assert popup['payload']['tag']==visible[0]['payload']['tag']
    assert not any(key.startswith('_') for key in popup['payload'])
    identity[0]=Identity(role='leader',auth_user_id=accounts['leader'])
    assert inbox.get('/v2/notification-inbox').json()['notifications']==[]
    assert inbox.get('/v2/notification-popup').json()['notifications']==[]
    assert inbox.get(f"/v2/notification-inbox/{popup['id']}").status_code==404
    identity[0]=Identity(role='nhanvien',auth_user_id=accounts['nhanvien'])
    assert inbox.post(f"/v2/notification-inbox/{visible[0]['id']}/read").status_code==200
    assert inbox.get('/v2/notification-popup').json()['notifications']==[]
    assert all(row['read_at'] for row in stored(database))


def test_batch_booking_is_one_insert_and_each_employee_gets_own_details(database, booking_state, booking_api):
    client, _=booking_api
    second={**booking()['payload'],'employee_id':'e2','room':'20.1','request':''}
    request=booking(action='multi_booking',payload={'bookings':[booking()['payload'],second]})
    inserts=[]
    def capture(conn,cursor,statement,*args):
        if 'INSERT INTO vera_notification_delivery' in statement:inserts.append(statement)
    event.listen(database,'before_cursor_execute',capture)
    try:
        response=client.post('/v2/live-tour/action',json=request)
        assert response.status_code==200,response.text
    finally:event.remove(database,'before_cursor_execute',capture)
    assert len(inserts)==1
    rows=stored(database)
    assert len(rows)==6
    assert {row['recipient'] for row in rows}=={booking_state['nhanvien'],booking_state['leader']}
    assert all(row['payload']['body'].startswith('Minh Anh |') if row['recipient']==booking_state['nhanvien'] else row['payload']['body'].startswith('Bình |') for row in rows)


def test_failed_booking_and_failed_state_write_leave_no_notifications(database, booking_state, booking_api, monkeypatch):
    client, _=booking_api
    invalid=booking(payload={**booking()['payload'],'room':'missing'})
    assert client.post('/v2/live-tour/action',json=invalid).status_code==400
    assert stored(database)==[]
    original=live._write_state_compat
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise HTTPException(503,'Injected business rollback')
    monkeypatch.setattr(live,'_write_state_compat',fail)
    assert client.post('/v2/live-tour/action',json=booking()).status_code==503
    assert stored(database)==[]
    monkeypatch.setattr(live,'_write_state_compat',original)
    assert client.post('/v2/live-tour/action',json=booking()).status_code==200
    assert len(stored(database))==3


def test_notification_storage_error_does_not_break_successful_booking(database, booking_state, booking_api):
    client, _=booking_api
    with database.begin() as conn:
        conn.execute(text("ALTER TABLE vera_notification_delivery ADD CONSTRAINT simulated_failure CHECK(rule_key<>'native:live_tour_booking')"))
    response=client.post('/v2/live-tour/action',json=booking())
    assert response.status_code==200,response.text
    assert response.json()['result']['employee']['service']=='90 PR Tiêu chuẩn'
    assert stored(database)==[]


@pytest.mark.parametrize('control',['source','push','locked','rebound'])
def test_pending_booking_honors_current_admin_and_account_controls(database, booking_state, booking_api, notices, control):
    client,_=booking_api
    assert client.post('/v2/live-tour/action',json=booking()).status_code==200
    subscribe(database,booking_state['nhanvien'])
    with database.begin() as conn:
        if control=='source':
            conn.execute(text("INSERT INTO vera_v2_notification_setting(notification_key,enabled) VALUES('live_tour_booking',false)"))
        elif control=='push':
            conn.execute(text("INSERT INTO vera_v2_notification_channel_setting(notification_key,channel,enabled,updated_by) VALUES('live_tour_booking','push',false,'test')"))
        elif control=='locked':
            conn.execute(text('UPDATE vera_v2_user_profile SET is_active=false WHERE auth_user_id=CAST(:id AS uuid)'), {'id':booking_state['nhanvien']})
        else:
            conn.execute(text("UPDATE vera_v2_user_profile SET employee_username='Someone else' WHERE auth_user_id=CAST(:id AS uuid)"), {'id':booking_state['nhanvien']})
    assert dispatch(database)==[]
    accounts,identity,inbox=notices
    identity[0]=Identity(role='nhanvien',auth_user_id=accounts['nhanvien'])
    assert len(inbox.get('/v2/notification-inbox').json()['notifications'])==(1 if control=='push' else 0)
    assert len(inbox.get('/v2/notification-popup').json()['notifications'])==(1 if control=='push' else 0)


@pytest.mark.parametrize('channel',['popup','push','in_app'])
def test_booking_channel_switches_are_independent(database, booking_state, booking_api, notices, channel):
    accounts,identity,client=notices
    changed=client.put(f'/v2/notification-settings/live_tour_booking/channels/{channel}',json={'enabled':False})
    assert changed.status_code==200,changed.text
    booking_client,_=booking_api
    assert booking_client.post('/v2/live-tour/action',json=booking()).status_code==200
    assert {row['channel'] for row in stored(database)}=={'in_app','push','popup'}-{channel}
    identity[0]=Identity(role='nhanvien',auth_user_id=accounts['nhanvien'])
    assert len(client.get('/v2/notification-popup').json()['notifications'])==(0 if channel=='popup' else 1)
    subscribe(database,accounts['nhanvien'])
    assert len(dispatch(database))==(0 if channel=='push' else 1)


def test_admin_can_hide_pending_popup_without_disabling_lock_screen(database, booking_state, booking_api, notices):
    accounts,identity,client=notices
    booking_client,_=booking_api
    assert booking_client.post('/v2/live-tour/action',json=booking()).status_code==200
    assert client.put('/v2/notification-settings/live_tour_booking/channels/popup',json={'enabled':False}).status_code==200
    identity[0]=Identity(role='nhanvien',auth_user_id=accounts['nhanvien'])
    assert client.get('/v2/notification-popup').json()['notifications']==[]
    assert len(client.get('/v2/notification-inbox').json()['notifications'])==1
    subscribe(database,accounts['nhanvien'])
    assert len(dispatch(database))==1


def test_admin_toggle_controls_new_bookings_and_cannot_broadcast_them(database, booking_state, booking_api, notices):
    accounts,identity,settings=notices
    items=settings.get('/v2/notification-settings').json()
    source=next(item for item in items['settings'] if item['key']=='live_tour_booking')
    assert source['enabled'] and source['recipient_locked']
    revision=items['revision']
    changed=settings.put('/v2/notification-settings/live_tour_booking',json={'enabled':False,'revision':revision})
    assert changed.status_code==200,changed.text
    client,_=booking_api
    assert client.post('/v2/live-tour/action',json=booking()).status_code==200
    assert stored(database)==[]
    revision=changed.json()['revision']
    blocked=settings.put('/v2/notification-settings/live_tour_booking',json={'enabled':True,'revision':revision,'recipients':['group:all'],'channels':['push']})
    assert blocked.status_code==400
    changed=settings.put('/v2/notification-settings/live_tour_booking',json={'enabled':True,'revision':revision})
    assert changed.status_code==200,changed.text
    response=client.post('/v2/live-tour/action',json=booking(revision=8,idempotency_key='second-booking-notice',payload={**booking()['payload'],'employee_id':'e2','room':'20.1'}))
    assert response.status_code==200,response.text
    assert {row['recipient'] for row in stored(database)}=={accounts['leader']}
    identity[0]=Identity(role='nhanvien',auth_user_id=accounts['nhanvien'])
    assert settings.put('/v2/notification-settings/live_tour_booking',json={'enabled':False}).status_code==403

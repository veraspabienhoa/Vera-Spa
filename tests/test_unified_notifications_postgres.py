"""One logical notice across inbox and Web Push, with real PostgreSQL grants."""
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import vera_notification_delivery as delivery
import vera_web_v2_notification_settings as settings
from test_notification_routing import Identity
from test_notification_schema_locking import database


@pytest.fixture
def notices(database):
    accounts = {role: str(uuid4()) for role in ('admin', 'quanly', 'letan', 'nhanvien', 'leader', 'giamdoc')}
    with database.begin() as conn:
        conn.execute(text('''CREATE TABLE vera_v2_user_profile (
            auth_user_id uuid PRIMARY KEY, employee_username text, role text, is_active bool);
            CREATE TABLE vera_app_setting(category text,setting_key text,value_json jsonb);
            CREATE TABLE vera_v2_leave_watch(auth_user_id uuid,watched_date date);
            CREATE TABLE vera_v2_push_subscription(subscription_id uuid PRIMARY KEY,
                auth_user_id uuid,endpoint text,p256dh text,auth_secret text,is_active bool);'''))
        delivery.ensure_schema(conn)
        for role, identifier in accounts.items():
            conn.execute(text('INSERT INTO vera_v2_user_profile VALUES(CAST(:id AS uuid),:name,:role,true)'),
                         {'id': identifier, 'name': role, 'role': role})
    identity = [Identity(auth_user_id=accounts['admin'])]
    app = FastAPI()
    settings.install_notification_settings_routes(app, engine_instance=lambda: database,
        current_identity=lambda: identity[0], identity_type=Identity)
    with TestClient(app) as client:
        yield accounts, identity, client


def subscribe(database, recipient):
    with database.begin() as conn:
        conn.execute(text('''INSERT INTO vera_v2_push_subscription
            VALUES(CAST(:id AS uuid),CAST(:recipient AS uuid),'https://push.example/test','key','auth',true)'''),
            {'id': str(uuid4()), 'recipient': recipient})


def dispatch(database):
    sent = []
    def send(item, *_):
        assert database.pool.checkedout() == 0, 'network send must run outside DB connections'
        sent.append(item['payload'])
        return True, 201, ''
    delivery.dispatch_pending(database, send, lambda *_: 'test-vapid')
    return sent


def test_native_notification_visible_without_device_and_shared_push_detail(database, notices):
    accounts, identity, client = notices
    with database.begin() as conn:
        assert delivery.enqueue(conn, 'admin_leave_changes', {'title': 'Nghỉ phép', 'body': 'Test', 'tag': 'leave-1'})
    rows = client.get('/v2/notification-inbox').json()['notifications']
    assert len(rows) == 1
    assert not any(key.startswith('_') for key in rows[0]['payload'])
    identity[0] = Identity(role='nhanvien', auth_user_id=accounts['nhanvien'])
    assert client.get('/v2/notification-inbox').json()['notifications'] == []
    assert client.get(f"/v2/notification-inbox/{rows[0]['id']}").status_code == 404
    subscribe(database, accounts['admin'])
    sent = dispatch(database)
    assert len(sent) == 1 and sent[0]['notification_id'] == str(rows[0]['id'])
    assert sent[0]['recipient_id'] == accounts['admin']
    assert not any(key.startswith('_') for key in sent[0])
    assert dispatch(database) == []


@pytest.mark.parametrize('channels', [['in_app'], ['push'], ['in_app', 'push']])
def test_configured_notice_has_one_inbox_row_and_read_covers_both_channels(database, notices, channels):
    accounts, _, client = notices
    with database.begin() as conn:
        conn.execute(text('''INSERT INTO vera_notification_route(key,source_key,label,recipients,channels,updated_by)
            VALUES('birthday','birthday','Test',CAST(:recipients AS jsonb),CAST(:channels AS jsonb),'test')'''),
            {'recipients': json.dumps([accounts['admin']]), 'channels': json.dumps(channels)})
        for _ in range(2):
            delivery.enqueue(conn, 'birthday', {'title': 'Sinh nhật', 'tag': 'one-event'})
    rows = client.get('/v2/notification-inbox').json()['notifications']
    assert len(rows) == 1
    subscribe(database, accounts['admin'])
    assert len(dispatch(database)) == 1
    assert client.post(f"/v2/notification-inbox/{rows[0]['id']}/read").status_code == 200
    assert client.get('/v2/notification-inbox').json()['notifications'] == []
    with database.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_notification_delivery WHERE read_at IS NOT NULL')).scalar_one() == 2


def test_device_off_keeps_inbox_and_other_users_devices(database, notices):
    accounts, identity, client = notices
    subscribe(database, accounts['admin'])
    subscribe(database, accounts['quanly'])
    with database.begin() as conn:
        delivery.enqueue(conn, 'live_tour_queue', {'title': 'Queue', 'event_id': 'queue-1'})
        conn.execute(text('DELETE FROM vera_v2_push_subscription WHERE auth_user_id=CAST(:id AS uuid)'), {'id': accounts['admin']})
    assert len(client.get('/v2/notification-inbox').json()['notifications']) == 1
    sent = dispatch(database)
    assert [row['recipient_id'] for row in sent] == [accounts['quanly']]
    identity[0] = Identity(role='nhanvien', auth_user_id=accounts['nhanvien'])
    assert client.get('/v2/notification-inbox').json()['notifications'] == []


@pytest.mark.parametrize('revoke', ['role', 'account', 'source', 'push_channel', 'override'])
def test_queued_delivery_rechecks_current_permissions(database, notices, revoke):
    accounts, _, client = notices
    subscribe(database, accounts['admin'])
    with database.begin() as conn:
        delivery.enqueue(conn, 'admin_leave_changes', {'title': 'Nghỉ phép', 'event_id': 'permission-test'})
        if revoke == 'role':
            conn.execute(text("UPDATE vera_v2_user_profile SET role='nhanvien' WHERE auth_user_id=CAST(:id AS uuid)"), {'id': accounts['admin']})
        elif revoke == 'account':
            conn.execute(text('UPDATE vera_v2_user_profile SET is_active=false'))
        elif revoke == 'source':
            conn.execute(text("INSERT INTO vera_v2_notification_setting(notification_key,enabled) VALUES('admin_leave_changes',false)"))
        elif revoke == 'push_channel':
            conn.execute(text("INSERT INTO vera_v2_notification_channel_setting(notification_key,channel,enabled,updated_by) VALUES('admin_leave_changes','push',false,'test')"))
        else:
            conn.execute(text("INSERT INTO vera_notification_route(key,source_key,label,recipients,channels,updated_by) VALUES('admin_leave_changes','admin_leave_changes','Test','[]','[\"push\"]','test')"))
    assert dispatch(database) == []
    rows = client.get('/v2/notification-inbox').json()['notifications']
    assert len(rows) == (1 if revoke == 'push_channel' else 0)


def test_training_and_employee_reminders_do_not_broadcast_to_other_staff(database, notices):
    accounts, identity, client = notices
    with database.begin() as conn:
        delivery.enqueue(conn, 'training_completed', {'title': 'Đào tạo', 'tag': 'training-1'}, default_usernames=['nhanvien'])
        delivery.enqueue(conn, 'attendance_break', {'title': 'Sắp hết giờ', 'kind': 'attendance-break-reminder', 'employee': 'nhanvien', 'tag': 'break-1'})
    assert client.get('/v2/notification-inbox').json()['notifications'] == []
    identity[0] = Identity(role='nhanvien', auth_user_id=accounts['nhanvien'])
    assert len(client.get('/v2/notification-inbox').json()['notifications']) == 2
    identity[0] = Identity(role='leader', auth_user_id=accounts['leader'])
    assert client.get('/v2/notification-inbox').json()['notifications'] == []


def test_failed_transaction_never_leaves_inbox_or_push_work(database, notices):
    _, _, client = notices
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            delivery.enqueue(conn, 'admin_leave_changes', {'title': 'Rollback', 'tag': 'abort'})
            raise RuntimeError('rollback')
    assert client.get('/v2/notification-inbox').json()['notifications'] == []
    assert dispatch(database) == []


@pytest.mark.parametrize('control', ['paused', 'deleted'])
def test_break_control_suppresses_queued_alert_but_delivers_clear(database, notices, control):
    accounts, identity, client = notices
    subscribe(database, accounts['nhanvien'])
    with database.begin() as conn:
        delivery.enqueue(conn, 'attendance_break', {'title': 'Nhắc nghỉ', 'kind': 'attendance-break-reminder', 'employee': 'nhanvien'}, 'break-event:reminder')
        category, key, value = ('attendance_break_alert_control','global',{'disabled': True}) if control == 'paused' else ('attendance_break_alert','break-event',{'globally_deleted_at': '2026-09-27'})
        conn.execute(text('INSERT INTO vera_app_setting VALUES(:category,:key,CAST(:value AS jsonb))'), {'category':category,'key':key,'value':json.dumps(value)})
    identity[0] = Identity(role='nhanvien', auth_user_id=accounts['nhanvien'])
    assert client.get('/v2/notification-inbox').json()['notifications'] == []
    assert dispatch(database) == []


def test_all_roles_receive_only_their_own_profile_notice(database, notices):
    accounts, identity, client = notices
    for role, account in accounts.items():
        with database.begin() as conn:
            delivery.enqueue(conn, 'profile_completion', {'title': 'Hồ sơ', 'tag': role}, default_accounts=[account])
        subscribe(database, account)
    for role, account in accounts.items():
        identity[0] = Identity(role=role, auth_user_id=account)
        rows = client.get('/v2/notification-inbox').json()['notifications']
        assert len(rows) == 1 and rows[0]['payload']['tag'] == role
    assert {item['recipient_id'] for item in dispatch(database)} == set(accounts.values())


def test_watch_removal_and_old_quota_suppress_existing_native_rows(database, notices):
    accounts, identity, client = notices
    account = accounts['admin']
    subscribe(database, account)
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_v2_leave_watch VALUES(CAST(:id AS uuid), CURRENT_DATE)"), {'id':account})
        day = conn.execute(text('SELECT CURRENT_DATE::text')).scalar_one()
        delivery.enqueue(conn, 'leave_watch', {'title':'Lịch nghỉ','watched_date':day,'tag':'watched-day'})
        delivery.enqueue(conn, 'leave_quota_exceeded', {'title':'Hạn mức','quota_month':delivery.current_month(),'tag':'quota'})
        conn.execute(text('DELETE FROM vera_v2_leave_watch'))
        conn.execute(text("UPDATE vera_notification_delivery SET payload=jsonb_set(payload,'{quota_month}','\"2000-01\"') WHERE rule_key='native:leave_quota_exceeded'"))
    assert client.get('/v2/notification-inbox').json()['notifications'] == []
    assert dispatch(database) == []


@pytest.mark.parametrize('route', [None, ['group:all'], ['group:letan']])
@pytest.mark.parametrize('source', ['auto_penalty', 'missing_checkin_absence'])
def test_auto_penalty_private_audience_and_old_broad_deliveries(database, notices, route, source):
    accounts, identity, client = notices
    allowed = {'admin', 'quanly', 'nhanvien'}
    accounts['other'] = str(uuid4())
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_v2_user_profile VALUES(CAST(:id AS uuid),'other','nhanvien',true)"), {'id':accounts['other']})
    for identifier in accounts.values():
        subscribe(database, identifier)
    with database.begin() as conn:
        if route is not None:
            conn.execute(text("""INSERT INTO vera_notification_route(key,source_key,label,recipients,channels,updated_by)
                VALUES(:source,:source,'Test',CAST(:recipients AS jsonb),'["in_app","push"]','test')"""),
                {'recipients':json.dumps(route),'source':source})
        delivery.enqueue(conn, source, {'employee':'nhanvien', 'tag':'private-penalty', 'body':'private'})
        rows = list(conn.execute(text('SELECT * FROM vera_notification_delivery')).mappings())
        assert {row['recipient'] for row in rows} == {accounts[role] for role in allowed}
        template = rows[0]
        # Simulate old deliveries from a previously broad route; every read/send rechecks policy.
        for role in set(accounts) - allowed:
            conn.execute(text("""INSERT INTO vera_notification_delivery(event_key,rule_key,recipient,channel,payload)
                VALUES('private-penalty',:rule,:recipient,'push',CAST(:payload AS jsonb))"""),
                {'rule':template['rule_key'], 'recipient':accounts[role], 'payload':json.dumps(template['payload'])})
    if route == ['group:letan']:
        # Reclassifying the route cannot expose its old private penalty content.
        with database.begin() as conn:
            conn.execute(text("UPDATE vera_notification_route SET source_key='birthday',recipients='[\"group:all\"]' WHERE key=:source"), {'source':source})
    for role, identifier in accounts.items():
        identity[0] = Identity(role=role, auth_user_id=identifier)
        rows = client.get('/v2/notification-inbox').json()['notifications']
        assert bool(rows) == (role in allowed)
        with database.connect() as conn:
            nid = conn.execute(text("SELECT id FROM vera_notification_delivery WHERE recipient=:id AND channel='push'"), {'id':identifier}).scalar_one()
        assert client.get(f'/v2/notification-inbox/{nid}').status_code == (200 if role in allowed else 404)
    sent = dispatch(database)
    assert {row['recipient_id'] for row in sent} == {accounts[role] for role in allowed}

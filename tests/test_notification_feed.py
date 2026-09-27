from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_web_v2_notification_settings as settings
from test_notification_routing import Identity, Result


def test_combined_feed_reuses_one_connection_and_keeps_recipient_channel_filters(monkeypatch):
    identity = Identity(role='letan')
    calls, connections = [], []
    class Engine:
        @contextmanager
        def begin(self):
            connections.append(self)
            yield self
        def execute(self, statement, params=None):
            sql = str(statement)
            calls.append((sql, params))
            if sql.lstrip().startswith('SELECT'):
                assert params['recipient'] == identity.auth_user_id
                assert 'p.is_active' in sql and 'COALESCE(s.enabled,TRUE)' in sql
                assert 'COALESCE(cs.enabled,TRUE)' in sql and 'd.read_at IS NULL' in sql
                assert 'vera_notification_group' in sql
                return Result([{'id':1 if "DISTINCT ON" in sql else 2, 'payload':{'title':'Test'}}])
            return Result()
    def config(conn, admin=False):
        assert conn is connections[0] and not admin
        return {'settings':[{'key':'birthday','enabled':True}],'revision':4}
    monkeypatch.setattr(settings,'_response',config)
    app = FastAPI()
    settings.install_notification_settings_routes(app, engine_instance=Engine,
        current_identity=lambda:identity, identity_type=Identity)
    response = TestClient(app).get('/v2/notification-feed')
    assert response.status_code == 200, response.text
    assert len(connections) == 1
    assert response.json()['inbox'][0]['id'] == 1
    assert response.json()['popup'][0]['id'] == 2
    assert len(calls) == 3
    assert 'recipients' not in response.json()


def test_current_missing_checkins_reuse_feed_connection_and_limit_management_roles(monkeypatch):
    import vera_missing_checkin_notifications as absence
    calls = []
    conn = object()
    monkeypatch.setattr(absence,'current_missing_checkins',lambda connection,ident,now,include_expiry: calls.append((connection,ident.role,include_expiry)) or [{'employee':'worker'}])
    config = {'settings':[{'key':'missing_checkin','enabled':True,'channel_enabled':{'popup':True}}]}
    for role in ['admin','letan','quanly']:
        assert settings._missing_checkin_rows(conn,Identity(role=role),config)==[{'employee':'worker'}]
    assert calls==[(conn,role,True) for role in ['admin','letan','quanly']]
    for role in ['nhanvien','leader','giamdoc','']:
        assert settings._missing_checkin_rows(conn,Identity(role=role),config)==[]
    config['settings'][0]['channel_enabled']['popup']=False
    assert settings._missing_checkin_rows(conn,Identity(),config)==[]
    config['settings'][0].update(enabled=False,channel_enabled={'popup':True})
    assert settings._missing_checkin_rows(conn,Identity(),config)==[]
    assert len(calls)==3

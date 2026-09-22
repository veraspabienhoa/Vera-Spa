import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy import text

import vera_notification_delivery as delivery
import vera_notification_tasks as tasks
import vera_web_v2_notification_settings as settings


class Identity(BaseModel):
    role: str = 'admin'
    auth_user_id: str = '00000000-0000-0000-0000-000000000001'
    employee_username: str = 'tester'
    full_name: str = 'Tester'


class Result:
    def __init__(self, rows=(), scalar=None): self.rows=list(rows); self.scalar_value=scalar
    def mappings(self): return self
    def __iter__(self): return iter(self.rows)
    def one(self): return self.rows[0]
    def scalar_one_or_none(self): return self.scalar_value


@pytest.mark.parametrize('method,path,body', [
    ('put','/v2/notification-settings/birthday', {'enabled':True}),
    ('put','/v2/notification-settings/order', {'keys':[],'revision':0}),
    ('post','/v2/notification-settings', {'label':'Test','source_key':'birthday','recipients':['x'],'channels':['in_app'],'revision':0}),
    ('get','/v2/notification-settings/tasks',None),
])
def test_non_admin_cannot_manage_notifications_or_list_accounts(method,path,body):
    app=FastAPI()
    def forbidden(): raise AssertionError('must deny before opening database')
    settings.install_notification_settings_routes(app,engine_instance=forbidden,current_identity=lambda:Identity(role='letan'),identity_type=Identity)
    response=TestClient(app).request(method,path,json=body)
    assert response.status_code==403,response.text


def test_route_creation_rejects_unconnected_task_before_database():
    app=FastAPI()
    settings.install_notification_settings_routes(app,engine_instance=lambda:None,current_identity=Identity,identity_type=Identity)
    response=TestClient(app).post('/v2/notification-settings',json={'label':'Test','source_key':'fake_task','recipients':['x'],'channels':['push'],'revision':0})
    assert response.status_code==400


def test_catalog_is_installed_mutations_only_and_emits_only_success(monkeypatch):
    app=FastAPI()
    @app.post('/v2/training/session')
    def save(): return {'ok':True}
    @app.post('/v2/training/fail')
    def fail(): return {'ok':False}
    @app.post('/v2/training/duplicate')
    def duplicate(): return {'ok':True,'duplicate':True}
    @app.get('/v2/training/read')
    def read(): return {'ok':True}
    @app.post('/v2/auth/login')
    def login(): return {'ok':True}
    seen=[]
    monkeypatch.setattr(tasks,'route_event',lambda engine,key,payload:seen.append((key,payload)))
    app.add_middleware(tasks.TaskNotificationMiddleware,owner=app,engine_instance=lambda:object())
    catalog=tasks.task_catalog(app)
    assert len(catalog)==3
    client=TestClient(app)
    for path in ('session','fail','duplicate'): client.post('/v2/training/'+path,json={'password':'never-copy','customer':'private'})
    client.get('/v2/training/read');client.post('/v2/auth/login')
    assert len(seen)==1
    assert seen[0][0]==tasks.task_key('POST','/v2/training/session')
    assert 'never-copy' not in json.dumps(seen) and 'private' not in json.dumps(seen)


def test_enqueue_fans_out_exact_recipients_and_channels_and_keeps_plain_text(monkeypatch):
    monkeypatch.setattr(delivery,'ensure_schema',lambda conn:None)
    rules=[{'key':'birthday','source_key':'birthday','custom':False,'enabled':True,
            'recipients':['a','b','a'],'channels':['in_app','push']},
           {'key':'custom-disabled','custom':True,'enabled':False,'recipients':['c'],'channels':['push']}]
    writes=[]
    class Conn:
        def execute(self,statement,params=None):
            if 'SELECT r.*' in str(statement): return Result(rules)
            writes.append((str(statement),params));return Result()
    assert delivery.enqueue(Conn(),'birthday',{'title':'<script>raw text</script>','body':'Body','url':'https://evil.invalid','tag':'birthday-1'})
    assert {(p['recipient'],p['channel']) for _,p in writes}=={('a','push'),('a','in_app'),('b','push'),('b','in_app')}
    assert len(writes)==4
    for query,params in writes:
        assert 'ON CONFLICT DO NOTHING' in query
        assert json.loads(params['payload'])['url']==delivery.APP_URL
    # Repeated source deliveries carry the same event identity, irrespective of countdown/body changes.
    assert delivery.fingerprint('birthday',{'tag':'same','body':'1'})==delivery.fingerprint('birthday',{'tag':'same','body':'2'})


def test_stale_revision_and_inactive_recipient_rejected(monkeypatch):
    monkeypatch.setattr(settings,'ensure_schema',lambda conn:None)
    monkeypatch.setattr(settings,'ensure_routing_schema',lambda conn:None)
    conn=SimpleNamespace(execute=lambda *_:Result([{'revision':5,'ordering':[]}]))
    with pytest.raises(settings.HTTPException) as exc:settings._lock_config(conn,4)
    assert exc.value.status_code==409
    conn=SimpleNamespace(execute=lambda *_:Result([{'id':'active'}]))
    with pytest.raises(settings.HTTPException):settings._recipients(conn,['inactive'])
    with pytest.raises(settings.HTTPException):settings._recipients(conn,[])
    assert settings._recipients(conn,['active','active'])==['active']
    with pytest.raises(ValidationError):settings.NotificationCreate(label=' ',source_key='birthday',recipients=['a'],channels=['in_app'],revision=0)
    with pytest.raises(ValidationError):settings.NotificationCreate(label='ok',source_key='birthday',recipients=['a'],channels=['telegram'],revision=0)


def test_push_network_outside_connections_and_partial_success_checkpointed(monkeypatch):
    monkeypatch.setattr(delivery,'ensure_schema',lambda conn:None)
    row={'id':7,'rule_key':'birthday','recipient':'a','payload':{'title':'Hi'},'sent_subscriptions':['old']}
    queries=[]
    class Engine:
        active=0
        @contextmanager
        def begin(self):
            self.active+=1
            try:yield self
            finally:self.active-=1
        connect=begin
        def execute(self,query,params=None):
            query=str(query);queries.append((query,params))
            if 'WITH pending' in query:return Result([row])
            if 'SELECT 1 FROM vera_notification_route' in query:return Result(scalar=1)
            if 'SELECT subscription_id' in query:return Result([{'subscription_id':sid} for sid in ('old','new','bad')])
            return Result()
    engine=Engine();sent=[]
    def send(sub,*_):
        assert engine.active==0
        sent.append(sub['subscription_id'])
        return (sub['subscription_id']=='new',503,'error')
    delivery.dispatch_pending(engine,send,lambda *_:'configured')
    assert sent==['new','bad']
    checkpoints=[json.loads(p['ids']) for q,p in queries if 'SET sent_subscriptions' in q]
    assert checkpoints[-1]==['new','old']
    final=[p for q,p in queries if 'last_error=:error' in q][-1]
    assert final['complete'] is False


def test_inbox_read_update_always_scoped_to_authenticated_user(monkeypatch):
    queries=[]
    class Engine:
        @contextmanager
        def begin(self):yield self
        def execute(self,q,p=None):queries.append((str(q),p));return Result()
    app=FastAPI()
    settings.install_notification_settings_routes(app,engine_instance=Engine,current_identity=Identity,identity_type=Identity)
    response=TestClient(app).post('/v2/notification-inbox/42/read')
    assert response.status_code==200
    assert queries[-1][1]['recipient']==Identity().auth_user_id
    assert 'recipient=:recipient' in queries[-1][0]

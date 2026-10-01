import hashlib
import json
import os
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text

import vera_web_v2_facegate_enrollment as routes
from vera_web_v2_face_id import ensure_table
from vera_facegate_enrollment import UploadRejected
from test_facegate_enrollment import REF


@pytest.fixture
def setup(monkeypatch):
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url: pytest.skip('Real PostgreSQL required')
    schema = 'enrollment_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn: conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url,pool_size=1,max_overflow=0,pool_timeout=.1,
                           connect_args={'options':f'-csearch_path={schema}'})
    out=BytesIO(); Image.new('RGB',(120,160),'blue').save(out,'PNG'); image=out.getvalue()
    sha=hashlib.sha256(image).hexdigest()
    monkeypatch.setenv('VERA_FACEGATE_DEVICE_ID','test-device')
    with engine.begin() as conn:
        conn.execute(text('''CREATE TABLE employees(username text PRIMARY KEY,full_name text,role text,payload jsonb DEFAULT '{}'::jsonb)'''))
        conn.execute(text("INSERT INTO employees(username,full_name,role) VALUES ('worker','Test Staff','nhanvien'),('other','Other Staff','nhanvien')"))
        conn.execute(text('''CREATE TABLE vera_app_setting(category text,setting_key text,value_json jsonb,source text,updated_by text,
            revision integer,created_at timestamptz,updated_at timestamptz,PRIMARY KEY(category,setting_key))'''))
        conn.execute(text("INSERT INTO vera_app_setting(category,setting_key,value_json,revision) VALUES ('devices','registry',CAST(:v AS jsonb),1)"),
                     {'v':json.dumps({'devices':[{'id':'facegate-current','enabled':True,'adapter':'facegate_server','address':'192.168.1.34'}]})})
        ensure_table(conn)
        conn.execute(text("""INSERT INTO vera_employee_face_id VALUES ('worker',:image,'image/png',:size,:sha,'admin',NOW())"""),
                     {'image':image,'size':len(image),'sha':sha})
    calls=[]; mode={'value':'ok'}
    class Client:
        def __init__(self): self._call('init')
        def _call(self,name):
            assert engine.pool.checkedout() == 0, 'network I/O inside database transaction'
            calls.append(name)
        def login(self): self._call('login')
        def profiles(self):
            self._call('profiles')
            return [{'uname':'Test Staff'}] if mode['value']=='existing' else []
        def door_defaults(self): self._call('defaults'); return (1,0)
        def upload(self, photo, session):
            self._call('upload')
            with engine.connect() as conn:
                assert conn.execute(text('SELECT stage FROM vera_facegate_enrollment')).scalar()=='uploading'
            if mode['value']=='upload_timeout': raise TimeoutError('secret must not be disclosed')
            if mode['value']=='no_face': raise UploadRejected('upload_105','Không có khuôn mặt.')
            return REF
        def add(self,name,token,ref,defaults):
            self._call('add')
            with engine.connect() as conn:
                assert conn.execute(text('SELECT stage FROM vera_facegate_enrollment')).scalar()=='committing'
            if mode['value']=='commit_timeout': raise TimeoutError('secret must not be disclosed')
        def verify(self,name,token,ref):
            self._call('verify')
            if mode['value']=='verify_fail': raise ValueError('secret device payload')
            if mode['value']=='mapping_conflict':
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO vera_app_setting(category,setting_key,value_json,revision) VALUES ('facegate','mapping_test-device',CAST(:v AS jsonb),1)"),
                        {'v':json.dumps([{'username':'other','profile_id':123,'registration_ref':REF}])})
            return {'profile_id':123,'device_name':name,'registration_ref':ref}
        def close(self): self._call('close')
    monkeypatch.setattr(routes,'FaceGateEnrollmentClient',Client)
    grants={'employee_face_id_manage','device_facegate_mapping_manage'}
    def require(conn,ident,feature):
        if feature not in grants: raise HTTPException(403,'denied')
    app=FastAPI()
    class Identity: employee_username='admin'
    routes.install_enrollment_routes(app,engine_instance=lambda:engine,current_identity=lambda:Identity(),require_feature=require,identity_type=Identity)
    try: yield SimpleNamespace(engine=engine,api=TestClient(app),calls=calls,mode=mode,grants=grants,sha=sha)
    finally:
        engine.dispose()
        with admin.begin() as conn: conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


PATH='/v2/staff/worker/face-id/enrollment'

def send(s, sha=None): return s.api.post(PATH,json={'photo_sha256':sha or s.sha,'confirmed':True})

def state(s):
    with s.engine.connect() as conn:
        return conn.execute(text('SELECT status FROM vera_facegate_enrollment ORDER BY created_at DESC LIMIT 1')).scalar()


def test_success_atomic_mapping_and_idempotent_replay(setup):
    s=setup
    response=send(s)
    assert response.status_code==200,response.text
    assert response.json()['status']=='verified'
    with s.engine.connect() as conn:
        rows=routes.mappings(conn,'test-device')
        assert len(rows)==1 and rows[0]['username']=='worker' and rows[0]['registration_ref']==REF
        assert rows[0]['employee_code']==''
    assert send(s).json()['operation_id']==response.json()['operation_id']
    assert s.calls.count('upload')==s.calls.count('add')==1
    assert send(s,'0'*64).status_code==409
    assert s.api.get(PATH).json()['status']=='verified'


@pytest.mark.parametrize('feature',['employee_face_id_manage','device_facegate_mapping_manage'])
def test_requires_both_grants_before_device_io(setup,feature):
    s=setup;s.grants.remove(feature)
    assert send(s).status_code==403
    assert s.api.get(PATH).status_code==403
    assert s.api.post(PATH+'/verify').status_code==403
    assert not s.calls


def test_stale_photo_and_unconfirmed_never_call_device(setup):
    s=setup
    assert send(s,'0'*64).status_code==409
    assert s.api.post(PATH,json={'photo_sha256':s.sha,'confirmed':False}).status_code==400
    assert not s.calls


@pytest.mark.parametrize('mode',['upload_timeout','commit_timeout','verify_fail'])
def test_ambiguous_outcome_is_durable_and_not_replayed(setup,mode):
    s=setup;s.mode['value']=mode
    result=send(s)
    assert result.status_code==502 and 'secret' not in result.text
    assert state(s)=='unverified'
    before=list(s.calls)
    assert send(s).json()['status']=='unverified'
    assert s.calls==before
    other=s.api.post(PATH.replace('worker','other'),json={'photo_sha256':s.sha,'confirmed':True})
    assert other.status_code==409 and s.calls==before
    s.mode['value']='ok'
    if mode=='upload_timeout':
        assert s.api.post(PATH+'/verify').json()['status']=='rejected'
        assert state(s)=='rejected'
        assert s.calls.count('upload')==1 and 'add' not in s.calls
    else:
        assert s.api.post(PATH+'/verify').json()['status']=='verified'
        assert s.calls.count('upload')==s.calls.count('add')==1


@pytest.mark.parametrize('mode',['existing','no_face'])
def test_known_rejection_does_not_add_or_map(setup,mode):
    s=setup;s.mode['value']=mode
    assert send(s).status_code==409 and state(s)=='rejected'
    assert 'add' not in s.calls
    with s.engine.connect() as conn: assert routes.mappings(conn,'test-device')==[]


def test_mapping_conflict_never_overwrites_owner(setup):
    s=setup;s.mode['value']='mapping_conflict'
    assert send(s).status_code==502 and state(s)=='unverified'
    with s.engine.connect() as conn:
        assert routes.mappings(conn,'test-device')[0]['username']=='other'


def test_disabled_or_public_device_never_contacts_network(setup):
    s=setup
    for device in [{'id':'facegate-current','enabled':False,'address':'192.168.1.34','adapter':'facegate_server'},
                   {'id':'facegate-current','enabled':True,'address':'1.1.1.1','adapter':'facegate_server'}]:
        with s.engine.begin() as conn:
            conn.execute(text("UPDATE vera_app_setting SET value_json=CAST(:v AS jsonb) WHERE category='devices'"),{'v':json.dumps({'devices':[device]})})
        assert send(s).status_code==409
    assert not s.calls


def test_other_employee_can_find_and_verify_device_blocker(setup):
    s=setup;s.mode['value']='commit_timeout'
    assert send(s).status_code==502
    status=s.api.get(PATH.replace('worker','other')).json()
    assert status['status']=='not_registered'
    assert status['device_pending']['employee_username']=='worker'
    assert not status['can_enroll']
    s.mode['value']='ok'
    assert s.api.post(PATH+'/verify').json()['status']=='verified'
    assert s.api.get(PATH.replace('worker','other')).json()['device_pending'] is None
    assert s.calls.count('upload')==s.calls.count('add')==1


def test_failed_read_keeps_precommit_reservation_and_journal(setup,monkeypatch):
    s=setup;s.mode['value']='upload_timeout'
    assert send(s).status_code==502
    def fail(self):raise ValueError('private device data')
    monkeypatch.setattr(routes.FaceGateEnrollmentClient,'profiles',fail)
    result=s.api.post(PATH+'/verify')
    assert result.status_code==502 and 'private' not in result.text
    assert state(s)=='unverified'
    assert s.api.get(PATH.replace('worker','other')).json()['device_pending']['employee_username']=='worker'
    assert s.calls.count('upload')==1 and 'add' not in s.calls


def test_precommit_collision_keeps_reservation(setup,monkeypatch):
    s=setup;s.mode['value']='upload_timeout'
    assert send(s).status_code==502
    with s.engine.connect() as conn:
        op=conn.execute(text('SELECT operation_id FROM vera_facegate_enrollment')).scalar()
    monkeypatch.setattr(routes.FaceGateEnrollmentClient,'profiles',lambda self:[{'utext':'vera:'+op}])
    assert s.api.post(PATH+'/verify').status_code==409
    assert state(s)=='unverified'

@pytest.mark.parametrize('stage',['preflight','uploading','uploaded','committing'])
def test_interrupted_running_operations_recover_at_every_checkpoint(setup,stage):
    s=setup;s.mode['value']='upload_timeout'
    assert send(s).status_code==502
    with s.engine.begin() as conn:
        conn.execute(text("UPDATE vera_facegate_enrollment SET status='running',stage=:stage,registration_ref=CAST(:ref AS jsonb),updated_at=NOW()-interval '4 minutes'"),
                     {'stage':stage,'ref':json.dumps(REF) if stage in {'uploaded','committing'} else None})
    assert s.api.get(PATH).json()['stale']
    s.mode['value']='ok'
    response=s.api.post(PATH+'/verify')
    assert response.status_code==200,response.text
    assert response.json()['status']==('verified' if stage=='committing' else 'rejected')
    assert s.calls.count('upload')==1 and 'add' not in s.calls


def test_active_writer_is_not_recovered_and_deleted_employee_precommit_can_close(setup):
    s=setup;s.mode['value']='upload_timeout'
    assert send(s).status_code==502
    with s.engine.begin() as conn:
        conn.execute(text("UPDATE vera_facegate_enrollment SET status='running',updated_at=NOW()"))
    before=list(s.calls)
    assert s.api.post(PATH+'/verify').status_code==409
    assert s.calls==before
    with s.engine.begin() as conn:
        conn.execute(text("UPDATE vera_facegate_enrollment SET status='unverified'"))
        conn.execute(text("UPDATE employees SET payload=CAST(:payload AS jsonb) WHERE username='worker'"), {'payload':json.dumps({'__deleted':True})})
    assert s.api.post(PATH+'/verify').json()['status']=='rejected'
    assert s.api.get(PATH.replace('worker','other')).json()['device_pending'] is None


def test_old_writer_cannot_resurrect_a_recovered_reservation_or_add_profile(setup,monkeypatch):
    s=setup
    original=routes.FaceGateEnrollmentClient.upload
    def interrupted(self,photo,session):
        ref=original(self,photo,session)
        with s.engine.begin() as conn:
            conn.execute(text("UPDATE vera_facegate_enrollment SET updated_at=NOW()-interval '4 minutes'"))
        assert s.api.post(PATH+'/verify').json()['status']=='rejected'
        return ref
    monkeypatch.setattr(routes.FaceGateEnrollmentClient,'upload',interrupted)
    assert send(s).status_code==502
    assert state(s)=='rejected'
    assert s.calls.count('upload')==1 and 'add' not in s.calls

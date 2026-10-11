"""Bind two operator-confirmed scans to their one unowned device profile.

No photo upload or raw attendance modification. Canonical name worker performs
and verifies the device rename after the mapping transaction has committed.
"""
import json
from datetime import datetime, timezone
from sqlalchemy import text
from vera_facegate_cutover import runtime_engine, verify_runtime
from vera_facegate_control_log import facegate_endpoint, mapping_device_id, registration_ref, VN_TZ
from vera_facegate_enrollment import FaceGateEnrollmentClient
from vera_web_v2_facegate_enrollment import target, mappings
from vera_employee_facegate_delete import deletion_pending
from vera_employee_rename_sync import queue_device_rename, sync_device_names
from vera_auto_check import _norm
from vera_facegate_readiness import reference

OWNER = 'Cậu Tưởng'
EVENTS = {'80905': '2026-10-10T08:26:40+07:00', '81064': '2026-10-11T08:22:43+07:00'}
RELEASE = '8aa549d5ad56be2ea40cabe7fe34c47f0d32108d'

def event_snapshot(conn, device):
    rows = conn.execute(text("SELECT event_id,occurred_at,payload_json,payload_sha256 FROM vera_facegate_event WHERE device_id=:device AND event_id IN ('80905','81064') ORDER BY event_id"), {'device':device}).mappings().all()
    if len(rows) != 2:
        raise ValueError('event_count')
    refs = []
    for row in rows:
        at = row['occurred_at']
        at = datetime.fromisoformat(at) if isinstance(at,str) else at
        if at.astimezone(VN_TZ).isoformat() != EVENTS[str(row['event_id'])]:
            raise ValueError('event_time')
        payload = row['payload_json']
        payload = json.loads(payload) if isinstance(payload,str) else payload
        refs.append(reference(payload.get('registration_ref')))
    if not all(refs) or len(set(refs)) != 1:
        raise ValueError('event_references')
    return rows, refs[0]

def main():
    verify_runtime(RELEASE)
    engine=runtime_engine();client=None
    try:
        with engine.begin() as conn:
            people=conn.execute(text("SELECT username,full_name,role FROM employees WHERE COALESCE(payload->>'__deleted','false')<>'true'")).mappings().all()
            owners=[p for p in people if _norm(p['username'])==_norm(OWNER) or _norm(p['full_name'])==_norm(OWNER)]
            actors=[p for p in people if p['role']=='admin' and _norm(p['username'])=='admin']
            if len(owners)!=1 or len(actors)!=1 or owners[0]['role'] in {'admin','giamdoc','quanly','support'}:
                raise ValueError('directory_identity')
            username,actor=owners[0]['username'],actors[0]['username']
            address,device=target(conn),mapping_device_id()
            snapshot,ref=event_snapshot(conn,device)
        with facegate_endpoint('http://'+address):
            client=FaceGateEnrollmentClient();client.login()
            profiles=[p for p in client.profiles() if reference(registration_ref(p))==ref]
            if len(profiles)!=1:
                raise ValueError('profile_count')
            listed=profiles[0];uid=int(listed['uid']);detail=client.profile_details(uid)
            if (registration_ref(detail)!=registration_ref(listed) or detail.get('uname')!=listed.get('uname')
                or detail.get('utext')!=listed.get('utext')
                or _norm(detail.get('uname')).replace('_',' ') not in {'nhan vien',_norm(username)}):
                raise ValueError('profile_identity')
            profile={'profile_id':uid,'device_name':detail['uname'],'registration_ref':registration_ref(detail)}
        with engine.begin() as conn:
            conn.execute(text('SELECT pg_advisory_xact_lock(723491, 1)'))
            if target(conn)!=address or mapping_device_id()!=device or deletion_pending(conn):
                raise ValueError('device_changed_or_deleting')
            current=conn.execute(text("SELECT username,full_name,role FROM employees WHERE username=:name AND COALESCE(payload->>'__deleted','false')<>'true' FOR UPDATE"),{'name':username}).mappings().one()
            if dict(current)!=dict(owners[0]) or event_snapshot(conn,device)[0]!=snapshot:
                raise ValueError('evidence_changed')
            key='mapping_'+device
            conn.execute(text("INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at) VALUES ('facegate',:key,'[]'::jsonb,'web_v2',:actor,1,NOW(),NOW()) ON CONFLICT(category,setting_key) DO NOTHING"),{'key':key,'actor':actor})
            entries=mappings(conn,device,lock=True)
            relevant=[m for m in entries if m.get('username')==username or str(m.get('profile_id'))==str(uid) or reference(m.get('registration_ref'))==ref]
            if relevant:
                if len(relevant)!=1 or relevant[0].get('username')!=username or str(relevant[0].get('profile_id'))!=str(uid) or reference(relevant[0].get('registration_ref'))!=ref or relevant[0].get('device_address')!=address or not relevant[0].get('confirmed_by'):
                    raise ValueError('mapping_conflict')
            else:
                if len(entries)>=200:
                    raise ValueError('mapping_limit')
                entries.append({**profile,'username':username,'employee_code':'','device_address':address,'confirmed_by':actor,'confirmed_at':datetime.now(timezone.utc).isoformat(),'operator_confirmed_events':sorted(EVENTS),'identity_review':'operator-confirmed-owner-oct10-11'})
                conn.execute(text("UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb),updated_by=:actor,updated_at=NOW(),revision=revision+1 WHERE category='facegate' AND setting_key=:key"),{'key':key,'actor':actor,'value':json.dumps(entries,ensure_ascii=False)})
            owned=[m for m in entries if m.get('username')==username][0]
            if owned.get('device_name')!=username:
                pending=conn.execute(text("SELECT to_regclass('vera_facegate_rename_job')")).scalar()
                pending=pending and conn.execute(text("SELECT 1 FROM vera_facegate_rename_job WHERE employee_username=:name AND status='pending'"),{'name':username}).scalar()
                if not pending:
                    queue_device_rename(conn,username,username)
        result=sync_device_names(engine,username)
        with facegate_endpoint('http://'+address):
            actual=client.profile_details(uid)
            if actual.get('uname')!=username or registration_ref(actual)!=profile['registration_ref'] or actual.get('utext')!=detail.get('utext'):
                raise ValueError('rename_not_verified')
        with engine.begin() as conn:
            owned=[m for m in mappings(conn,device) if m.get('username')==username]
            if len(owned)!=1 or owned[0].get('device_name')!=username or reference(owned[0].get('registration_ref'))!=ref or result['status']!='verified':
                raise ValueError('mapping_not_verified')
        print(json.dumps({'ok':True,'owner_mapping_verified':True,'device_name_verified':True,'photo_reference_preserved':True,'device_token_preserved':True,'raw_events_modified':False,'confirmed_event_count':2}))
    finally:
        if client:client.close()
        engine.dispose()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__,'error_code':str(exc) if isinstance(exc,ValueError) and str(exc) in {'event_count','event_time','event_references','directory_identity','profile_count','profile_identity','device_changed_or_deleting','evidence_changed','mapping_conflict','mapping_limit','rename_not_verified','mapping_not_verified'} else 'operation_failed','writes_may_have_committed':True}))
        raise SystemExit(1)

"""Read-only checks for an operator-confirmed owner; output counts/booleans only."""
import json
from sqlalchemy import text
from vera_facegate_cutover import runtime_engine, verify_runtime
from vera_facegate_control_log import facegate_endpoint, mapping_device_id, registration_ref
from vera_facegate_enrollment import FaceGateEnrollmentClient
from vera_web_v2_facegate_enrollment import target, mappings
from vera_auto_check import _norm
from vera_facegate_readiness import reference

OWNER = 'Cậu Tưởng'  # Owner explicitly identified both scans in this operation.
EVENTS = ('80905','81064')


def main():
    verify_runtime('8aa549d5ad56be2ea40cabe7fe34c47f0d32108d')
    engine = runtime_engine(readonly=True)
    client = None
    try:
        with engine.begin() as conn:
            people = conn.execute(text("SELECT username,full_name,role FROM employees WHERE COALESCE(payload->>'__deleted','false')<>'true'")).mappings().all()
            owners = [p for p in people if _norm(p['username'])==_norm(OWNER) or _norm(p['full_name'])==_norm(OWNER)]
            if len(owners)!=1:
                raise ValueError('owner_not_unique')
            username = owners[0]['username']
            address, device = target(conn), mapping_device_id()
            entries = mappings(conn,device)
            owned = [m for m in entries if m.get('username')==username]
            events = conn.execute(text("SELECT event_id,occurred_at,payload_json,payload_sha256 FROM vera_facegate_event WHERE device_id=:device AND event_id IN ('80905','81064')"),{'device':device}).mappings().all()
            available = conn.execute(text("SELECT to_regclass('vera_facegate_enrollment')")).scalar()
            jobs = conn.execute(text('SELECT status,stage,profile_id,registration_ref,photo_sha256 FROM vera_facegate_enrollment WHERE employee_username=:name ORDER BY created_at DESC'),{'name':username}).mappings().all() if available else []
            photo = conn.execute(text('SELECT sha256 FROM vera_employee_face_id WHERE employee_username=:name'),{'name':username}).scalar()
        refs=[]
        for event in events:
            payload=event['payload_json']
            payload=json.loads(payload) if isinstance(payload,str) else payload
            refs.append(reference(payload.get('registration_ref')))
        with facegate_endpoint('http://'+address):
            client=FaceGateEnrollmentClient()
            client.login()
            profiles=client.profiles()
            generic=[p for p in profiles if _norm(p.get('uname')).replace('_',' ') in {'nhan vien'}]
            matching=[p for p in profiles if reference(registration_ref(p)) in {r for r in refs if r}]
            matching_owner=[p for p in profiles if _norm(p.get('uname'))==_norm(username)]
            details=[client.profile_details(int(p['uid'])) for p in matching]
        print(json.dumps({'ok':True,'database_writes':False,'device_writes':False,
                          'confirmed_owner_count':len(owners),'event_count':len(events),
                          'valid_event_reference_count':sum(bool(r) for r in refs),
                          'distinct_event_references':len(set(r for r in refs if r)),
                          'owner_mapping_count':len(owned),'owner_photo_saved':bool(photo),
                          'owner_enrollment_status_counts':{s:sum(j['status']==s for j in jobs) for s in {j['status'] for j in jobs}},
                          'generic_device_profile_count':len(generic),'event_matching_profile_count':len(matching),
                          'owner_named_profile_count':len(matching_owner),
                          'matching_profile_detail_refs_agree':all(reference(registration_ref(a))==reference(registration_ref(b)) for a,b in zip(matching,details)),
                          'matching_profile_owned_elsewhere':any(m.get('username')!=username and (str(m.get('profile_id')) in {str(p['uid']) for p in matching} or reference(m.get('registration_ref')) in set(r for r in refs if r)) for m in entries)},sort_keys=True))
    finally:
        if client: client.close()
        engine.dispose()


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__,'database_writes':False,'device_writes':False}))
        raise SystemExit(1)

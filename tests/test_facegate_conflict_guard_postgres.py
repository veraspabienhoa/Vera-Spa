"""Persisted drift must not disappear behind the immutable event primary key."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json

import pytest
from sqlalchemy import text

import vera_facegate_attendance as fg
import vera_facegate_runtime as runtime
import vera_facegate_sync as sync
from vera_facegate_control_log import VN_TZ
from test_facegate_attendance_postgres import database, seed_preview, batch, DAY


def test_persisted_conflict_blocks_every_employee_without_overwriting_evidence(database):
    seed_preview(database)
    changed = deepcopy(batch(1))
    payload = json.loads(changed[0]['payload_json']); payload['status_code'] = '2'
    changed[0]['payload_json'] = json.dumps(payload, sort_keys=True)
    changed[0]['payload_sha256'] = hashlib.sha256(changed[0]['payload_json'].encode()).hexdigest()
    with database.begin() as conn:
        assert sync.persist_batch(conn, 'synthetic-device', DAY.isoformat(), changed)['conflict_count'] == 1
        retained = conn.execute(text('SELECT payload_json FROM vera_facegate_event')).scalar_one()
        assert json.loads(retained)['status_code'] == '1'
    with database.begin() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        data = fg.project_evidence(conn, DAY, DAY)
        assert data['issues'] == [{'event_id': '0', 'reason': 'conflicting_duplicate'}]
        assert runtime.blocking_issues(data, DAY, 'Unrelated synthetic employee')
        report = runtime.evidence_diagnostics(data, DAY, DAY)
        assert report['global_issue_count'] == 1 and report['scoped_issue_count'] == 0
        assert conn.execute(text('SELECT payload_json FROM vera_facegate_event')).scalar_one() == retained


def test_conflict_capture_is_bounded_to_device_and_requested_overnight_range(database):
    seed_preview(database)
    # An unrelated older day outside the requested overnight capture window
    # must not disable healthy current dates indefinitely.
    with database.begin() as conn:
        conn.execute(text('''INSERT INTO vera_facegate_event_conflict VALUES
            (:device,'old','2026-01-01T10:00:00+07:00','2026-01-01','a','b','{}','now','now',1)'''),
            {'device': 'synthetic-device'})
        assert fg.project_evidence(conn, DAY, DAY)['issues'] == []


def test_missing_conflict_ledger_fails_closed_without_creating_schema(database):
    seed_preview(database)
    with database.begin() as conn:
        conn.execute(text('DROP TABLE vera_facegate_event_conflict'))
    with database.begin() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        with pytest.raises(fg.EvidenceError, match='conflict_archive_unavailable'):
            fg.project_evidence(conn, DAY, DAY)
        assert conn.execute(text("SELECT to_regclass('vera_facegate_event_conflict')")).scalar() is None


def test_verified_device_name_drift_is_reviewed_without_rewriting_archive(database):
    from vera_employee_rename_sync import ensure_jobs
    from test_facegate_attendance import ADDRESS, REF, MAP
    seed_preview(database)
    changed=deepcopy(batch(1))
    old=json.loads(changed[0]['payload_json'])
    new={**old,'device_name':'Ánh Thử'}
    changed[0]['payload_json']=json.dumps(new,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    changed[0]['payload_sha256']=hashlib.sha256(changed[0]['payload_json'].encode()).hexdigest()
    with database.begin() as conn:
        ensure_jobs(conn)
        mappings=deepcopy(MAP);mappings[0]['device_name']='Ánh Thử'
        conn.execute(text("UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb) WHERE category='facegate' AND setting_key='mapping_synthetic-device'"),{'value':json.dumps(mappings)})
        conn.execute(text("INSERT INTO vera_facegate_rename_job(employee_username,device_id,device_address,profile_id,old_name,new_name,registration_ref,status) VALUES (:name,'synthetic-device',:address,:uid,:old,:name,CAST(:ref AS jsonb),'verified')"),{'name':mappings[0]['username'],'address':ADDRESS,'uid':mappings[0]['profile_id'],'old':old['device_name'],'ref':json.dumps(REF)})
        sync.persist_batch(conn,'synthetic-device',DAY.isoformat(),changed)
    with database.begin() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        data=fg.project_evidence(conn,DAY,DAY)
        assert data['issues']==[] and len(data['rename_reviews'])==1
        stored=conn.execute(text("SELECT payload_json FROM vera_facegate_event WHERE event_id='0'")).scalar_one()
        assert json.loads(stored)['device_name']==old['device_name']
        assert conn.execute(text('SELECT count(*) FROM vera_facegate_event_conflict')).scalar_one()==1

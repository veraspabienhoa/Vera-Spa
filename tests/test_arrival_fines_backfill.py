import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path
from vera_facegate_control_log import VN_TZ

spec = importlib.util.spec_from_file_location('backfill',Path(__file__).parents[1]/'scripts/arrival_fines_oct08_11.py')
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)


def sample():
    day = date(2026,10,8)
    start = datetime(2026,10,8,9,tzinfo=VN_TZ)
    end = start+timedelta(hours=8)
    now = datetime(2026,10,11,20,tzinfo=VN_TZ)
    data = {'index':{(1,):{'username':'Test'}},'issues':[],
            'events':[{'occurred_at':(start+timedelta(minutes=1)).isoformat()}],
            'syncs':[{'work_date':day,'last_synced_at':(end+timedelta(hours=2)).isoformat(),'last_observed_count':1}]}
    return data,day,now,(start,end)


def test_closed_historical_capture_can_backfill():
    data,day,now,window = sample()
    assert backfill.evidence_reasons(data,'Test',day,now,window)==[]


def test_unidentified_scan_still_blocks_every_fine():
    data,day,now,window = sample()
    data['issues']=[{'reason':'unmapped_reference'}]
    assert 'unresolved_evidence' in backfill.evidence_reasons(data,'Test',day,now,window)


def test_incomplete_closed_capture_stays_blocked():
    data,day,now,window = sample()
    data['syncs'][0]['last_synced_at']=window[1].isoformat()
    assert 'incomplete_archive' in backfill.evidence_reasons(data,'Test',day,now,window)


def test_future_capture_not_waived():
    data,day,now,window = sample()
    data['syncs'][0]['last_synced_at']=(now+timedelta(minutes=1)).isoformat()
    assert 'stale_archive' in backfill.evidence_reasons(data,'Test',day,now,window)


def test_current_day_requires_fresh_capture():
    data,day,now,window = sample()
    now=window[1]+timedelta(hours=4)
    assert 'stale_archive' in backfill.evidence_reasons(data,'Test',day,now,window)


def test_wrong_count_stays_blocked():
    data,day,now,window = sample()
    data['syncs'][0]['last_observed_count']=2
    assert 'incomplete_archive' in backfill.evidence_reasons(data,'Test',day,now,window)


def allowance_fixture(monkeypatch):
    monkeypatch.setattr(backfill.auto,'registered_late_for_day',lambda *_:([],0,''))
    monkeypatch.setattr(backfill.auto,'late_support_for_day',lambda *_:([],0,''))
    return {'employee_name':'Test','late_minutes':120.5,'check_in_at':'2026-10-10T12:00:30+07:00'}


def test_support_fully_covers_lateness(monkeypatch):
    row=allowance_fixture(monkeypatch)
    monkeypatch.setattr(backfill.auto,'late_support_for_day',lambda *_:(['support'],180,'support'))
    assert backfill.arrival_after_allowances(None,row,date(2026,10,10),[])==(0,'allowance_covered')


def test_support_preserves_late_seconds(monkeypatch):
    row=allowance_fixture(monkeypatch)
    monkeypatch.setattr(backfill.auto,'late_support_for_day',lambda *_:(['support'],120,'support'))
    assert backfill.arrival_after_allowances(None,row,date(2026,10,10),[])==(0.5,'chargeable')


def test_unknown_support_blocks(monkeypatch):
    row=allowance_fixture(monkeypatch)
    monkeypatch.setattr(backfill.auto,'late_support_for_day',lambda *_:(['support'],None,'support'))
    assert backfill.arrival_after_allowances(None,row,date(2026,10,10),[])==(None,'unknown_support_allowance')


def test_existing_manual_fine_not_duplicated(monkeypatch):
    row=allowance_fixture(monkeypatch)
    leaves=[{'leave_reason':'Đi trễ KHÔNG phép','penalty':100}]
    assert backfill.arrival_after_allowances(None,row,date(2026,10,10),leaves)==(None,'existing_positive_arrival_fine')


def test_approved_leave_preserved(monkeypatch):
    row=allowance_fixture(monkeypatch)
    leaves=[{'leave_reason':'Nghỉ CÓ phép','penalty':0}]
    assert backfill.arrival_after_allowances(None,row,date(2026,10,10),leaves)==(None,'other_leave_or_manual_decision')


def test_registered_clock_overrides_support(monkeypatch):
    row=allowance_fixture(monkeypatch)
    monkeypatch.setattr(backfill.auto,'registered_late_for_day',lambda *_:(['registered'],720,'registered'))
    monkeypatch.setattr(backfill.auto,'daily_clock',lambda *_:'12:00')
    monkeypatch.setattr(backfill.auto,'late_support_for_day',lambda *_:(['support'],180,'support'))
    assert backfill.arrival_after_allowances(None,row,date(2026,10,10),[])==(0.5,'chargeable')


def rename_conflict_fixture():
    import json,hashlib
    ref={'file_type':0,'file_index':0,'file_position':42}
    original={'device_name':'Nhan_Vien','device_address':'192.168.1.26','registration_ref':ref,'status_code':'1','type_code':'0'}
    observed={**original,'device_name':backfill.CONFIRMED_OWNER}
    digest=lambda p:hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    event={'event_id':'81064','occurred_at':backfill.CONFIRMED_EVENTS['81064'],'payload_json':original,'payload_sha256':digest(original)}
    conflict={'event_id':'81064','occurred_at':event['occurred_at'],'stored_payload_sha256':digest(original),'observed_payload_json':observed,'observed_payload_sha256':digest(observed)}
    mapping={'username':backfill.CONFIRMED_OWNER,'device_name':observed['device_name'],'profile_id':5,'device_address':original['device_address'],'registration_ref':ref,'confirmed_by':'operator'}
    job={'employee_username':mapping['username'],'profile_id':5,'device_address':mapping['device_address'],'registration_ref':ref,'status':'verified','old_name':'Nhan_Vien','new_name':mapping['username']}
    return event,conflict,mapping,job,original['device_address']


def test_exact_name_only_drift_with_verified_rename_is_reviewable():
    assert backfill.verified_name_only_conflict(*rename_conflict_fixture())


def test_other_conflict_fields_are_not_ignored():
    for field,value in [('registration_ref',None),('status_code','0'),('type_code','1'),('device_address','192.168.1.27')]:
        event,conflict,mapping,job,address=rename_conflict_fixture()
        conflict['observed_payload_json'][field]=value
        assert not backfill.verified_name_only_conflict(event,conflict,mapping,job,address)


def test_unconfirmed_other_owner_or_other_profile_cannot_resolve_conflict():
    for target,field,value in [('job','status','pending'),('mapping','username','Other'),('mapping','confirmed_by',''),('job','profile_id',8),('conflict','observed_payload_sha256','wrong'),('event','event_id','999')]:
        event,conflict,mapping,job,address=rename_conflict_fixture()
        {'job':job,'mapping':mapping,'conflict':conflict,'event':event}[target][field]=value
        assert not backfill.verified_name_only_conflict(event,conflict,mapping,job,address)

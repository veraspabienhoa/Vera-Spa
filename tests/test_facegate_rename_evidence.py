from copy import deepcopy
import hashlib
import json
import pytest
from vera_facegate_rename_evidence import review_conflicts


def fixture():
    ref={'file_type':0,'file_index':0,'file_position':42}
    address='192.168.1.34'
    payload={'device_name':'Old','device_address':address,'status_code':'1','type_code':'0','registration_ref':ref}
    newer={**payload,'device_name':'New'}
    event={'event_id':'1','occurred_at':'2026-10-12T09:00:01+07:00','payload_json':payload,'payload_sha256':digest(payload)}
    conflict={'event_id':'1','occurred_at':event['occurred_at'],'stored_payload_sha256':digest(payload),'observed_payload_sha256':digest(newer),'observed_payload_json':newer}
    mapping={'username':'New','device_name':'New','profile_id':3,'device_address':address,'registration_ref':ref,'confirmed_by':'Operator'}
    job={'status':'verified','employee_username':'New','profile_id':3,'device_address':address,'registration_ref':ref,'old_name':'Old','new_name':'New'}
    return event,conflict,{(0,0,42):mapping},address,[job]


def digest(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def test_only_verified_name_drift_is_reviewed_and_originals_are_untouched():
    event,conflict,index,address,jobs=fixture();original=deepcopy((event,conflict))
    retained,reviews=review_conflicts([event],[conflict],index,address,jobs)
    assert retained==[] and reviews[0]['raw_evidence_preserved']
    assert (event,conflict)==original


@pytest.mark.parametrize('field,value',[('status_code','2'),('type_code','1'),('registration_ref',None),('device_address','192.168.1.35'),('extra','changed')])
def test_even_rehashed_non_name_changes_stay_blocking(field,value):
    event,conflict,index,address,jobs=fixture()
    conflict['observed_payload_json'][field]=value
    conflict['observed_payload_sha256']=digest(conflict['observed_payload_json'])
    assert review_conflicts([event],[conflict],index,address,jobs)==([conflict],[])


@pytest.mark.parametrize('target,field,value',[('job','status','pending'),('job','employee_username','Other'),('job','profile_id',4),('job','old_name','Someone Else'),('mapping','confirmed_by',''),('mapping','device_name','Different'),('conflict','stored_payload_sha256','wrong'),('event','occurred_at','2026-10-12T09:05:00+07:00')])
def test_bad_journal_mapping_digest_or_time_keeps_the_conflict(target,field,value):
    event,conflict,index,address,jobs=fixture()
    {'job':jobs[0],'mapping':index[(0,0,42)],'conflict':conflict,'event':event}[target][field]=value
    assert review_conflicts([event],[conflict],index,address,jobs)==([conflict],[])


def test_an_unreviewable_variant_of_same_scan_still_blocks():
    event,conflict,index,address,jobs=fixture()
    extra=deepcopy(conflict);extra['observed_payload_json']['status_code']='2'
    extra['observed_payload_sha256']=digest(extra['observed_payload_json'])
    retained,reviews=review_conflicts([event],[conflict,extra],index,address,jobs)
    assert retained==[extra] and len(reviews)==1

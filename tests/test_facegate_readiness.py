import json
from vera_facegate_readiness import summarize


def test_report_counts_reference_matches_without_exposing_identity_or_claiming_readiness():
    ref = {'file_type':0,'file_index':1,'file_position':99}
    mapping = {'registration_ref':ref,'confirmed_by':'secret-admin','username':'private-employee'}
    report = summarize({'records':[{'registration_ref':ref,'device_name':'private-name','status_code':'0','type_code':'1'},
                                  {'registration_ref':None,'status_code':'private text','type_code':'name'}],
                        'total_count':100,'truncated':True}, [mapping])
    assert report['sample_reference_matches'] == 1
    assert report['raw_status_type_counts'] == {'0/1':1,'other':1}
    assert report['sample_truncated'] is True
    assert report['attendance_cutover_ready'] is False
    assert 'private' not in json.dumps(report) and 'secret' not in json.dumps(report)
    assert summarize({'records':[{'registration_ref':ref}]},[mapping,mapping])['sample_reference_matches'] == 0

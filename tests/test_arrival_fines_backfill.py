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

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

import vera_facegate_auto_sync as sync
import vera_facegate_runtime as runtime
import timesoft_sync_job as job


@pytest.mark.parametrize('paused', [False, True])
def test_minute_arrival_worker_releases_read_connection_before_writing(monkeypatch, paused, capsys):
    conn = object()
    active = []
    written = []
    day = date(2026, 10, 11)
    frame = pd.DataFrame([{'employeeInfo.Name': 'Synthetic Employee'}])
    @contextmanager
    def begin():
        active.append(conn)
        try:
            yield conn
        finally:
            active.pop()
    monkeypatch.setattr(job.auto_check, 'load_config', lambda c: {'status': 'PAUSED' if paused else 'RUNNING'})
    def frames(c, days):
        assert c is conn and active == [conn] and days == [day]
        return [(day, frame)]
    monkeypatch.setattr(runtime, 'worker_frames', frames)
    monkeypatch.setattr(job.auto_check, 'load_catalog', lambda c: {'catalog': True})
    def write(engine, cfg, names, catalog, frames, *, include_synced_history):
        assert not active
        assert include_synced_history is True
        assert names == {job._employee_key('Synthetic Employee'): 'Synthetic Employee'}
        assert cfg['status'] == 'RUNNING' and catalog == {'catalog': True}
        written.append(frames)
        print('Synthetic Employee must not reach minute-worker logs')
        return {'added': 1, 'errors': 0}
    monkeypatch.setattr(job, 'process_timesoft_penalties', write)
    result = sync.process_arrival_penalties(SimpleNamespace(begin=begin), day)
    assert result['added'] == int(not paused)
    assert len(written) == int(not paused)
    assert not capsys.readouterr().out


def test_archive_reconciles_today_before_yesterday_and_keeps_successful_day_on_failure(monkeypatch, capsys):
    from datetime import datetime, timedelta
    import json
    calls=[]
    today=datetime.now(sync.VN_TZ).date()
    def archive(args, **kwargs):
        day=date.fromisoformat(args[args.index('--date')+1])
        calls.append(('archive',day))
        if day!=today:
            return SimpleNamespace(returncode=1,stdout=json.dumps({'ok':False,'reason':'sync_failed'}))
        return SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'inserted_count':1,'stored_day_count':1}))
    monkeypatch.setattr(sync.subprocess,'run',archive)
    monkeypatch.setattr(sync,'reconcile_day',lambda day:calls.append(('reconcile',day)) or [])
    assert sync.archive_days()==1
    assert calls==[('archive',today),('reconcile',today),('archive',today-timedelta(days=1))]
    assert 'sync_failed' in capsys.readouterr().out


def test_failed_rule_does_not_suppress_other_committed_rules(monkeypatch):
    import vera_attendance_source as source
    import vera_facegate_cutover as cutover
    import vera_missing_checkin_absence as absence
    import vera_hc_rules as hc
    conn=object();transactions=[];calls=[]
    @contextmanager
    def begin():
        transactions.append('open')
        try:yield conn
        finally:transactions.append('closed')
    engine=SimpleNamespace(begin=begin,dispose=lambda:calls.append('disposed'))
    monkeypatch.setattr(source,'enabled',lambda:True)
    monkeypatch.setattr(cutover,'runtime_engine',lambda:engine)
    monkeypatch.setattr(runtime,'publish',lambda c,a,b:calls.append('publish') or [])
    def bad(*_):
        assert transactions[-1]=='closed'
        calls.append('arrival');raise RuntimeError('private detail')
    monkeypatch.setattr(sync,'process_arrival_penalties',bad)
    monkeypatch.setattr(hc,'process',lambda c:calls.append('hc') or {'added':1})
    monkeypatch.setattr(absence,'process',lambda c:calls.append('absence') or {'added':0})
    result=sync.reconcile_day(date(2026,10,12))
    assert calls==['publish','arrival','hc','absence','disposed']
    assert result==[{'date':'2026-10-12','stage':'arrival_rule','reason':'RuntimeError'}]

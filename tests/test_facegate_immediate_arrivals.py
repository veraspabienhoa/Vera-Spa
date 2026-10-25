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
        assert cfg['status'] == ('PAUSED' if paused else 'RUNNING') and catalog == {'catalog': True}
        written.append(frames)
        print('Synthetic Employee must not reach minute-worker logs')
        return {'added': 1, 'errors': 0}
    monkeypatch.setattr(job, 'process_timesoft_penalties', write)
    result = sync.process_arrival_penalties(SimpleNamespace(begin=begin), day)
    assert result['added'] == 1
    assert len(written) == 1
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
    assert calls==[('archive',today),('archive',today-timedelta(days=1))]
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
    monkeypatch.setattr(sync,'process_break_penalties',lambda *a:calls.append('break') or {'added':0})
    monkeypatch.setattr(hc,'process',lambda c:calls.append('hc') or {'added':1})
    monkeypatch.setattr(absence,'process',lambda c:calls.append('absence') or {'added':0})
    result=sync.reconcile_day(date(2026,10,12))
    assert calls==['publish','arrival','break','hc','absence','disposed']
    assert result==[{'date':'2026-10-12','stage':'arrival_rule','reason':'RuntimeError'}]


def test_apply_reconciles_only_after_archive_commit_without_waiting_for_auto_check(monkeypatch):
    import vera_facegate_sync as archive
    import vera_web_v2_devices as devices
    state = {'active': False, 'committed': False, 'calls': []}
    class Conn:
        def execute(self, sql, params=None):
            sql = str(sql)
            value = [] if 'value_json' in sql else None if 'last_observed_count' in sql else True
            return SimpleNamespace(scalar=lambda: value)
    @contextmanager
    def connection():
        assert not state['active']
        state['active'] = True
        try: yield Conn()
        finally: state['active'] = False
    @contextmanager
    def transaction():
        with connection() as conn: yield conn
        state['committed'] = True
    @contextmanager
    def address(*args): yield 'synthetic'
    engine = SimpleNamespace(connect=connection, begin=transaction)
    monkeypatch.setattr(archive.device, 'mapping_device_id', lambda: 'synthetic')
    monkeypatch.setattr(devices, 'active_facegate_mappings', lambda c, m: [])
    monkeypatch.setattr(devices, 'use_registered_facegate', address)
    monkeypatch.setattr(archive, 'prepare_batch', lambda *a: [])
    monkeypatch.setattr(archive, 'summarize', lambda *a: {'confirmed_mapping_count':0,'sample_reference_matches':0})
    monkeypatch.setattr(archive, 'ensure_schema', lambda c: None)
    monkeypatch.setattr(archive, 'persist_batch', lambda *a: {})
    def reconcile(day, **kwargs):
        assert not state['active'] and state['committed'] and kwargs['engine'] is engine
        state['calls'].append(day)
        return []
    monkeypatch.setattr(sync, 'reconcile_day', reconcile)
    archive.sync_day(engine, '2026-10-14', apply=False, fetch=lambda *a: {'total_count':0})
    assert not state['calls']
    archive.sync_day(engine, '2026-10-14', apply=True, fetch=lambda *a: {'total_count':0})
    assert state['calls'] == [date(2026,10,14)]


def test_reconciliation_report_exposes_counts_and_blockers_without_private_payloads(monkeypatch):
    from contextlib import nullcontext
    import vera_attendance_source as source
    import vera_missing_checkin_absence as absence
    import vera_hc_rules as hc
    monkeypatch.setattr(source, 'enabled', lambda: True)
    monkeypatch.setattr(runtime, 'publish', lambda *a: [])
    monkeypatch.setattr(sync, 'process_arrival_penalties', lambda *a: {
        'eligible': 2, 'added': 1, 'errors': 1, 'evidence_blocked': 3,
        'employee': 'PRIVATE_EMPLOYEE', 'sql': 'PRIVATE_SQL',
        'reason_counts': {'stale_archive': 3, 'PRIVATE_REASON': 4},
        'error_counts': {'database_error': 1, 'PRIVATE_SQL': 2}})
    monkeypatch.setattr(sync, 'process_break_penalties', lambda *a: {'added': 0})
    monkeypatch.setattr(absence, 'process', lambda c: {'added': 0, 'reason': 'stale_evidence'})
    monkeypatch.setattr(hc, 'process', lambda c: {'added': 0})
    report = []
    failures = sync.reconcile_day(date(2026, 10, 25),
        engine=SimpleNamespace(begin=lambda: nullcontext(object())), report=report)
    arrival = next(r for r in report if r['stage'] == 'arrival_rule')
    assert arrival['added'] == arrival['errors'] == 1
    assert arrival['reason_counts'] == {'stale_archive': 3}
    assert arrival['error_counts'] == {'database_error': 1}
    assert report[-1]['reason'] == 'stale_evidence'
    assert 'PRIVATE' not in str(report)
    assert failures == [{'date': '2026-10-25', 'stage': 'arrival_rule', 'reason': 'rule_errors'}]


def test_archive_forwards_rule_summary_even_when_no_new_scans(monkeypatch, capsys):
    import json
    report = {'stage': 'arrival_rule', 'added': 0, 'considered': 4,
              'evidence_blocked': 4, 'reason_counts': {'unresolved_evidence': 4}}
    monkeypatch.setattr(sync.subprocess, 'run', lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout=json.dumps({'ok': True, 'inserted_count': 0,
            'stored_day_count': 145, 'reconciliation_results': [report], 'reconciliation_failures': []})))
    assert sync.archive_days() == 0
    summaries = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r['reconciliation'] for r in summaries if 'reconciliation' in r] == [report, report]

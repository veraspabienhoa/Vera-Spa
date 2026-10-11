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
    def write(engine, cfg, names, catalog, frames):
        assert not active
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

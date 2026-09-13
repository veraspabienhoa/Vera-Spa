from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
import vera_web_v2_live_tour as live
from test_live_tour_server_only import SettingsDatabase, app_client


def initialized():
    db = SettingsDatabase()
    app, client = app_client(db)
    assert client.get('/v2/live-tour').status_code == 200
    return db, client


def test_many_readers_succeed_while_writer_holds_lock(monkeypatch):
    db, client = initialized()
    before, revision = deepcopy(db.stored), db.revision
    reads = db.employee_reads
    monkeypatch.setattr(live, 'try_state_lock', lambda *_: False)
    # A busy read must not enter attendance/directory/write projections.
    def forbidden(*args, **kwargs):
        raise AssertionError('projection attempted without lock')
    monkeypatch.setattr(live, '_read_state', forbidden)
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: client.get('/v2/live-tour'), range(24)))
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json()['revision'] == revision for r in responses)
    assert db.stored == before and db.revision == revision
    assert db.employee_reads == reads


@pytest.mark.parametrize('path', [
    '/v2/live-tour/reports', '/v2/live-tour/customers', '/v2/live-tour/settings',
])
def test_secondary_reads_do_not_fail_when_board_busy(monkeypatch, path):
    db, client = initialized()
    revision = db.revision
    monkeypatch.setattr(live, 'try_state_lock', lambda *_: False)
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()['revision'] == revision


def test_busy_bootstrap_does_not_return_fabricated_state(monkeypatch):
    db = SettingsDatabase()
    _, client = app_client(db)
    monkeypatch.setattr(live, 'try_state_lock', lambda *_: False)
    assert client.get('/v2/live-tour').status_code == 503
    assert db.stored is None

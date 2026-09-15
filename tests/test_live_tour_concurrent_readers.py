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


def test_unchanged_poll_returns_lightweight_response_without_projection(monkeypatch):
    db, client = initialized()
    revision = db.revision

    def forbidden(*args, **kwargs):
        raise AssertionError('unchanged poll must not lock or project the board')

    monkeypatch.setattr(live, 'try_state_lock', forbidden)
    monkeypatch.setattr(live, '_read_state', forbidden)
    response = client.get(f'/v2/live-tour?known_revision={revision}')
    assert response.status_code == 200
    assert response.json()['unchanged'] is True
    assert response.json()['revision'] == revision
    assert 'records' not in response.json()


def test_changed_conditional_poll_reads_committed_snapshot_without_projection(monkeypatch):
    db, client = initialized()
    before, revision = deepcopy(db.stored), db.revision

    def forbidden(*args, **kwargs):
        raise AssertionError('routine poll must not lock or project the board')

    monkeypatch.setattr(live, 'try_state_lock', forbidden)
    monkeypatch.setattr(live, '_read_state', forbidden)
    response = client.get(f'/v2/live-tour?known_revision={revision - 1}')
    assert response.status_code == 200
    assert response.json()['revision'] == revision
    assert response.json()['records']
    assert db.stored == before and db.revision == revision


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
    monkeypatch.setattr(live, 'acquire_state_lock', lambda *_: (_ for _ in ()).throw(
        live.HTTPException(503, 'busy')
    ))
    assert client.get('/v2/live-tour').status_code == 503
    assert db.stored is None


@pytest.mark.parametrize('path', ['/v2/live-tour/reports', '/v2/live-tour/customers'])
def test_lookup_reads_skip_lock_and_projection_even_when_free(monkeypatch, path):
    db, client = initialized()
    before, revision = deepcopy(db.stored), db.revision
    def forbidden(*args, **kwargs):
        raise AssertionError('lookup must not lock or refresh attendance')
    monkeypatch.setattr(live, 'try_state_lock', forbidden)
    monkeypatch.setattr(live, '_read_state', forbidden)
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()['revision'] == revision
    assert db.stored == before

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import vera_live_tour_resource_store as store
from test_live_tour_backend import NOW, employee, state_with


@pytest.mark.parametrize('action', ['booking', 'start', 'quick_checkout'])
@pytest.mark.parametrize('blocked', [False, True])
def test_counter_recovery_requires_exclusive_fence_and_full_read(monkeypatch, action, blocked):
    state = state_with(employee('e1', 'Test'))
    state['counter_business_date'] = '2026-09-04'
    reads, locks = [], []
    conn = SimpleNamespace(info={})

    def lock(conn, *, shared=False):
        locks.append(shared)
        if not shared and blocked:
            raise HTTPException(503, 'busy')
        conn.info['live_tour_exclusive'] = not shared

    def read(conn, **kwargs):
        reads.append(kwargs)
        return deepcopy(state), 7, {}

    monkeypatch.setattr(store, 'lock', lock)
    monkeypatch.setattr(store, 'read', read)
    monkeypatch.setattr(store.concurrency, 'lock_resources', lambda *a, **kw: None)
    args = (conn, action, {'employee_id': 'e1'}, 7, 'recovery-key', NOW.date().isoformat())
    if blocked:
        with pytest.raises(HTTPException) as error:
            store.begin_action(*args, compact=True)
        assert error.value.status_code == 503
        assert len(reads) == 1
    else:
        _, revision, fresh = store.begin_action(*args, compact=True)
        assert fresh and revision == 7
        assert reads[-1] == {}
        assert conn.info['live_tour_exclusive']
    assert locks == [True, False]

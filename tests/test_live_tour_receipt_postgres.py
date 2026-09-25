from copy import deepcopy

import pytest

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW
from test_live_tour_resource_postgres import database


def test_nested_receipt_edit_rolls_back_without_changing_saved_payment(database):
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        after = deepcopy(before)
        after['idempotency']['payment-key'] = {
            'status': 'completed', 'result': {'invoice': {'id': 'bill-1', 'total': 350000}},
        }
        store.write(conn, before, after, 'test')
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            store.lock(conn)
            before, _, _ = store.read(conn)
            after = deepcopy(before)
            after['idempotency']['payment-key']['result']['invoice']['total'] = 0
            assert before['idempotency']['payment-key']['result']['invoice']['total'] == 350000
            store.write(conn, before, after, 'test')
            raise RuntimeError('rollback test')
    with database.connect() as conn:
        saved, _, _ = store.read(conn)
    assert saved['idempotency']['payment-key']['result']['invoice']['total'] == 350000


def test_audit_eviction_batch_preserves_order_payloads_and_rollback(database, monkeypatch):
    monkeypatch.setattr(live, 'MAX_AUDIT', 5)
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        seeded = deepcopy(before)
        seeded['audit'] = [{'id': identifier, 'action': 'test', 'detail': {'number': i}}
                           for i, identifier in enumerate(['z', 'x', 'a', 'c', 'b'])]
        seeded['idempotency']['saved-payment'] = {'status': 'completed', 'result': {'invoice': {'total': 350000}}}
        store.write(conn, before, seeded, 'test')
    with database.begin() as conn:
        store.lock(conn)
        before, _, versions = store.read(conn)
        changed = deepcopy(before)
        live._audit(changed, 'test', {}, 'test', NOW)
        revision = store.write(conn, before, changed, 'test')
    with database.connect() as conn:
        saved, saved_revision, saved_versions = store.read(conn)
    assert saved_revision == revision
    assert saved['audit'] == changed['audit']
    assert saved['idempotency'] == seeded['idempotency']
    assert [row['id'] for row in saved['audit'][:4]] == ['x', 'a', 'c', 'b']
    assert all(saved_versions[('audit', key)] == versions[('audit', key)] for key in ['x', 'a', 'c', 'b'])
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            store.lock(conn)
            before, _, _ = store.read(conn)
            changed_again = deepcopy(before)
            live._audit(changed_again, 'test', {}, 'test', NOW)
            store.write(conn, before, changed_again, 'test')
            raise RuntimeError('rollback ordering')
    with database.connect() as conn:
        rolled_back, after_revision, _ = store.read(conn)
    assert after_revision == revision
    assert rolled_back['audit'] == saved['audit']
    assert rolled_back['idempotency'] == saved['idempotency']

from copy import deepcopy

import pytest

import vera_live_tour_resource_store as store
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

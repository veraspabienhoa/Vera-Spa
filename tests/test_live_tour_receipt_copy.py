from copy import deepcopy
from datetime import datetime
import json

from fastapi import HTTPException
import pytest

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW


def receipt_state():
    state = live._empty_state(NOW)
    payload_hash = live._canonical_payload_hash('quick_checkout', {'employee_id': 'e1'})
    state['idempotency'] = store._ReceiptSnapshot({
        'old-payment': {'action': 'quick_checkout', 'actor': 'admin',
                        'payload_hash': payload_hash, 'status': 'completed',
                        'at': NOW.isoformat(), 'result': {'invoice': {
                            'id': 'invoice-1', 'total': 350000, 'tip': 1000000,
                            'entries': [{'employee_name': 'Kiểm thử', 'paid': True,
                                         'discount': None, 'units': 0.5}]}}},
    })
    return state, payload_hash


def test_receipt_copy_preserves_serialized_values_and_nested_isolation():
    before, _ = receipt_state()
    working = deepcopy(live._normalize_state(before, NOW))
    assert json.dumps(working, sort_keys=True) == json.dumps(before, sort_keys=True)
    working['idempotency']['old-payment']['result']['invoice']['entries'][0]['units'] = 99
    working['idempotency'].pop('old-payment')
    assert before['idempotency']['old-payment']['result']['invoice']['entries'][0]['units'] == 0.5
    assert 'old-payment' in before['idempotency']


def test_old_financial_receipt_survives_pruning_and_still_rejects_changed_payload(monkeypatch):
    before, payload_hash = receipt_state()
    working = deepcopy(before)
    monkeypatch.setattr(live, 'MAX_IDEMPOTENCY', 1)
    live._remember_idempotency(working, 'new-change', action='set_vip', actor='admin',
                              payload_hash='different', result={'ok': True}, now=NOW)
    entry = live._idempotency_replay(working, 'old-payment', action='quick_checkout',
                                    actor='admin', payload_hash=payload_hash)
    assert entry['result']['invoice']['total'] == 350000
    with pytest.raises(HTTPException) as exc:
        live._idempotency_replay(working, 'old-payment', action='quick_checkout',
                                 actor='admin', payload_hash='different')
    assert exc.value.status_code == 409
    assert list(before['idempotency']) == ['old-payment']


def test_non_json_in_memory_values_fall_back_to_independent_deepcopy():
    original = store._ReceiptSnapshot({'key': {'time': datetime(2026, 9, 25), 'values': {1, 2}}})
    copied = deepcopy(original)
    copied['key']['values'].add(3)
    assert original['key']['values'] == {1, 2}
    assert copied['key']['time'] == original['key']['time']


def test_database_receipts_and_repeated_working_copies_do_not_alias():
    original, _ = receipt_state()
    original['_resource_ready'] = True
    # The driver returns ordinary decoded JSON, with no special dictionary type.
    payload = json.loads(json.dumps(original))
    class Result:
        def mappings(self): return self
        def all(self): return [{'kind': '_meta', 'payload': payload, 'aggregate_revision': 7}]
    class Conn:
        def execute(self, statement): return Result()
    first, _, _ = store.read(Conn())
    second = deepcopy(deepcopy(first))
    second['idempotency']['old-payment']['result']['invoice']['total'] = 0
    assert first['idempotency']['old-payment']['result']['invoice']['total'] == 350000
    assert payload['idempotency']['old-payment']['result']['invoice']['total'] == 350000


def test_public_response_does_not_copy_or_expose_private_receipts():
    state, _ = receipt_state()
    class PrivateReceipts(dict):
        def __deepcopy__(self, memo):
            raise AssertionError('Public response must not traverse private receipts')
    state['idempotency'] = PrivateReceipts(state['idempotency'])
    response = live._state_response(state, 7, NOW)
    assert 'idempotency' not in response
    assert response['revision'] == 7


def test_full_view_loads_all_business_collections_without_replay_receipts(monkeypatch):
    from test_live_tour_safety import api_client
    client, shared = api_client(monkeypatch)
    calls = []
    def read(conn, collections=None):
        calls.append(collections)
        result = deepcopy(shared['state'])
        result.pop('idempotency', None)
        return result, shared['revision'], {}
    monkeypatch.setattr(store, 'enabled', lambda: True)
    monkeypatch.setattr(store, 'read', read)
    response = client.get('/v2/live-tour?view=full')
    assert response.status_code == 200
    assert calls == [store.relational.RESOURCE_COLLECTIONS]
    assert 'idempotency' not in response.json()

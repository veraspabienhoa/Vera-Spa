"""Area configuration is independent of unrelated live work, never blind-rebased."""
from copy import deepcopy

import pytest
from fastapi import HTTPException
from sqlalchemy import event

import vera_web_v2_live_tour as live
import vera_live_tour_resource_store as store
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_safety import api_client
from test_live_tour_resource_postgres import database
from test_live_tour_payment_scope_postgres import payments, saved


def area(state, name='1'):
    return next(row for row in live._service_areas(state) if row['name'] == name)


def request(current, revision, key='area-request-123'):
    return dict(action='service_area_upsert', expected_revision=revision, idempotency_key=key,
                response_view='receipt', payload={**current, 'expected_area_version': current['version'],
                    'beds': [*current['beds'], {'name': 'Extra bed'}]})


@pytest.mark.parametrize('phase', ['waiting', 'doing', 'pending'])
@pytest.mark.parametrize('service', ['Body 90', 'P.Riêng'])
def test_add_bed_preserves_active_and_unpaid_references_and_private_room_rules(phase, service):
    state = state_with(employee('e1', 'An'), employee('e2', 'Binh'))
    live._apply_action(state, 'booking', {'employee_id': 'e1', 'room': '1.1', 'service': service}, 'admin', NOW)
    if phase != 'waiting':
        live._apply_action(state, 'start', {'employee_id': 'e1'}, 'admin', NOW)
    if phase == 'pending':
        live._apply_action(state, 'finish_to_pending', {'employee_id': 'e1'}, 'admin', NOW)
    before = deepcopy(state)
    current = area(state)
    result = live._apply_action(state, 'service_area_upsert', request(current, 1)['payload'], 'admin', NOW)
    after = result['service_area']
    assert len(after['beds']) == len(current['beds']) + 1
    assert after['beds'][:-1] == current['beds']
    assert state['employees'] == before['employees'] and state['pending'] == before['pending']
    assert state['invoices'] == before['invoices'] and state['reports'] == before['reports']
    assert after['version'] != current['version']
    if service == 'P.Riêng' and phase != 'pending':
        assert not live._room_available(state, after['beds'][-1]['booking_name'])
    for payload in ({**after, 'name': 'Renamed'}, {**after, 'beds': after['beds'][1:]}):
        unchanged = deepcopy(state)
        with pytest.raises(HTTPException) as exc:
            live._apply_action(state, 'service_area_upsert', payload, 'admin', NOW)
        assert exc.value.status_code == 409 and state == unchanged


def test_area_http_ignores_other_rooms_but_rejects_same_area_even_with_refreshed_board_version(monkeypatch):
    client, shared = api_client(monkeypatch, state_with(employee('e1', 'An')))
    first = request(area(shared['state']), shared['revision'])
    second = request(area(shared['state'], '2'), shared['revision'], 'other-area-123')
    # An unrelated user changes operational data while both editors stay open.
    live._apply_action(shared['state'], 'set_vip', {'employee_id': 'e1'}, 'other', NOW)
    shared['revision'] += 1
    one = client.post('/v2/live-tour/action', json=first)
    assert one.status_code == 200, one.text
    two = client.post('/v2/live-tour/action', json=second)
    assert two.status_code == 200, two.text
    assert shared['state']['employees'][0]['vip'] is True
    persisted = deepcopy(shared)
    repeated = client.post('/v2/live-tour/action', json=first)
    assert repeated.status_code == 200 and repeated.json()['duplicate']
    assert shared == persisted
    stale = deepcopy(first)
    stale.update(expected_revision=shared['revision'], idempotency_key='stale-form-123')
    stale['payload']['beds'][-1]['name'] = 'Different addition'
    conflict = client.post('/v2/live-tour/action', json=stale)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()['detail']['code'] == 'LIVE_TOUR_AREA_CHANGED'
    assert shared == persisted
    create = dict(action='service_area_upsert', expected_revision=1, idempotency_key='new-room-123',
                  response_view='receipt', payload={'name':'New room','kind':'room','beds':[{'name':'New bed'}], 'expected_area_version':None})
    assert client.post('/v2/live-tour/action', json=create).status_code == 200
    create['idempotency_key'] = 'same-name-123'
    assert client.post('/v2/live-tour/action', json=create).status_code == 409


def test_area_compact_postgres_preserves_history_and_other_users_can_continue(database, payments, monkeypatch):
    client, checkout, _ = payments
    before, revision = saved(database)
    body = request(area(before), revision)
    original = store.read
    reads, statements = [], []
    def bounded(conn, collections=None, **kwargs):
        assert collections == store.AREA_COLLECTIONS or kwargs.get('profile') == 'area'
        value = original(conn, collections, **kwargs)
        assert value[0]['invoices'] == value[0]['reports'] == value[0]['audit'] == []
        assert set(value[0].get('idempotency', {})) <= {body['idempotency_key']}
        reads.append(kwargs.get('profile'))
        return value
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    monkeypatch.setattr(store, 'read', bounded)
    event.listen(database, 'before_cursor_execute', record)
    try:
        result = client.post('/v2/live-tour/action', json=body)
    finally:
        event.remove(database, 'before_cursor_execute', record)
    assert result.status_code == 200, result.text
    assert reads == [None, 'area'] and 'records' not in result.json()
    # Writes are batched by collection; no one-SQL-per-history-row loop.
    writes = [sql for sql in statements if sql.lstrip().split()[0].upper() in {'INSERT','UPDATE','DELETE'}]
    assert len(writes) <= 6, writes
    assert client.post('/v2/live-tour/action', json=body).json()['duplicate']
    monkeypatch.setattr(store, 'read', original)
    after, updated = saved(database)
    for kind in ('employees','pending','invoices','reports','customers','invoice_changes'):
        assert after[kind] == before[kind]
    assert all(after['idempotency'][key] == value for key,value in before['idempotency'].items())
    assert after.get('_configuration_revision') == before.get('_configuration_revision')
    with database.begin() as conn:
        _, _, fresh = store.begin_action(conn, 'update_appointment', {'employee_id':'e2','appointment':'Other room'},
                                        revision, 'other-user-123', live._counter_business_date(NOW).isoformat(), compact=True)
        assert fresh, 'untouched room must not inherit a global configuration conflict'
    with database.begin() as conn:
        _, _, fresh = store.begin_action(conn, 'update_appointment', {'employee_id':'e1','appointment':'Same room'},
                                        revision, 'same-room-123', live._counter_business_date(NOW).isoformat(), compact=True)
        assert not fresh, 'related room must still require fresh state'
    stale = deepcopy(body)
    stale.update(expected_revision=updated, idempotency_key='stale-again-123')
    assert client.post('/v2/live-tour/action', json=stale).status_code == 409
    assert saved(database) == (after, updated)


@pytest.mark.parametrize('same_area', [False, True])
def test_two_admins_saving_at_once_keep_both_changes_or_return_a_real_conflict(database, payments, same_area):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import sleep
    client, _, _ = payments
    before, revision = saved(database)
    barrier = Barrier(2)
    requests = [request(area(before, '1'), revision, 'parallel-area-one'),
                request(area(before, '1' if same_area else '2'), revision, 'parallel-area-two')]
    requests[1]['payload']['beds'][-1]['name'] = 'Another new bed'
    def save(body):
        barrier.wait(timeout=5)
        for _ in range(30):
            response = client.post('/v2/live-tour/action', json=body)
            if response.status_code != 503:
                return response
            sleep(0.02)
        return response
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, requests))
    assert sorted(response.status_code for response in results) == ([200,409] if same_area else [200,200]), [r.text for r in results]
    after, _ = saved(database)
    if same_area:
        rejected = next(response for response in results if response.status_code == 409)
        assert rejected.json()['detail']['code'] == 'LIVE_TOUR_AREA_CHANGED'
        assert len(area(after)['beds']) == len(area(before)['beds']) + 1
    else:
        for name in ('1','2'):
            assert len(area(after,name)['beds']) == len(area(before,name)['beds']) + 1
    assert after['employees'] == before['employees'] and after['invoices'] == before['invoices']

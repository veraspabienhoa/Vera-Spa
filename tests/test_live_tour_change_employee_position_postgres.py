"""Persisted HTTP replacement restores the queue once, including request replay."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee
from test_live_tour_change_employee_position import book_and_start, order
from test_live_tour_day_rollover_postgres import booking_api
from test_live_tour_resource_postgres import database


@pytest.mark.parametrize('intervening_start', [False, True])
@pytest.mark.parametrize('history_size', [0, 400])
def test_replacement_api_persists_original_slot_and_replay_does_not_move_it_again(
        database, booking_api, monkeypatch, intervening_start, history_size):
    client, clock = booking_api
    source_id = 'e2' if intervening_start else 'e1'
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        seeded = deepcopy(before)
        seeded['employees'] = [employee(f'e{i}', f'Test Worker {i}') for i in range(1, 5)]
        for index, row in enumerate(seeded['employees']):
            row['board_started_at'] = live._iso(NOW - timedelta(minutes=40-index*10))
        expected_slot = order(seeded).index(source_id)
        prior_clock = next(row['board_started_at'] for row in seeded['employees'] if row['id'] == source_id)
        book_and_start(seeded, source_id)
        if intervening_start:
            book_and_start(seeded, 'e1', minute=1, room='2.1')
        seeded['invoices'] = [{'id': f'old-{i}', 'total': 100, 'entries': [{'note': 'history ' * 100}]} for i in range(history_size)]
        seeded['reports'] = [{'id': f'report-{i}', 'invoice_id': f'old-{i}', 'total': 100} for i in range(history_size)]
        seeded['idempotency'] = {f'old-key-{i}': {'action': 'checkout', 'status': 'completed', 'result': {'invoice': row}} for i, row in enumerate(seeded['invoices'])}
        revision = store.write(conn, before, seeded, 'test')
    clock[0] = NOW + timedelta(minutes=80)
    body = {'action': 'change_employee', 'expected_revision': revision,
            'idempotency_key': 'restore-tour-position-once', 'response_view': 'board',
            'payload': {'employee_id': source_id, 'target_employee_id': 'e4'}}
    original_read = store.read
    reads = []
    def bounded_read(conn, collections=None, **kwargs):
        assert collections is not None or kwargs.get('profile') == 'operational'
        result = original_read(conn, collections, **kwargs)
        snapshot = result[0]
        assert snapshot['invoices'] == snapshot['reports'] == snapshot['audit'] == []
        assert set(snapshot.get('idempotency', {})) <= {body['idempotency_key']}
        if kwargs.get('profile') == 'operational':
            assert conn.info['live_tour_exclusive'] is True  # Restore may reorder other employees.
        reads.append(len(json.dumps(snapshot)))
        return result
    monkeypatch.setattr(store, 'read', bounded_read)
    response = client.post('/v2/live-tour/action', json=body)
    monkeypatch.setattr(store, 'read', original_read)
    assert response.status_code == 200, response.text
    assert len(reads) <= 3 and max(reads) < 100_000
    assert [row['_employee_id'] for row in response.json()['records']].index(source_id) == expected_slot
    with database.begin() as conn:
        persisted, saved_revision, _ = store.read(conn)
    assert order(persisted).index(source_id) == expected_slot
    source = next(row for row in persisted['employees'] if row['id'] == source_id)
    target = next(row for row in persisted['employees'] if row['id'] == 'e4')
    assert source['board_started_at'] == prior_clock
    assert source['tour_count'] == 0 and target['tour_count'] == 1
    assert not source['service'] and target['started_at'] == live._iso(NOW)
    for key in ('invoices', 'pending', 'reports', 'combo_usage'):
        assert persisted[key] == seeded[key], 'Replacing an employee must not create or edit a bill/ledger'
    assert len([item for item in persisted['audit'] if item['action'] == 'change_employee']) == 1
    replay = client.post('/v2/live-tour/action', json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()['duplicate'] is True
    assert [row['_employee_id'] for row in replay.json()['records']].index(source_id) == expected_slot
    stale = client.post('/v2/live-tour/action', json={**body, 'idempotency_key': 'stale-tour-position-request'})
    assert stale.status_code == 409
    with database.begin() as conn:
        current, current_revision, _ = store.read(conn)
    assert current == persisted and current_revision == saved_revision

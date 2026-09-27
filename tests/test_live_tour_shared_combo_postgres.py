"""Shared-room reservations are atomic and serialize on the combo owner."""
import pytest

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee
from test_live_tour_combo_booking import setup, booking
from test_live_tour_day_rollover_postgres import booking_api
from test_live_tour_resource_postgres import database


@pytest.mark.parametrize('shortage', [False, True])
def test_shared_combo_room_booking_rejects_shortage_atomically_and_cannot_oversell(database, booking_api, shortage):
    client, clock = booking_api
    clock[0] = NOW
    fixture, _, body_service, owner, owned = setup()
    fixture['employees'].extend([employee('e3', 'Test 3'), employee('e4', 'Test 4')])
    owned['remaining'] = 1 if shortage else 2
    for part in owned['component_balances']:
        part['remaining'] = owned['remaining'] if part['service_id'] == body_service['id'] else 0
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        seeded = {**before, **fixture}
        revision = store.write(conn, before, seeded, 'test')
        canonical, _, _ = store.read(conn)
    rows = [{**booking(owner, owned, body_service, worker), 'room': room}
            for worker, room in [('e1', '1.1'), ('e2', '1.2')]]
    payload = {'bookings': rows}
    request = {'action': 'multi_booking', 'payload': payload, 'response_view': 'board',
               'expected_revision': revision, 'idempotency_key': 'shared-room-combo-123'}
    response = client.post('/v2/live-tour/action', json=request)
    if shortage:
        assert response.status_code == 409, response.text
        with database.begin() as conn:
            current, actual_revision, _ = store.read(conn)
        assert current == canonical and actual_revision == revision
        return
    assert response.status_code == 200, response.text
    replay = client.post('/v2/live-tour/action', json=request)
    assert replay.status_code == 200 and replay.json()['duplicate'] is True
    with database.begin() as conn:
        current, version, _ = store.read(conn)
    customer = current['customers'][0]
    assert live._available_combo(current, customer['id'], customer['combo_purchases'][0])['remaining'] == 0
    assert sum(row.get('combo_reserved_units', 0) for row in current['employees']) == 2
    assert current['invoices'] == canonical['invoices']
    assert current['combo_usage'] == canonical['combo_usage']
    assert len([row for row in current['audit'] if row['action'] == 'multi_booking']) == 1
    contender = {**request, 'expected_revision': version, 'idempotency_key': 'other-room-combo-456',
        'payload': {'bookings': [{**row, 'employee_id': worker, 'room': room}
                    for row, worker, room in zip(rows, ['e3', 'e4'], ['2.1', '2.2'])]}}
    # Different rooms and workers still share the customer reservation lock.
    with database.begin() as held:
        store.begin_action(held, 'multi_booking', payload, version, 'held-combo-lock',
                           live._counter_business_date(NOW).isoformat(), compact=True)
        assert client.post('/v2/live-tour/action', json=contender).status_code == 503
    assert client.post('/v2/live-tour/action', json=contender).status_code == 409
    with database.begin() as conn:
        final, final_revision, _ = store.read(conn)
    assert final == current and final_revision == version

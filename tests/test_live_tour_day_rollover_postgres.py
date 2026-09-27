"""Real API/transaction regressions for the 11:10 Vietnam business-day boundary."""
from copy import deepcopy
from datetime import timedelta
import json
import math
from time import perf_counter

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import event

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee
from test_live_tour_resource_postgres import database


@pytest.fixture
def booking_api(database, monkeypatch):
    clock = [NOW.replace(hour=11, minute=10, second=0)]

    class Identity(BaseModel):
        employee_username: str = 'admin'
        full_name: str = 'Test operator'
        role: str = 'admin'

    class Clock(live.datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    monkeypatch.setattr(live, 'datetime', Clock)
    app = FastAPI()
    live.install_live_tour_routes(
        app, engine_instance=lambda: database, current_identity=lambda: Identity(),
        require_feature=lambda *args: None, feature_allowed=lambda *args: True,
        identity_type=Identity,
    )
    with TestClient(app) as client:
        yield client, clock


def seed(database, *, history=0, day_offset=-1):
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        state = deepcopy(before)
        state['business_date'] = (NOW.date() + timedelta(days=day_offset)).isoformat()
        # The independent counter rollover already ran at 10:00.
        state['counter_business_date'] = NOW.date().isoformat()
        state['employees'] = [employee(f'e{i}', f'Test {i}') for i in range(1, 43)]
        service = next(row for row in state['services'] if row['name'] in {'VIP 90 PR', '90 PR VIP'})
        service.update(name='90 PR VIP', price=350000)
        state['audit'] = [{'id': f'audit-{i}', 'action': 'fixture'} for i in range(history)]
        state['invoices'] = [{'id': f'invoice-{i}', 'total': 350000} for i in range(history)]
        state['reports'] = [{'id': f'report-{i}', 'total': 350000} for i in range(history)]
        state['idempotency'] = {'prior-payment': {'status': 'completed', 'result': {'total': 350000}}}
        revision = store.write(conn, before, state, 'fixture')
        return revision


def body(revision, key='rollover-booking-once'):
    return {'action': 'booking', 'expected_revision': revision, 'idempotency_key': key,
            'response_view': 'board', 'payload': {'employee_id': 'e1', 'room': '20.1', 'service': '90 PR VIP'}}


def saved(database):
    with database.connect() as conn:
        return store.read(conn)


@pytest.mark.parametrize('seconds', [-1, 0, 1, 6000])
def test_vip_booking_across_1110_commits_once_and_preserves_other_resources(database, booking_api, seconds):
    client, clock = booking_api
    clock[0] += timedelta(seconds=seconds)
    revision = seed(database, history=12)
    before, _, versions = saved(database)
    request = body(revision)
    response = client.post('/v2/live-tour/action', json=request)
    assert response.status_code == 200, response.text
    replay = client.post('/v2/live-tour/action', json=request)
    assert replay.status_code == 200 and replay.json()['duplicate'] is True, replay.text
    after, current, new_versions = saved(database)
    assert current == revision + 1
    assert after['business_date'] == live._business_date(clock[0]).isoformat()
    booked = next(row for row in after['employees'] if row['id'] == 'e1')
    assert booked['service'] == '90 PR VIP' and booked['room'] == '20.1'
    assert booked['status'] == 'Đang chờ' and not booked['customer_id']
    assert len(after['audit']) == len(before['audit']) + 1
    for kind in ('invoices', 'reports', 'customers', 'rooms', 'services'):
        assert after[kind] == before[kind]
    assert after['idempotency']['prior-payment'] == before['idempotency']['prior-payment']
    for row in before['employees'][1:]:
        assert next(item for item in after['employees'] if item['id'] == row['id']) == row
        assert new_versions[('employees', row['id'])] == versions[('employees', row['id'])]
    assert client.post('/v2/live-tour/action', json=body(revision, 'new-stale-booking')).status_code == 409
    assert saved(database)[1] == current


def test_other_metadata_still_requires_exclusive_configuration_lock(database):
    revision = seed(database)
    before = saved(database)
    with pytest.raises(HTTPException) as rejected:
        with database.begin() as conn:
            state, _, fresh = store.begin_action(conn, 'set_vip', {'employee_id': 'e1'}, revision,
                                                  'config-bypass-test', NOW.date().isoformat(), compact=True)
            assert fresh
            changed = deepcopy(state)
            changed['payment_settings']['employee_change_enabled'] = False
            store.write(conn, state, changed, 'test')
    assert rejected.value.status_code == 409
    assert 'Cấu hình đã đổi' in rejected.value.detail
    assert saved(database) == before


def test_1000_counter_transition_is_not_bypassed(database, booking_api):
    client, _ = booking_api
    revision = seed(database)
    with database.begin() as conn:
        store.lock(conn)
        state, _, _ = store.read(conn)
        changed = deepcopy(state)
        changed['counter_business_date'] = (NOW.date() - timedelta(days=1)).isoformat()
        revision = store.write(conn, state, changed, 'fixture')
    before = saved(database)
    response = client.post('/v2/live-tour/action', json=body(revision))
    assert response.status_code == 409 and 'chuyển ngày' in response.text
    assert saved(database) == before


def test_disjoint_actions_at_cutoff_do_not_rewind_business_date(database):
    revision = seed(database, day_offset=-2)
    # Both transactions discover the older metadata; the pre-cutoff action
    # publishes last. Its server timestamp must not rewind the published day.
    with database.begin() as older:
        old, _, fresh = store.begin_action(older, 'booking', {'employee_id': 'e1', 'room': '20.1'},
                                           revision, 'before-cutoff', NOW.date().isoformat(), compact=True)
        assert fresh
        old_change = deepcopy(old)
        live._apply_action(old_change, 'booking', body(revision)['payload'], 'test', NOW.replace(hour=11, minute=9))
        with database.begin() as newer:
            new, _, fresh = store.begin_action(newer, 'booking', {'employee_id': 'e2', 'room': '21.1'},
                                               revision, 'after-cutoff', NOW.date().isoformat(), compact=True)
            assert fresh
            new_change = deepcopy(new)
            live._apply_action(new_change, 'booking', {'employee_id': 'e2', 'room': '21.1', 'service': '90 PR VIP'},
                               'test', NOW.replace(hour=11, minute=10))
            store.write(newer, new, new_change, 'test')
        store.write(older, old, old_change, 'test')
    state, current, _ = saved(database)
    assert state['business_date'] == NOW.date().isoformat()
    assert current == revision + 2 and len(state['audit']) == 2
    assert all(row['status'] == 'Đang chờ' for row in state['employees'][:2])


def test_rollover_write_failure_rolls_back_booking_and_receipt(database, booking_api, monkeypatch):
    client, _ = booking_api
    revision = seed(database)
    before = saved(database)
    write = store.write

    def abort(*args):
        write(*args)
        raise HTTPException(503, 'Injected failure before commit')

    monkeypatch.setattr(store, 'write', abort)
    assert client.post('/v2/live-tour/action', json=body(revision)).status_code == 503
    assert saved(database) == before
    monkeypatch.setattr(store, 'write', write)
    assert client.post('/v2/live-tour/action', json=body(revision)).status_code == 200
    assert saved(database)[1] == revision + 1


def test_booking_work_measurement(database, booking_api):
    """Count driver executions/returned rows, not wire round trips or scanned rows.

    In-process HTTP + local CI PostgreSQL; authentication is a fixture. Setup,
    resets and verification reads are excluded. Latency is reported, not gated.
    """
    client, _ = booking_api
    results = []
    for history in (0, 3000):
        for day_offset in (0, -1):
            samples = []
            for index in range(10):
                revision = seed(database, history=history, day_offset=day_offset)
                observed = {'sql': 0, 'rows_returned': 0, 'rows_written': 0}

                def counted(conn, cursor, statement, parameters, context, executemany):
                    observed['sql'] += 1
                    count = max(0, cursor.rowcount)
                    if statement.lstrip().upper().startswith('SELECT'):
                        observed['rows_returned'] += count
                    elif statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                        observed['rows_written'] += count

                event.listen(database, 'after_cursor_execute', counted)
                started = perf_counter()
                try:
                    response = client.post('/v2/live-tour/action', json=body(revision, f'measure-{history}-{day_offset}-{index}'))
                finally:
                    elapsed = (perf_counter() - started) * 1000
                    event.remove(database, 'after_cursor_execute', counted)
                samples.append({**observed, 'ms': elapsed, 'status': response.status_code, 'bytes': len(response.content)})
            times = sorted(row['ms'] for row in samples)
            results.append({'history_per_collection': history, 'rollover': day_offset == -1, 'samples': len(samples),
                            'statuses': sorted({row['status'] for row in samples}),
                            'sql': sorted({row['sql'] for row in samples}),
                            'rows_returned': sorted({row['rows_returned'] for row in samples}),
                            'rows_written': sorted({row['rows_written'] for row in samples}),
                            'bytes_min_max': [min(row['bytes'] for row in samples), max(row['bytes'] for row in samples)],
                            'p50_ms': round(times[math.ceil(len(times) * .5) - 1], 2),
                            'p95_ms': round(times[math.ceil(len(times) * .95) - 1], 2)})
    print('BOOKING_MEASUREMENT=' + json.dumps(results, sort_keys=True))
    assert all(row['statuses'] == [200] for row in results), results
    # Historical growth must not expand the booking read/write work.
    for small, large in zip(results[:2], results[2:]):
        for key in ('sql', 'rows_returned'):
            assert small[key] == large[key], (key, results)
        # A full audit ring also expires one old audit row, never all history.
        assert max(large['rows_written']) <= max(small['rows_written']) + 1

"""Receipt cutover, atomicity, compatibility and isolated write measurements."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import perf_counter
from statistics import median
import hashlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
import vera_live_tour_receipts as receipts
import vera_live_tour_relational as relational
import vera_live_tour_resource_store as store
import vera_live_tour_maintenance as maintenance
import test_live_tour_resource_postgres as existing
from test_live_tour_resource_postgres import database
from test_live_tour_backend import NOW


def seed(conn, archive):
    store.lock(conn)
    before, _, _ = store.read(conn)
    after = deepcopy(before)
    after['idempotency'] = archive
    return store.write(conn, before, after, 'fixture')


def test_cutover_roundtrip_preserves_unknown_fields_and_current_receipts(database):
    archive = {'payment': {'action': 'checkout', 'status': 'legacy-status',
                          'result': {'invoice': {'id': 'invoice-1', 'total': 450000}},
                          'future_field': [1, None, {'x': 'giữ nguyên'}]},
               'null-entry': None, 'old-entry': ['legacy', 42]}
    with database.begin() as conn:
        seed(conn, archive)
        before = store.read(conn)[0]
        assert receipts.migrate(conn)['changed']
        assert not receipts.migrate(conn)['changed']
        after = store.read(conn)[0]
        assert after.pop(receipts.MARKER) is True
        assert before == after
        assert relational.load_state(conn)[0]['idempotency'] == archive
        for key, value in archive.items():
            scoped = store.read(conn, receipt_key=key, profile='operational')[0]
            assert scoped['idempotency'] == {key: value}
        assert store.read(conn, receipt_key='missing', profile='operational')[0]['idempotency'] == {}
        meta = conn.execute(text(f'SELECT payload FROM {relational.META_TABLE}')).scalar_one()
        assert 'idempotency' not in meta
        receipts.write_changes(conn, {'new': {'action': 'start', 'result': {'ok': True}}}, [])
        assert receipts.migrate(conn, rollback=True)['changed']
        assert not receipts.migrate(conn, rollback=True)['changed']
        restored = store.read(conn)[0]
        assert restored['idempotency'] == {**archive, 'new': {'action': 'start', 'result': {'ok': True}}}
        assert receipts.MARKER not in restored
        assert conn.execute(text(f'SELECT count(*) FROM {relational.MUTATION_TABLE}')).scalar_one() == 0


@pytest.mark.parametrize('statement', [
    "payload || jsonb_build_object('idempotency','{}'::jsonb)",
    "payload - '_receipt_rows_ready'",
])
def test_old_writer_is_rejected_atomically(database, statement):
    with database.begin() as conn:
        receipts.migrate(conn)
        original = store.read(conn)[:2]
    with pytest.raises(DBAPIError, match='receipt rows are authoritative'):
        with database.begin() as conn:
            receipts.write_changes(conn, {'must-rollback': {'action': 'checkout'}}, [])
            conn.execute(text(f'UPDATE {relational.META_TABLE} SET payload={statement}'))
    with database.connect() as conn:
        assert store.read(conn)[:2] == original


def test_migration_failure_rolls_back_and_reserved_records_are_not_overwritten(database):
    with pytest.raises(RuntimeError, match='injected'):
        with database.begin() as conn:
            seed(conn, {'old': {'action': 'checkout'}})
            receipts.migrate(conn)
            raise RuntimeError('injected')
    with database.begin() as conn:
        assert not receipts.ready(conn)
        assert conn.execute(text(f'SELECT count(*) FROM {relational.MUTATION_TABLE}')).scalar_one() == 0
        receipts.write_changes(conn, {'reserved': {'unknown': True}}, [])
    with pytest.raises(RuntimeError, match='unrecognized'):
        with database.begin() as conn:
            receipts.migrate(conn)
    with database.connect() as conn:
        assert not receipts.ready(conn)
        assert conn.execute(text(f'SELECT result FROM {relational.MUTATION_TABLE}')).scalar_one() == {'unknown': True}


def test_disjoint_receipt_writers_and_failed_business_write_are_atomic(database):
    with database.begin() as conn:
        receipts.migrate(conn)
        revision = store.read(conn)[1]
    barrier = Barrier(2)
    def edit(identifier):
        with database.begin() as conn:
            before, _, fresh = store.begin_action(conn, 'set_vip', {'employee_id': identifier},
                revision, 'key-'+identifier, existing.live._counter_business_date(NOW).isoformat(), compact=True)
            assert fresh
            after = deepcopy(before)
            existing.live._apply_action(after, 'set_vip', {'employee_id': identifier}, 'admin', NOW)
            after['idempotency']['key-'+identifier] = {'status': 'completed'}
            barrier.wait(timeout=5)
            return store.write(conn, before, after, 'admin')
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit, ['e1', 'e2'])) == [revision+1, revision+2]
    with database.connect() as conn:
        original = store.read(conn)[:2]
        assert set(original[0]['idempotency']) == {'key-e1', 'key-e2'}
        assert all(row['vip'] for row in original[0]['employees'])
    with pytest.raises(RuntimeError, match='abort'):
        with database.begin() as conn:
            store.lock(conn)
            before = store.read(conn)[0]
            after = deepcopy(before)
            after['employees'][0]['vip'] = False
            after['idempotency']['failed-write'] = {'status': 'completed'}
            store.write(conn, before, after, 'admin')
            raise RuntimeError('abort')
    with database.connect() as conn:
        assert store.read(conn)[:2] == original


@pytest.mark.parametrize('scenario', [
    existing.test_checkout_retry_is_idempotent_and_lists_read_current_canonical_storage,
    existing.test_start_retry_counts_tour_once_and_stale_new_request_is_rejected,
])
def test_financial_and_start_replays_in_row_format(database, monkeypatch, scenario):
    with database.begin() as conn:
        receipts.migrate(conn)
    scenario(database, monkeypatch)


def test_receipt_pruning_keeps_other_keys_in_row_format(database):
    with database.begin() as conn:
        receipts.migrate(conn)
    existing.test_receipt_pruning_removes_only_keys_from_its_snapshot(database)


def test_maintenance_verifies_full_parity_and_legacy_rollback_exports_rows(database):
    with database.connect() as conn:
        maintenance.acquire_fences(conn)
        conn.commit()
        assert maintenance.migrate_receipts(conn, rollback=False)['receipt_storage'] == 'rows'
        with conn.begin():
            receipts.write_changes(conn, {'paid': {'action': 'checkout', 'result': {'total': 100}}}, [])
        assert maintenance.migrate_receipts(conn, rollback=True)['receipt_storage'] == 'inline'
        assert maintenance.migrate_receipts(conn, rollback=False)['receipt_storage'] == 'rows'
        with conn.begin():
            existing.cutover(conn, rollback=True)
            aggregate = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='live_tour'")).scalar_one()
            assert aggregate['idempotency']['paid']['result']['total'] == 100
            assert receipts.MARKER not in aggregate
        conn.execute(text('SELECT pg_advisory_unlock_all()'))
        conn.commit()


def test_receipt_write_measurement(database):
    # Synthetic ~10 MB archive, never production data. Same mutation, reader and
    # commit path in both formats. No timing threshold on variable CI hardware.
    archive = {f'paid-{i}': {'action': 'checkout', 'status': 'completed',
        'result': {'invoice': {'id': f'invoice-{i}', 'notes': hashlib.shake_256(str(i).encode()).hexdigest(2500)}}}
        for i in range(2000)}
    with database.begin() as conn:
        seed(conn, archive)
    report = {'scope': 'isolated PostgreSQL synthetic archive; not production latency',
              'receipt_count': len(archive), 'samples_per_format': 7, 'formats': {}}
    for mode in ('inline', 'rows'):
        if mode == 'rows':
            with database.begin() as conn:
                receipts.migrate(conn)
        samples = []
        for index in range(7):
            with database.connect() as conn:
                store.lock(conn)
                key = f'measure-{mode}-{index}'
                before = store.read(conn, receipt_key=key, profile='operational')[0]
                after = deepcopy(before)
                after['employees'][0]['vip'] = not before['employees'][0].get('vip', False)
                after['idempotency'][key] = {'action': 'set_vip', 'status': 'completed'}
                started = perf_counter()
                store.write(conn, before, after, 'fixture')
                conn.commit()
                samples.append(round((perf_counter()-started)*1000, 3))
        with database.connect() as conn:
            size = conn.execute(text(f'SELECT octet_length(payload::text) FROM {relational.META_TABLE}')).scalar_one()
            saved = store.read(conn)[0]['idempotency']
            assert all(saved[key] == value for key, value in archive.items())
        report['formats'][mode] = {'write_commit_ms': samples, 'median_ms': median(samples), 'metadata_text_bytes': size}
    assert report['formats']['rows']['metadata_text_bytes'] < 100000
    assert report['formats']['inline']['metadata_text_bytes'] > 10000000
    report['median_write_speedup'] = round(report['formats']['inline']['median_ms']/report['formats']['rows']['median_ms'], 2)
    target = os.getenv('VERA_TEST_RECEIPT_MEASUREMENT_PATH')
    if target:
        Path(target).write_text(json.dumps(report, sort_keys=True))
    print('RECEIPT_WRITE_MEASUREMENT=' + json.dumps(report, sort_keys=True))

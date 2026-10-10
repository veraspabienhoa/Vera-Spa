"""CAS, permissions and atomic schedule batches, against isolated PostgreSQL.

Run with VERA_TEST_POSTGRES_URL (CI's disposable PostgreSQL service).
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, text

import vera_web_v2_work_schedule as schedule

DAY = date(2026, 10, 10)
ADMIN = SimpleNamespace(role='admin', employee_username='synthetic')


def row(username='a', revision=0, **extra):
    return schedule.ScheduleWriteRow(work_date=DAY, employee_username=username,
        department='letan', shift_code='Ca 1', expected_revision=revision, **extra)


def deletion(username, revision):
    return schedule.ScheduleDelete(work_date=DAY, employee_username=username, expected_revision=revision)


@pytest.fixture
def database(monkeypatch):
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('VERA_TEST_POSTGRES_URL required for real PostgreSQL concurrency tests')
    schema = 'schedule_test_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    monkeypatch.setattr(schedule, '_employee_catalog', lambda *_: [{'username': name} for name in ('a', 'b', 'c')])
    try:
        with engine.begin() as conn:
            schedule._ensure_schema(conn)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def endpoints(engine, *, permitted=True):
    app = FastAPI()
    schedule.install_work_schedule_routes(app, engine_instance=lambda: engine,
        current_identity=lambda: ADMIN, feature_allowed=lambda *_: permitted)
    routes = {(r.path, method): r.endpoint for r in app.routes for method in (r.methods or [])}
    return app, routes['/v2/work-schedule', 'PUT'], routes['/v2/work-schedule', 'DELETE']


def save(engine, rows=(), deletes=(), *, ident=ADMIN):
    return endpoints(engine)[1](schedule.ScheduleSave(rows=list(rows), deletes=list(deletes)), ident)


def revision(engine, username='a'):
    with engine.connect() as conn:
        return conn.execute(text('SELECT revision FROM vera_work_schedule WHERE employee_username=:name'),
                            {'name': username}).scalar_one_or_none()


def values(engine):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text('SELECT * FROM vera_work_schedule ORDER BY employee_username')).mappings()]


def test_http_writes_reject_missing_negative_or_noninteger_revision_without_database():
    app, _, _ = endpoints(None)
    client = TestClient(app)
    payload = row().model_dump(mode='json')
    for invalid in (None, -1, True, 1.25, '0'):
        candidate = dict(payload)
        if invalid is None:
            candidate.pop('expected_revision')
        else:
            candidate['expected_revision'] = invalid
        assert client.put('/v2/work-schedule', json={'rows': [candidate]}).status_code == 422
    assert client.delete('/v2/work-schedule', params={'work_date': DAY.isoformat(), 'employee_username': 'a'}).status_code == 422
    with pytest.raises(ValidationError):
        schedule.ScheduleDelete(work_date=DAY, employee_username='a', expected_revision=0)


def test_import_validation_still_accepts_unversioned_preview_rows():
    data = row().model_dump()
    data.pop('expected_revision')
    assert schedule.ScheduleRow(**data).shift_code == 'Ca 1'


def test_create_update_readback_and_stale_update(database):
    first = save(database, [row()])['revisions'][0]['revision']
    second = save(database, [row(revision=first, note='new')])['revisions'][0]['revision']
    assert second > first > 0
    before = values(database)
    with pytest.raises(HTTPException) as caught:
        save(database, [row(revision=first, note='stale')])
    assert caught.value.status_code == 409
    assert caught.value.detail['conflicts'] == [{'work_date': DAY.isoformat(), 'employee_username': 'a'}]
    assert values(database) == before
    app, _, _ = endpoints(database)
    response = TestClient(app).get('/v2/work-schedule', params={'start': DAY, 'end': DAY, 'department': 'letan'})
    assert response.status_code == 200
    assert response.json()['rows'][0]['revision'] == second


def test_simultaneous_create_same_cell_has_exactly_one_winner(database):
    barrier = Barrier(2)
    # Pause both transactions after observing the same empty cell.
    def after_select(conn, cursor, statement, params, context, many):
        if 'SELECT department, revision FROM vera_work_schedule' in statement:
            barrier.wait(timeout=10)
    event.listen(database, 'after_cursor_execute', after_select)
    def create(note):
        try:
            save(database, [row(note=note)])
            return 200
        except HTTPException as exc:
            return exc.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(create, ['first', 'second']))
    finally:
        event.remove(database, 'after_cursor_execute', after_select)
    assert sorted(statuses) == [200, 409]
    assert len(values(database)) == 1


def test_simultaneous_updates_same_cell_have_exactly_one_winner(database):
    initial = save(database, [row()])['revisions'][0]['revision']
    barrier = Barrier(2)
    def update(note):
        barrier.wait(timeout=10)
        try:
            save(database, [row(revision=initial, note=note)])
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, ['first', 'second'])) == [200, 409]
    assert values(database)[0]['note'] in ('first', 'second')


def test_disjoint_cells_can_be_saved_concurrently(database):
    initial = save(database, [row('a'), row('b')])
    revisions = {r['employee_username']: r['revision'] for r in initial['revisions']}
    barrier = Barrier(2)
    def after_lock(conn, cursor, statement, params, context, many):
        if 'SELECT department, revision FROM vera_work_schedule' in statement:
            barrier.wait(timeout=10)
    event.listen(database, 'after_cursor_execute', after_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda name: save(database, [row(name, revisions[name], note=name)]), ['a', 'b']))
    finally:
        event.remove(database, 'after_cursor_execute', after_lock)
    assert all(result['saved'] == 1 for result in results)
    assert [r['note'] for r in values(database)] == ['a', 'b']


def test_conflict_rolls_back_upserts_and_deletes_together(database):
    save(database, [row('a'), row('b'), row('c')])
    before = values(database)
    with pytest.raises(HTTPException) as caught:
        save(database, [row('b', revision(database, 'b'), note='must roll back'), row('c', 0)],
             [deletion('a', revision(database, 'a'))])
    assert caught.value.status_code == 409
    assert values(database) == before


def test_update_cannot_recreate_deleted_cell_and_old_delete_cannot_remove_recreated_cell(database):
    old = save(database, [row()])['revisions'][0]['revision']
    assert save(database, deletes=[deletion('a', old)])['deleted'] == 1
    with pytest.raises(HTTPException) as caught:
        save(database, [row(revision=old)])
    assert caught.value.status_code == 409
    new = save(database, [row(note='recreated')])['revisions'][0]['revision']
    assert new > old
    _, _, delete = endpoints(database)
    with pytest.raises(HTTPException) as caught:
        delete(DAY, 'a', old, ADMIN)
    assert caught.value.status_code == 409
    assert values(database)[0]['note'] == 'recreated'
    assert delete(DAY, 'a', new, ADMIN)['deleted'] == 1


def test_mixed_duplicate_or_whitespace_keys_rejected_before_writes(database):
    rev = save(database, [row()])['revisions'][0]['revision']
    before = values(database)
    with pytest.raises(HTTPException) as caught:
        save(database, [row(' a ', rev)], [deletion('a', rev)])
    assert caught.value.status_code == 400
    assert values(database) == before


def test_existing_department_permissions_checked_before_revision_conflict(database):
    save(database, [schedule.ScheduleWriteRow(**{**row().model_dump(), 'department': 'locker'})])
    reception = SimpleNamespace(role='letan', employee_username='operator')
    with pytest.raises(HTTPException) as caught:
        save(database, [row()], ident=reception)
    assert caught.value.status_code == 403
    with pytest.raises(HTTPException) as caught:
        save(database, deletes=[deletion('a', revision(database))], ident=reception)
    assert caught.value.status_code == 403


def test_version_one_upgrade_and_other_sql_writers_get_revisions(database):
    save(database, [row()])
    with database.begin() as conn:
        conn.execute(text('DROP TRIGGER vera_work_schedule_revision ON vera_work_schedule'))
        conn.execute(text('ALTER TABLE vera_work_schedule DROP COLUMN revision'))
        conn.execute(text('DROP SEQUENCE vera_work_schedule_revision_seq'))
        conn.execute(text("UPDATE vera_read_path_schema SET version=1 WHERE component='work_schedule'"))
        schedule._ensure_schema(conn)
        assert conn.execute(text("SELECT version FROM vera_read_path_schema WHERE component='work_schedule'")).scalar_one() == 2
        old = conn.execute(text("SELECT revision FROM vera_work_schedule WHERE employee_username='a'")).scalar_one()
        assert old > 0
        conn.execute(text("UPDATE vera_work_schedule SET note='maintenance' WHERE employee_username='a'"))
    assert revision(database) > old
    with pytest.raises(HTTPException) as caught:
        save(database, [row(revision=old)])
    assert caught.value.status_code == 409

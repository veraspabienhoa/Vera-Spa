from copy import deepcopy

import pytest
from sqlalchemy import event, text
import vera_live_tour_query as query_store

import vera_live_tour_resource_store as store
import vera_live_tour_relational as relational
from test_live_tour_resource_postgres import database
from test_live_tour_backend import employee


@pytest.mark.parametrize('query_ready', [False, True])
def test_fifty_employee_changes_use_one_write_and_one_history_insert(database, query_ready):
    with database.begin() as conn:
        if query_ready:
            query_store.ensure_schema(conn)
        store.lock(conn)
        before, _, _ = store.read(conn)
        after = deepcopy(before)
        after['employees'] = [employee(f'e{i+1}', f'Worker {i}') for i in range(50)]
        store.write(conn, before, after, 'fixture')
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        after = deepcopy(before)
        for worker in after['employees']:
            worker['vip'] = not worker['vip']
        calls = []
        def count(_conn, _cursor, statement, *_args):
            calls.append(statement)
        event.listen(conn, 'before_cursor_execute', count)
        try:
            revision = store.write(conn, before, after, 'batch-test')
        finally:
            event.remove(conn, 'before_cursor_execute', count)
        # Readiness adds a fixed catalog/version check, never per-worker SQL.
        writes = [sql for sql in calls if sql.lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))]
        assert len(writes) == 3  # publication, employee batch, history batch
        assert len(calls) == 3 + (2 if query_ready else 1)
        assert sum('INSERT INTO vera_live_tour_employee(' in sql for sql in writes) == 1
        assert sum('INSERT INTO vera_live_tour_board_history' in sql for sql in writes) == 1
    with database.connect() as conn:
        state, actual_revision, _ = store.read(conn)
        assert actual_revision == revision
        assert state['employees'] == after['employees']
        if query_ready:
            assert query_store.verify_projections(conn)['ok']
            assert conn.execute(text("SELECT COUNT(*) FROM vera_live_tour_employee WHERE deleted_at IS NULL AND query_hash=payload_hash")).scalar_one() == 50
        rows = conn.execute(text(f'''SELECT employee_id,before_payload,after_payload
            FROM {relational.BOARD_HISTORY_TABLE} WHERE actor='batch-test' ORDER BY id''')).mappings().all()
    assert len(rows) == 50
    assert [row['employee_id'] for row in rows] == sorted(row['id'] for row in after['employees'])
    assert all(row['before_payload']['vip'] is False and row['after_payload']['vip'] is True for row in rows)

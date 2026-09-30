"""Use the actual locked projection/writer and canonical absence source rows."""
from datetime import timedelta

import pytest
from sqlalchemy import event, text

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_resource_postgres import database
from test_live_tour_unexcused_return import DAY, fixture, directory, leaves, order, UNEXCUSED_REASONS


@pytest.mark.parametrize('corrected', [False, True])
@pytest.mark.parametrize('reason', UNEXCUSED_REASONS)
def test_return_projection_persists_once_and_rechecks_source_in_one_query(database, corrected, reason):
    source = leaves(reason)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE leave_records(id bigint PRIMARY KEY, employee_name text, leave_reason text, leave_type text, leave_date date, detail text, record_uid text, source_row int)'))
        for row in source:
            conn.execute(text('INSERT INTO leave_records(id,employee_name,leave_reason,leave_date,detail,record_uid,source_row) VALUES(:id,:employee_name,:leave_reason,:leave_date,:detail,:record_uid,:source_row)'), row)
        store.lock(conn)
        before, _, _ = store.read(conn)
        seeded = {**before, **fixture()}
        store.write(conn, before, seeded, 'fixture')
        live._read_state(conn, DAY, for_update=True, directory_records=directory(DAY))
    if corrected:
        with database.begin() as conn:
            conn.execute(text("UPDATE leave_records SET leave_reason='Nghỉ CÓ phép' WHERE employee_name='Test 1'"))
    now = (DAY + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(database, 'before_cursor_execute', capture)
    try:
        with database.begin() as conn:
            store.lock(conn)
            live._read_state(conn, now, for_update=True, directory_records=directory(now, (1, 2, 3, 4, 5)), leave_records=[])
    finally:
        event.remove(database, 'before_cursor_execute', capture)
    queries = [sql for sql in statements if 'FROM leave_records' in sql]
    assert len(queries) == 1 and 'return_day' in queries[0]
    with database.begin() as conn:
        persisted, revision, _ = store.read(conn)
    assert order(persisted, now) == (['e1', 'e4', 'e5', 'e2', 'e3'] if corrected else ['e4', 'e5', 'e1', 'e2', 'e3'])
    with database.begin() as conn:
        store.lock(conn)
        _, repeated = live._read_state(conn, now + timedelta(minutes=5), for_update=True,
            directory_records=directory(now, (1, 2, 3, 4, 5)), leave_records=[])
    assert repeated == revision
    with database.begin() as conn:
        after, final_revision, _ = store.read(conn)
    assert after == persisted and final_revision == revision
    for name in ('invoices', 'reports', 'pending', 'combo_usage'):
        assert after[name] == seeded[name]

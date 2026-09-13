"""Attendance must complete with one connection, including penalty recording."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

import vera_auto_check as auto_check
import vera_auto_penalty_notifications as notifications
import vera_web_v2_break_return_penalty as returned
import vera_web_v2_outside_leave_rule as outside
import vera_web_v2_snapshot as snapshot


class App:
    state = None

    def __init__(self):
        self.state = SimpleNamespace()

    def get(self, _path):
        return lambda function: function


@pytest.mark.parametrize('kind', ['outside', 'return'])
@pytest.mark.parametrize('write_fails', [False, True])
def test_penalty_projection_reuses_connection_and_isolates_failed_write(monkeypatch, tmp_path, kind, write_fails):
    # A second checkout would raise TimeoutError. This reproduces the nested
    # checkout even without PostgreSQL or multiple HTTP clients.
    engine = create_engine(f'sqlite:///{tmp_path / "test.db"}', poolclass=QueuePool,
                           pool_size=1, max_overflow=0, pool_timeout=0.01)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE recorded (id INTEGER PRIMARY KEY)'))
    today = datetime.now(outside.VN_TZ).date()
    records = [{'date': today.strftime('%d/%m/%Y'), 'employee_name': 'test-worker',
                'break_enabled': True, 'break_out': '13:00:00', 'break_in': '15:00:00',
                'break_planned_minutes': 90}]
    reason = {'name': 'Ra ngoài vào muộn dưới 120 phút', 'penalty': 100000}
    holder = {}

    def catalog(conn):
        assert conn is holder['connection']
        conn.execute(text('SELECT 1'))
        return {'test': reason}

    def save(conn, **_kwargs):
        assert conn is holder['connection']
        conn.execute(text('INSERT INTO recorded(id) VALUES (1)'))
        if write_fails:
            raise ValueError('simulated recording failure')
        return True, 'ADDED'

    def forbid_push(*_args, **_kwargs):
        raise AssertionError('Push must be delivered after the transaction by the existing worker')

    monkeypatch.setattr(auto_check, 'load_catalog', catalog)
    monkeypatch.setattr(auto_check, 'save_violation', save)
    monkeypatch.setattr(notifications, 'notify_pending', forbid_push)
    if kind == 'outside':
        monkeypatch.setattr(outside, '_restriction_map', lambda *_: {
            (today, outside._norm('test-worker')): {'reasons': ['Đi trễ CÓ phép']},
        })
        monkeypatch.setattr(outside, '_violation_for', lambda **_: (reason, 60, 'test'))
        project = lambda conn: outside._apply_restrictions_and_penalties(lambda: engine, conn, records, today, today)
        prefix = 'break_auto_penalty'
    else:
        monkeypatch.setattr(snapshot, '_records', lambda *_: records)
        monkeypatch.setattr(auto_check, 'outside_reason', lambda *_: reason)
        returned.install_break_return_penalty(App(), engine_instance=lambda: engine,
                                             api_module=None, vn_tz=outside.VN_TZ)
        project = lambda conn: snapshot._records(conn, today, today)
        prefix = 'break_return_penalty'
    try:
        with engine.begin() as conn:
            holder['connection'] = conn
            output = project(conn)
            assert engine.pool.checkedout() == 1
            assert conn.execute(text('SELECT 1')).scalar_one() == 1
            if write_fails:
                assert prefix + '_error' in output[0]
            else:
                assert output[0][prefix + '_status'] == 'ADDED'
        with engine.connect() as conn:
            assert conn.execute(text('SELECT COUNT(*) FROM recorded')).scalar_one() == int(not write_fails)
    finally:
        engine.dispose()

from contextlib import contextmanager
from decimal import Decimal

import vera_postgres_job_queue as queue


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row

    def scalar_one_or_none(self):
        return self.row


class FakeConnection:
    def __init__(self, row=None):
        self.row = row or {}
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return FakeResult(self.row)


class FakeEngine:
    def __init__(self, row=None):
        self.connection = FakeConnection(row)

    @contextmanager
    def connect(self):
        yield self.connection

    @contextmanager
    def begin(self):
        yield self.connection


def test_ensure_schema_runs_inside_transaction(monkeypatch):
    engine = FakeEngine()
    seen = []
    monkeypatch.setattr(queue, 'ensure_schema_conn', lambda conn: seen.append(conn))
    queue.ensure_schema(lambda: engine)
    assert seen == [engine.connection]


def test_health_metrics_normalizes_operational_signals():
    engine = FakeEngine({
        'retry': 2,
        'failed': 1,
        'stale_processing': 1,
        'last_success_age': Decimal('12.34'),
        'oldest_pending': Decimal('45.67'),
    })
    assert queue.health_metrics(lambda: engine, 'live_tour_projection') == {
        'last_success_age': 12.3,
        'oldest_pending': 45.7,
        'retry': 2,
        'failed': 1,
        'stale_processing': 1,
    }
    statement, params = engine.connection.calls[-1]
    assert "status='processing'" in statement
    assert "INTERVAL '10 minutes'" in statement
    assert params == {'queue_name': 'live_tour_projection'}


def test_recovery_skips_live_transactions_and_records_only_a_selected_job():
    engine = FakeEngine({'id': 42, 'status': 'processing'})
    assert queue.recover_expired(lambda: engine, 'live_tour_projection', 'admin-test') == {'requeued': 1}
    selection, params = engine.connection.calls[0]
    assert 'FOR UPDATE SKIP LOCKED LIMIT 1' in selection
    assert "locked_at < NOW() - INTERVAL '10 minutes'" in selection
    assert params == {'queue_name': 'live_tour_projection'}
    update, params = engine.connection.calls[1]
    assert 'WHERE id=:id' in update
    assert params == {'id': 42}
    audit, params = engine.connection.calls[2]
    assert 'vera_background_job_recovery' in audit
    assert params['job_id'] == 42
    assert params['actor'] == 'admin-test'


def test_expired_owner_cannot_mark_reclaimed_job_done():
    engine = FakeEngine()
    item = {'id': 42, 'locked_at': 'old-lease'}
    queue.mark_done(lambda: engine, item)
    statement, params = engine.connection.calls[0]
    assert "status='processing' AND locked_at=:locked_at" in statement
    assert params == {'id': 42, 'locked_at': 'old-lease'}

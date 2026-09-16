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

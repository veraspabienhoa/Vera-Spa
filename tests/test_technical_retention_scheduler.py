from contextlib import asynccontextmanager
from threading import Event

from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_technical_retention_scheduler as scheduler


def test_background_checks_honor_due_flag_and_retry_after_error(monkeypatch):
    calls = []
    class Stop:
        checks = 0
        def is_set(self): return False
        def wait(self, seconds):
            calls.append(('wait', seconds))
            self.checks += 1
            return self.checks >= 3
    def run(engine, **kwargs):
        calls.append(('run', engine, kwargs))
        if sum(row[0] == 'run' for row in calls) == 1:
            raise RuntimeError('synthetic failure')
    monkeypatch.setattr(scheduler, 'run', run)
    scheduler.monitor(lambda: 'engine', Stop())
    assert calls == [('wait', 30), ('run', 'engine', {'apply': True, 'scheduled': True}),
                     ('wait', 300), ('run', 'engine', {'apply': True, 'scheduled': True}), ('wait', 300)]


def test_scheduler_chains_lifespan_once_and_stops_its_worker(monkeypatch):
    events, running = [], Event()
    @asynccontextmanager
    async def previous(app):
        events.append('previous-start')
        yield {'shared': 'preserved'}
        events.append('previous-stop')
    def monitor(engine, stop):
        events.append('monitor-start'); running.set()
        stop.wait(3)
        events.append('monitor-stop')
    monkeypatch.setattr(scheduler, 'monitor', monitor)
    app = FastAPI(lifespan=previous)
    scheduler.install(app, lambda: None)
    installed = app.router.lifespan_context
    scheduler.install(app, lambda: None)
    assert app.router.lifespan_context is installed
    with TestClient(app):
        assert running.wait(1)
        assert app.state.technical_retention_worker.is_alive()
    assert not app.state.technical_retention_worker.is_alive()
    assert events == ['previous-start', 'monitor-start', 'monitor-stop', 'previous-stop']

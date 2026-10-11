import asyncio
from contextlib import asynccontextmanager
from threading import Event
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

import vera_web_v2_live_tour as live
from test_live_tour_backend import RouteIdentity


@pytest.mark.parametrize('fail', [False, True])
def test_scheduler_preserves_lifespan_and_stops_on_error(monkeypatch, fail):
    events = []

    @asynccontextmanager
    async def original(app):
        events.append('app-start')
        try:
            yield {'shared': 'preserved'}
        finally:
            events.append('app-stop')

    monkeypatch.setenv('VERA_SERVICE_ROLE', 'combined')
    monkeypatch.setenv('VERA_WORKER_DB_MODE', 'direct')
    monkeypatch.setattr(live.job_queue, 'ensure_schema', lambda engine_instance: events.append('queue-schema-ready'))
    app = FastAPI(lifespan=original)
    # Reject use of the removed API even when testing an older FastAPI.
    def removed(*args, **kwargs):
        raise AssertionError('removed event API used')
    monkeypatch.setattr(app, 'add_event_handler', removed, raising=False)
    kwargs = dict(engine_instance=lambda: MagicMock(), current_identity=lambda: RouteIdentity(),
                  require_feature=lambda *args: None, feature_allowed=lambda *args: True,
                  identity_type=RouteIdentity)
    live.install_live_tour_routes(app, **kwargs)
    installed = app.router.lifespan_context
    live.install_live_tour_routes(app, **kwargs)
    assert app.router.lifespan_context is installed
    runtime = app.state.worker_runtime
    expected = {'live-tour-projection-scheduler', 'live-tour-projection-worker',
                'live-tour-queue-alert-monitor'}
    assert set(runtime.workers) == expected
    # Exercise the real supervisor/lifespan and real threads. Only the loop
    # bodies and heartbeat transport are synthetic in this unit test.
    started = {name: Event() for name in expected}
    def work(name):
        def loop(stop):
            events.append(('worker-start', name))
            started[name].set()
            stop.wait(10)
            events.append(('worker-stop', name))
        return loop
    for name, worker in runtime.workers.items():
        worker.target = work(name)
    monkeypatch.setattr(runtime, 'heartbeat', lambda: None)

    async def run():
        async with app.router.lifespan_context(app) as state:
            assert state == {'shared': 'preserved'}
            assert events[:2] == ['app-start', 'queue-schema-ready']
            assert all(event.wait(1) for event in started.values())
            assert {item[1] for item in events[2:]} == expected
            assert all(worker.thread.is_alive() for worker in runtime.workers.values())
            if fail:
                raise RuntimeError('test shutdown')

    if fail:
        with pytest.raises(RuntimeError, match='test shutdown'):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert events[0] == 'app-start' and events[-1] == 'app-stop'
    assert events.count('queue-schema-ready') == 1
    starts = [item[1] for item in events if isinstance(item, tuple) and item[0] == 'worker-start']
    stops = [item[1] for item in events if isinstance(item, tuple) and item[0] == 'worker-stop']
    assert len(starts) == len(stops) == 3
    assert set(starts) == set(stops) == expected
    assert runtime.state == 'stopped'
    assert all(not worker.thread.is_alive() and worker.stop.is_set() for worker in runtime.workers.values())
    assert not runtime.monitor_thread.is_alive()


def test_projection_queue_health_exposes_operational_metrics(monkeypatch):
    monkeypatch.setattr(live.job_queue, 'counts', lambda engine_instance, queue_name: {'done': 23})
    monkeypatch.setattr(live.queue_alerts, 'health_status', lambda engine_instance, queue_name, metrics: {'active': False, 'conditions': []})
    monkeypatch.setattr(
        live.job_queue, 'health_metrics',
        lambda engine_instance, queue_name: {
            'last_success_age': 115.5,
            'oldest_pending': None,
            'retry': 0,
            'failed': 0,
            'stale_processing': 0,
        },
    )
    app = FastAPI()
    live.install_live_tour_routes(
        app, engine_instance=lambda: None, current_identity=lambda: RouteIdentity(),
        require_feature=lambda *args: None, feature_allowed=lambda *args: True,
        identity_type=RouteIdentity,
    )
    route = next(route for route in app.routes if route.path == '/v2/live-tour/projection-queue/health')
    payload = route.endpoint()
    assert payload['counts'] == {'done': 23}
    assert payload['last_success_age'] == 115.5
    assert payload['oldest_pending'] is None
    assert payload['retry'] == 0
    assert payload['failed'] == 0
    assert payload['stale_processing'] == 0
    assert payload['ok'] is True
    assert payload['alerting']['active'] is False

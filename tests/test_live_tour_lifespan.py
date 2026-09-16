import asyncio
from contextlib import asynccontextmanager

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

    class FakeThread:
        def __init__(self, **kwargs):
            assert kwargs['daemon']

        def start(self):
            events.append('scheduler-start')

        def join(self, timeout):
            events.append('scheduler-stop')

    monkeypatch.setattr(live, 'Thread', FakeThread)
    monkeypatch.setattr(live.job_queue, 'ensure_schema', lambda engine_instance: events.append('queue-schema-ready'))
    app = FastAPI(lifespan=original)
    # Reject use of the removed API even when testing an older FastAPI.
    def removed(*args, **kwargs):
        raise AssertionError('removed event API used')
    monkeypatch.setattr(app, 'add_event_handler', removed, raising=False)
    kwargs = dict(engine_instance=lambda: None, current_identity=lambda: RouteIdentity(),
                  require_feature=lambda *args: None, feature_allowed=lambda *args: True,
                  identity_type=RouteIdentity)
    live.install_live_tour_routes(app, **kwargs)
    live.install_live_tour_routes(app, **kwargs)

    async def run():
        async with app.router.lifespan_context(app) as state:
            assert state == {'shared': 'preserved'}
            assert events == ['app-start', 'queue-schema-ready', 'scheduler-start', 'scheduler-start', 'scheduler-start']
            if fail:
                raise RuntimeError('test shutdown')

    if fail:
        with pytest.raises(RuntimeError, match='test shutdown'):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert events == ['app-start', 'queue-schema-ready', 'scheduler-start', 'scheduler-start', 'scheduler-start', 'scheduler-stop', 'scheduler-stop', 'scheduler-stop', 'app-stop']


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

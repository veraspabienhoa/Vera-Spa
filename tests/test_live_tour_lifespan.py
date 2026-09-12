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
            assert events == ['app-start', 'scheduler-start']
            if fail:
                raise RuntimeError('test shutdown')

    if fail:
        with pytest.raises(RuntimeError, match='test shutdown'):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert events == ['app-start', 'scheduler-start', 'scheduler-stop', 'app-stop']

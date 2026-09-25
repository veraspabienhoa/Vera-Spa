"""Run the persisted cleanup schedule in the existing API service, without sudo."""
from contextlib import asynccontextmanager
import logging
from threading import Event, Thread

from vera_technical_retention import run


def monitor(engine_instance, stop, *, initial_delay=30, interval=300):
    if stop.wait(initial_delay):
        return
    while not stop.is_set():
        try:
            # The database lock and persisted due check coordinate API workers,
            # service restarts and optional external/manual scheduler checks.
            run(engine_instance(), apply=True, scheduled=True)
        except Exception as error:
            logging.getLogger(__name__).warning('Technical cleanup deferred: %s', type(error).__name__)
        if stop.wait(interval):
            return


def install(app, engine_instance):
    if getattr(app.state, 'technical_retention_scheduler_installed', False):
        return
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application) as state:
            stop = Event()
            worker = Thread(target=monitor, args=(engine_instance, stop),
                name='technical-retention-monitor', daemon=True)
            worker.start()
            app.state.technical_retention_worker = worker
            try:
                yield state
            finally:
                stop.set()
                worker.join(timeout=2)

    app.router.lifespan_context = lifespan
    app.state.technical_retention_scheduler_installed = True

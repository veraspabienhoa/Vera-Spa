"""Run the persisted cleanup schedule in the existing API service, without sudo."""
import logging
from vera_worker_runtime import register_worker

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
    register_worker(app, engine_instance=engine_instance,
        name='technical-retention-monitor',
        target=lambda stop: monitor(engine_instance, stop), stale_after=400)
    app.state.technical_retention_scheduler_installed = True

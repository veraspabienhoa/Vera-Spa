"""Bounded Live Tour timings. Never record SQL text, parameters or row data."""
import logging
import re
from contextlib import contextmanager
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.engine import Connection


class ActionTiming:
    def __init__(self, action):
        self.action = action if re.fullmatch(r'[a-z_]{1,80}', action) else 'invalid'
        self.started = self.previous = perf_counter()
        self.phases = {}
        self.sql_count = 0
        self.sql_seconds = 0.0

    def mark(self, phase):
        now = perf_counter()
        self.phases[phase] = round((now - self.previous) * 1000, 2)
        self.previous = now

    @contextmanager
    def transaction(self, engine):
        query_started = 0.0

        def before(*_args):
            nonlocal query_started
            self.sql_count += 1
            query_started = perf_counter()

        def after(*_args):
            self.sql_seconds += perf_counter() - query_started

        try:
            with engine.begin() as conn:
                real = isinstance(conn, Connection)
                if real:
                    event.listen(conn, 'before_cursor_execute', before)
                    event.listen(conn, 'after_cursor_execute', after)
                try:
                    yield conn
                finally:
                    if real:
                        event.remove(conn, 'before_cursor_execute', before)
                        event.remove(conn, 'after_cursor_execute', after)
        except Exception:
            self.emit('error')
            raise

    def emit(self, outcome='ok'):
        elapsed = (perf_counter() - self.started) * 1000
        if elapsed >= 500 or outcome == 'error':
            logging.getLogger('uvicorn.error').info(
                'LIVE_TOUR_TIMING action=%s outcome=%s total_ms=%.2f sql_count=%d sql_ms=%.2f phases_ms=%s',
                self.action, outcome, elapsed, self.sql_count,
                self.sql_seconds * 1000, self.phases,
            )

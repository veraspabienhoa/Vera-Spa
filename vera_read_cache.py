"""Bounded per-process JSON read cache; never cache identities or financial writes."""
from collections import OrderedDict
from concurrent.futures import Future
from datetime import date, datetime
from decimal import Decimal
import json
from threading import RLock
from time import monotonic


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(type(value).__name__)


class ReadCache:
    def __init__(self, max_entries=128, ttl_seconds=10, max_bytes=8*1024*1024):
        self.max_entries = max_entries
        self.ttl = ttl_seconds
        self.max_bytes = max_bytes
        self._bytes = 0
        self._lock = RLock()
        self._entries = OrderedDict()
        self._pending = {}
        self._generation = 0

    def invalidate(self):
        """Call AFTER a successful commit; in-flight old loads cannot repopulate."""
        with self._lock:
            self._generation += 1
            self._entries.clear()
            self._bytes = 0

    def get_or_load(self, key, loader):
        with self._lock:
            token = (self._generation, key)
            cached = self._entries.get(token)
            if cached and cached[0] > monotonic():
                self._entries.move_to_end(token)
                return json.loads(cached[1])
            if cached:
                self._bytes -= len(self._entries.pop(token)[1])
            future = self._pending.get(token)
            owner = future is None
            if owner:
                future = Future()
                self._pending[token] = future
        if not owner:
            # Never wait here while retaining a database connection.
            return json.loads(future.result(timeout=15))
        try:
            value = loader()  # loader owns and releases its own connection
            raw = json.dumps(value, ensure_ascii=False, default=json_default).encode()
            with self._lock:
                if token[0] == self._generation and len(raw) <= self.max_bytes:
                    self._entries[token] = (monotonic()+self.ttl, raw)
                    self._bytes += len(raw)
                    while len(self._entries) > self.max_entries or self._bytes > self.max_bytes:
                        _, expired = self._entries.popitem(last=False)
                        self._bytes -= len(expired[1])
                future.set_result(raw)
            return json.loads(raw)
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._pending.pop(token, None)

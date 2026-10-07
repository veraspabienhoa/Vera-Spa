"""Bounded request histograms including auth, SQL, serialization and response bytes.

Labels use registered route templates, never raw URLs, bodies, SQL, identities,
headers or exception messages. No network exporter and no database writes.
"""
from contextvars import ContextVar
from collections import Counter
import json
import logging
from threading import Lock
from time import perf_counter
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.engine import Engine

_request = ContextVar("vera_request_metrics", default=None)
_buckets = (50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, float("inf"))
_lock = Lock()
_totals = {}
_last_flush = perf_counter()
_logger = logging.getLogger("uvicorn.error")


@event.listens_for(Engine, "before_cursor_execute")
def _sql_begin(conn, cursor, statement, parameters, context, executemany):
    metrics = _request.get()
    if metrics is not None:
        metrics["sql_count"] += 1
        context._vera_request_started = perf_counter()


@event.listens_for(Engine, "after_cursor_execute")
def _sql_end(conn, cursor, statement, parameters, context, executemany):
    metrics = _request.get()
    started = getattr(context, "_vera_request_started", None)
    if metrics is not None and started is not None:
        metrics["sql_ms"] += (perf_counter() - started) * 1000
        context._vera_request_started = None


@event.listens_for(Engine, "handle_error")
def _sql_error(exception_context):
    context = exception_context.execution_context
    if context is not None:
        _sql_end(None, None, None, None, context, False)


def _record(route, method, status, metrics):
    global _last_flush
    now = perf_counter()
    snapshot = None
    with _lock:
        key = (route, method, status // 100)
        if key not in _totals and len(_totals) >= 1024:
            key = ("other", "other", status // 100)
        item = _totals.setdefault(key, {"count": 0, "total_ms": 0, "sql_ms": 0,
                                      "sql_count": 0, "bytes": 0, "latency_buckets": Counter()})
        item["count"] += 1
        for field in ("total_ms", "sql_ms", "sql_count", "bytes"):
            item[field] += metrics[field]
        bucket = next(index for index, limit in enumerate(_buckets) if metrics["total_ms"] <= limit)
        item["latency_buckets"][bucket] += 1
        if now - _last_flush >= 60:
            snapshot = list(_totals.items())
            _totals.clear()
            _last_flush = now
    if snapshot:
        for (path, verb, group), values in snapshot:
            _logger.info("VERA_REQUEST_METRICS %s", json.dumps({
                "route": path, "method": verb, "status_group": group, **values,
                "total_ms": round(values["total_ms"], 2), "sql_ms": round(values["sql_ms"], 2),
            }, separators=(",", ":")))


class RequestMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = perf_counter()
        metrics = {"sql_count": 0, "sql_ms": 0.0, "bytes": 0}
        token = _request.set(metrics)
        status = 500
        request_id = uuid4().hex

        async def measured_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {**message, "headers": [*message.get("headers", []),
                                                  (b"x-request-id", request_id.encode())]}
            elif message["type"] == "http.response.body":
                metrics["bytes"] += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        finally:
            metrics["total_ms"] = (perf_counter() - started) * 1000
            _request.reset(token)
            route = getattr(scope.get("route"), "path", "unmatched")
            method = scope.get("method", "other")
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                method = "other"
            _record(route, method, status, metrics)
            if metrics["total_ms"] >= 1000 or status >= 500:
                _logger.info("VERA_REQUEST_SLOW %s", json.dumps({
                    "request_id": request_id, "route": route, "method": method,
                    "status": status, **metrics,
                }, separators=(",", ":")))

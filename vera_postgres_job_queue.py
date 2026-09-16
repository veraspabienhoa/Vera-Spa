"""Durable PostgreSQL job queue for slow background application work.

A claim transaction uses ``FOR UPDATE SKIP LOCKED`` and commits before
the worker performs slow work. Completion/retry is recorded in a later
transaction, so external I/O never holds a queue row lock or DB session.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

TABLE = "vera_background_job"
RELEASE = "postgres-job-queue-2026-09-16.2-health"
MAX_ATTEMPTS = 12


def ensure_schema_conn(conn) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id BIGSERIAL PRIMARY KEY,
            queue_name TEXT NOT NULL,
            job_key TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            locked_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(queue_name, job_key)
        )
    """))
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_ready "
        f"ON {TABLE}(queue_name,status,available_at,id)"
    ))


def ensure_schema(engine_instance) -> None:
    """Create/verify the queue schema before any scheduler or worker starts."""
    with engine_instance().begin() as conn:
        ensure_schema_conn(conn)


def enqueue_conn(conn, queue_name: str, job_key: str,
                 payload: dict[str, Any] | None = None) -> bool:
    result = conn.execute(text(f"""
        INSERT INTO {TABLE}(
            queue_name,job_key,payload,status,attempts,
            available_at,created_at,updated_at
        ) VALUES(
            :queue_name,:job_key,CAST(:payload AS jsonb),'pending',0,
            NOW(),NOW(),NOW()
        )
        ON CONFLICT(queue_name,job_key) DO NOTHING
    """), {
        "queue_name": str(queue_name),
        "job_key": str(job_key),
        "payload": json.dumps(payload or {}, ensure_ascii=False, default=str),
    })
    return bool(getattr(result, "rowcount", 1))


def enqueue(engine_instance, queue_name: str, job_key: str,
            payload: dict[str, Any] | None = None) -> bool:
    with engine_instance().begin() as conn:
        return enqueue_conn(conn, queue_name, job_key, payload)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
        return dict(parsed) if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def claim_one(engine_instance, queue_name: str) -> dict[str, Any] | None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {TABLE}
            SET status='retry', available_at=NOW(), locked_at=NULL,
                last_error=COALESCE(last_error,'worker lease expired'),
                updated_at=NOW()
            WHERE queue_name=:queue_name
              AND status='processing'
              AND locked_at < NOW() - INTERVAL '10 minutes'
        """), {"queue_name": queue_name})
        row = conn.execute(text(f"""
            SELECT id,queue_name,job_key,payload,attempts
            FROM {TABLE}
            WHERE queue_name=:queue_name
              AND status IN ('pending','retry')
              AND available_at<=NOW()
            ORDER BY available_at,id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """), {"queue_name": queue_name}).mappings().first()
        if not row:
            return None
        conn.execute(text(f"""
            UPDATE {TABLE}
            SET status='processing',locked_at=NOW(),updated_at=NOW()
            WHERE id=:id
        """), {"id": row["id"]})
        item = dict(row)
        item["payload"] = _payload(item.get("payload"))
        return item


def mark_done(engine_instance, item_id: int) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {TABLE}
            SET status='done',completed_at=NOW(),locked_at=NULL,
                last_error=NULL,updated_at=NOW()
            WHERE id=:id
        """), {"id": int(item_id)})


def reschedule(engine_instance, item_id: int, *, delay_seconds: int = 5) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {TABLE}
            SET status='retry',
                available_at=NOW()+(:delay*INTERVAL '1 second'),
                locked_at=NULL,updated_at=NOW()
            WHERE id=:id
        """), {
            "id": int(item_id),
            "delay": max(1, int(delay_seconds)),
        })


def mark_retry(engine_instance, item: dict[str, Any], exc: Exception) -> None:
    attempts = int(item.get("attempts") or 0) + 1
    delay = min(3600, 15 * (2 ** min(attempts - 1, 8)))
    status = "failed" if attempts >= MAX_ATTEMPTS else "retry"
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {TABLE}
            SET status=:status,attempts=:attempts,
                available_at=NOW()+(:delay*INTERVAL '1 second'),
                locked_at=NULL,last_error=:error,updated_at=NOW()
            WHERE id=:id
        """), {
            "id": int(item["id"]),
            "status": status,
            "attempts": attempts,
            "delay": delay,
            "error": f"{type(exc).__name__}: {exc}"[:2000],
        })


def counts(engine_instance, queue_name: str) -> dict[str, int]:
    with engine_instance().connect() as conn:
        rows = conn.execute(text(f"""
            SELECT status,COUNT(*) AS n
            FROM {TABLE}
            WHERE queue_name=:queue_name
            GROUP BY status
        """), {"queue_name": queue_name}).mappings().all()
    return {str(row["status"]): int(row["n"]) for row in rows}


def health_metrics(engine_instance, queue_name: str) -> dict[str, int | float | None]:
    """Return operational queue signals without mutating or claiming jobs."""
    with engine_instance().connect() as conn:
        row = conn.execute(text(f"""
            SELECT
                COUNT(*) FILTER (WHERE status='retry') AS retry,
                COUNT(*) FILTER (WHERE status='failed') AS failed,
                COUNT(*) FILTER (
                    WHERE status='processing'
                      AND locked_at < NOW() - INTERVAL '10 minutes'
                ) AS stale_processing,
                EXTRACT(EPOCH FROM (
                    NOW() - MAX(completed_at) FILTER (
                        WHERE status='done' AND completed_at IS NOT NULL
                    )
                )) AS last_success_age,
                EXTRACT(EPOCH FROM (
                    NOW() - MIN(created_at) FILTER (WHERE status='pending')
                )) AS oldest_pending
            FROM {TABLE}
            WHERE queue_name=:queue_name
        """), {"queue_name": queue_name}).mappings().first() or {}

    def age(name: str) -> float | None:
        value = row.get(name)
        return None if value is None else round(max(0.0, float(value)), 1)

    return {
        "last_success_age": age("last_success_age"),
        "oldest_pending": age("oldest_pending"),
        "retry": int(row.get("retry") or 0),
        "failed": int(row.get("failed") or 0),
        "stale_processing": int(row.get("stale_processing") or 0),
    }

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
RELEASE = "postgres-job-queue-2026-09-24.1-fenced-recovery"
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
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS vera_background_job_recovery (
            id BIGSERIAL PRIMARY KEY,
            job_id BIGINT NOT NULL,
            queue_name TEXT NOT NULL,
            previous_status TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


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
            WITH expired AS (
                SELECT id FROM {TABLE}
                WHERE queue_name=:queue_name AND status='processing'
                  AND locked_at < NOW() - INTERVAL '10 minutes'
                FOR UPDATE SKIP LOCKED
            )
            UPDATE {TABLE} AS job
            SET status='retry', available_at=NOW(), locked_at=NULL,
                last_error=COALESCE(last_error,'worker lease expired'),
                updated_at=NOW()
            FROM expired WHERE job.id=expired.id
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
        lease = conn.execute(text(f"""
            UPDATE {TABLE}
            SET status='processing',locked_at=clock_timestamp(),updated_at=NOW()
            WHERE id=:id
            RETURNING locked_at
        """), {"id": row["id"]}).scalar_one()
        item = dict(row)
        item["payload"] = _payload(item.get("payload"))
        item["locked_at"] = lease
        return item


def lease_current(conn, item: dict[str, Any]) -> bool:
    """Hold a row share lock until the board transaction commits.

    Recovery and automatic lease expiry skip this row while its worker writes.
    """
    return bool(conn.execute(text(f"""
        SELECT 1 FROM {TABLE}
        WHERE id=:id AND queue_name=:queue_name
          AND status='processing' AND locked_at=:locked_at
        FOR SHARE
    """), {"id": int(item["id"]), "queue_name": item["queue_name"],
           "locked_at": item["locked_at"]}).scalar_one_or_none())


def mark_done(engine_instance, item: dict[str, Any]) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {TABLE}
            SET status='done',completed_at=NOW(),locked_at=NULL,
                last_error=NULL,updated_at=NOW()
            WHERE id=:id AND status='processing' AND locked_at=:locked_at
        """), {"id": int(item["id"]), "locked_at": item["locked_at"]})


def reschedule(engine_instance, item: dict[str, Any], *, delay_seconds: int = 5) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {TABLE}
            SET status='retry',
                available_at=NOW()+(:delay*INTERVAL '1 second'),
                locked_at=NULL,updated_at=NOW()
            WHERE id=:id AND status='processing' AND locked_at=:locked_at
        """), {
            "id": int(item["id"]), "locked_at": item["locked_at"],
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
            WHERE id=:id AND status='processing' AND locked_at=:locked_at
        """), {
            "id": int(item["id"]),
            "locked_at": item["locked_at"],
            "status": status,
            "attempts": attempts,
            "delay": delay,
            "error": f"{type(exc).__name__}: {exc}"[:2000],
        })


def recover_expired(engine_instance, queue_name: str, actor: str) -> dict[str, int]:
    """Requeue one expired or failed job without interrupting a live transaction."""
    with engine_instance().begin() as conn:
        row = conn.execute(text(f"""
            SELECT id,status FROM {TABLE}
            WHERE queue_name=:queue_name AND (
                status='failed' OR
                (status='processing' AND locked_at < NOW() - INTERVAL '10 minutes')
            )
            ORDER BY CASE WHEN status='failed' THEN 1 ELSE 0 END, id
            FOR UPDATE SKIP LOCKED LIMIT 1
        """), {"queue_name": queue_name}).mappings().first()
        if not row:
            return {"requeued": 0}
        conn.execute(text(f"""
            UPDATE {TABLE} SET status='retry', attempts=0, locked_at=NULL,
                available_at=NOW(), last_error=NULL, updated_at=NOW()
            WHERE id=:id
        """), {"id": row["id"]})
        conn.execute(text("""
            INSERT INTO vera_background_job_recovery
                (job_id,queue_name,previous_status,actor)
            VALUES (:job_id,:queue_name,:status,:actor)
        """), {"job_id": row["id"], "queue_name": queue_name,
                "status": row["status"], "actor": actor[:160]})
        return {"requeued": 1}


def recovery_history(engine_instance, queue_name: str) -> list[dict[str, Any]]:
    with engine_instance().connect() as conn:
        rows = conn.execute(text("""
            SELECT job_id,previous_status,actor,created_at
            FROM vera_background_job_recovery
            WHERE queue_name=:queue_name ORDER BY id DESC LIMIT 10
        """), {"queue_name": queue_name}).mappings().all()
    return [dict(row) for row in rows]


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

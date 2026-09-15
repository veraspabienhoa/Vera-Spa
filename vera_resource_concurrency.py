"""System-wide PostgreSQL resource locking and mutation primitives.

Business modules lock the smallest invariant they mutate (employee, room,
invoice, combo, leave owner/date, or payroll period).  Locks are always acquired
in canonical order, so transactions touching several resources cannot deadlock
because two routes happened to request them in a different order.

The tables are intentionally generic.  They do not replace domain tables; they
provide durable idempotency, per-resource revisions, exclusive claims and a
small mutation ledger shared by every VERA module.
"""
from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from typing import Any, Iterable

from sqlalchemy import text

SCHEMA_VERSION = 1
REVISION_TABLE = "vera_resource_revision"
MUTATION_TABLE = "vera_business_mutation"
CLAIM_TABLE = "vera_resource_claim"
EVENT_TABLE = "vera_business_mutation_event"
COUNTER_TABLE = "vera_business_counter"


def lock_mode() -> str:
    """Return legacy/hybrid/resource; hybrid is the safe migration default."""
    value = str(os.getenv("VERA_RESOURCE_LOCK_MODE", "hybrid") or "hybrid").strip().lower()
    return value if value in {"legacy", "hybrid", "resource"} else "hybrid"


def normalize_id(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).strip().casefold()
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(value.split())


def resource_key(domain: str, resource_id: Any) -> str:
    domain_value = normalize_id(domain).replace(" ", "_")
    id_value = normalize_id(resource_id)
    if not domain_value or not id_value:
        raise ValueError("domain and resource_id are required")
    return f"vera:resource:{domain_value}:{id_value}"


def canonical_keys(resources: Iterable[tuple[str, Any]]) -> list[str]:
    return sorted({resource_key(domain, resource_id) for domain, resource_id in resources})


def lock_resources(conn, resources: Iterable[tuple[str, Any]], *, wait: bool = True) -> list[str]:
    """Acquire transaction-scoped locks in one deterministic global order."""
    keys = canonical_keys(resources)
    function = "pg_advisory_xact_lock" if wait else "pg_try_advisory_xact_lock"
    for key in keys:
        result = conn.execute(
            text(f"SELECT {function}(hashtextextended(:key,0))"), {"key": key},
        )
        if not wait and not bool(result.scalar()):
            raise TimeoutError(f"resource busy: {key}")
    return keys


def lock_transition(
    conn, resources: Iterable[tuple[str, Any]], *, legacy_keys: Iterable[str] = (),
    wait: bool = True,
) -> list[str]:
    """Bridge old global locks to resource locks during a rolling cutover.

    ``hybrid`` coordinates with old application instances.  After every writer
    runs this release, ``resource`` removes the legacy lock and enables commits
    on unrelated resources to proceed concurrently.
    """
    selected = lock_mode()
    acquired: list[str] = []
    if selected in {"legacy", "hybrid"}:
        function = "pg_advisory_xact_lock" if wait else "pg_try_advisory_xact_lock"
        for key in sorted({str(item).strip() for item in legacy_keys if str(item).strip()}):
            result = conn.execute(text(f"SELECT {function}(hashtext(:key))"), {"key": key})
            if not wait and not bool(result.scalar()):
                raise TimeoutError(f"legacy resource busy: {key}")
            acquired.append(key)
    if selected in {"hybrid", "resource"}:
        acquired.extend(lock_resources(conn, resources, wait=wait))
    return acquired


def ensure_schema(conn) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {REVISION_TABLE} (
            domain TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            revision BIGINT NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(domain, resource_id)
        )
    """))
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {MUTATION_TABLE} (
            scope TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('started','completed','failed')),
            result JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            PRIMARY KEY(scope, idempotency_key)
        )
    """))
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {CLAIM_TABLE} (
            domain TEXT NOT NULL,
            claim_key TEXT NOT NULL,
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            revision BIGINT NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(domain, claim_key)
        )
    """))
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {EVENT_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            scope TEXT NOT NULL,
            idempotency_key TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            resources JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS idx_{EVENT_TABLE}_scope_created "
        f"ON {EVENT_TABLE}(scope, created_at DESC)"
    ))
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {COUNTER_TABLE} (
            scope TEXT NOT NULL,
            counter_key TEXT NOT NULL,
            value BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(scope, counter_key)
        )
    """))


def next_counter(conn, *, scope: str, counter_key: Any, floor: int = 0) -> int:
    """Atomically allocate a number without a table-wide MAX()+1 race."""
    value = conn.execute(text(f"""
        INSERT INTO {COUNTER_TABLE}(scope,counter_key,value,updated_at)
        VALUES(:scope,:counter_key,:initial,NOW())
        ON CONFLICT(scope,counter_key) DO UPDATE SET
          value=GREATEST({COUNTER_TABLE}.value,:floor)+1, updated_at=NOW()
        RETURNING value
    """), {
        "scope": normalize_id(scope), "counter_key": normalize_id(counter_key),
        "initial": max(1, int(floor) + 1), "floor": max(0, int(floor)),
    }).scalar_one()
    return int(value)


def bump_revisions(conn, resources: Iterable[tuple[str, Any]]) -> dict[str, int]:
    revisions: dict[str, int] = {}
    for key in canonical_keys(resources):
        _, _, domain, resource_id = key.split(":", 3)
        revision = conn.execute(text(f"""
            INSERT INTO {REVISION_TABLE}(domain,resource_id,revision,updated_at)
            VALUES(:domain,:resource_id,1,NOW())
            ON CONFLICT(domain,resource_id) DO UPDATE SET
              revision={REVISION_TABLE}.revision+1, updated_at=NOW()
            RETURNING revision
        """), {"domain": domain, "resource_id": resource_id}).scalar_one()
        revisions[key] = int(revision)
    return revisions


def request_hash(action: str, payload: Any) -> str:
    encoded = json.dumps(
        {"action": action, "payload": payload}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def completed_mutation(conn, scope: str, idempotency_key: str, expected_hash: str) -> dict | None:
    row = conn.execute(text(f"""
        SELECT request_hash,status,result FROM {MUTATION_TABLE}
        WHERE scope=:scope AND idempotency_key=:key
    """), {"scope": scope, "key": idempotency_key}).mappings().first()
    if not row:
        return None
    if str(row["request_hash"]) != expected_hash:
        raise ValueError("idempotency key was already used for a different request")
    if row["status"] != "completed":
        raise RuntimeError("mutation with this idempotency key is still in progress")
    value = row["result"]
    return value if isinstance(value, dict) else json.loads(value or "{}")


def complete_mutation(
    conn, *, scope: str, idempotency_key: str, actor: str, action: str,
    expected_hash: str, result: dict[str, Any], resources: Iterable[tuple[str, Any]],
) -> None:
    resource_keys = canonical_keys(resources)
    saved = conn.execute(text(f"""
        INSERT INTO {MUTATION_TABLE}(
          scope,idempotency_key,actor,action,request_hash,status,result,created_at,completed_at
        ) VALUES(:scope,:key,:actor,:action,:request_hash,'completed',CAST(:result AS jsonb),NOW(),NOW())
        ON CONFLICT(scope,idempotency_key) DO UPDATE SET
          actor=EXCLUDED.actor, action=EXCLUDED.action, request_hash=EXCLUDED.request_hash,
          status='completed', result=EXCLUDED.result, completed_at=NOW()
        WHERE {MUTATION_TABLE}.request_hash=EXCLUDED.request_hash
    """), {
        "scope": scope, "key": idempotency_key, "actor": actor, "action": action,
        "request_hash": expected_hash,
        "result": json.dumps(result, ensure_ascii=False, sort_keys=True, default=str),
    })
    if int(saved.rowcount or 0) != 1:
        raise ValueError("idempotency key was already used for a different request")
    conn.execute(text(f"""
        INSERT INTO {EVENT_TABLE}(scope,idempotency_key,actor,action,resources)
        VALUES(:scope,:key,:actor,:action,CAST(:resources AS jsonb))
    """), {
        "scope": scope, "key": idempotency_key, "actor": actor, "action": action,
        "resources": json.dumps(resource_keys, ensure_ascii=False),
    })


def claim(
    conn, *, domain: str, claim_key: Any, owner_type: str, owner_id: Any,
    payload: dict[str, Any] | None = None,
) -> None:
    domain_value = normalize_id(domain)
    claim_value = normalize_id(claim_key)
    owner_value = normalize_id(owner_id)
    result = conn.execute(text(f"""
        INSERT INTO {CLAIM_TABLE}(domain,claim_key,owner_type,owner_id,payload,revision,updated_at)
        VALUES(:domain,:claim_key,:owner_type,:owner_id,CAST(:payload AS jsonb),1,NOW())
        ON CONFLICT(domain,claim_key) DO UPDATE SET
          owner_type=EXCLUDED.owner_type, owner_id=EXCLUDED.owner_id,
          payload=EXCLUDED.payload, revision={CLAIM_TABLE}.revision+1, updated_at=NOW()
        WHERE {CLAIM_TABLE}.owner_type=EXCLUDED.owner_type
          AND {CLAIM_TABLE}.owner_id=EXCLUDED.owner_id
    """), {
        "domain": domain_value, "claim_key": claim_value,
        "owner_type": normalize_id(owner_type), "owner_id": owner_value,
        "payload": json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, default=str),
    })
    if int(result.rowcount or 0) != 1:
        raise RuntimeError(f"{domain_value} resource is already claimed")


def release_claim(conn, *, domain: str, claim_key: Any, owner_type: str, owner_id: Any) -> bool:
    result = conn.execute(text(f"""
        DELETE FROM {CLAIM_TABLE}
        WHERE domain=:domain AND claim_key=:claim_key
          AND owner_type=:owner_type AND owner_id=:owner_id
    """), {
        "domain": normalize_id(domain), "claim_key": normalize_id(claim_key),
        "owner_type": normalize_id(owner_type), "owner_id": normalize_id(owner_id),
    })
    return int(result.rowcount or 0) == 1

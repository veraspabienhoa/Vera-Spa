"""Normalized PostgreSQL storage used for the Live Tour concurrency cutover.

The existing aggregate remains the serving source during ``shadow`` mode.  Each
committed aggregate mutation is mirrored into independently versioned resource
rows.  ``verify`` compares both representations before ``active`` can be enabled.
No function in this module opens its own connection: callers keep one atomic
transaction and can compose it with the existing financial safeguards.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from typing import Any, Iterable

from sqlalchemy import text

import vera_resource_concurrency as concurrency

SCHEMA_VERSION = 2
META_TABLE = "vera_live_tour_meta"
MUTATION_TABLE = "vera_live_tour_mutation"
CLAIM_TABLE = "vera_live_tour_room_claim"

RESOURCE_COLLECTIONS = (
    "employees", "rooms", "services", "combos", "customers", "pending",
    "invoices", "reports", "combo_usage", "combo_sale_requests",
    "break_events", "audit", "backups", "pending_changes", "invoice_changes",
    "customer_changes",
)
RESOURCE_TABLES = {
    "employees": "vera_live_tour_employee",
    "rooms": "vera_live_tour_room",
    "services": "vera_live_tour_service",
    "combos": "vera_live_tour_combo",
    "customers": "vera_live_tour_customer",
    "pending": "vera_live_tour_pending",
    "invoices": "vera_live_tour_invoice",
    "reports": "vera_live_tour_report",
    "combo_usage": "vera_live_tour_combo_usage",
    "combo_sale_requests": "vera_live_tour_combo_sale_request",
    "break_events": "vera_live_tour_break_event",
    "audit": "vera_live_tour_audit",
    "backups": "vera_live_tour_backup",
    "pending_changes": "vera_live_tour_pending_change",
    "invoice_changes": "vera_live_tour_invoice_change",
    "customer_changes": "vera_live_tour_customer_change",
}


def mode() -> str:
    value = str(os.getenv("VERA_LIVE_TOUR_RELATIONAL_MODE", "shadow") or "shadow").strip().lower()
    return value if value in {"off", "shadow", "verify", "active"} else "shadow"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _resource_id(collection: str, item: dict[str, Any], ordinal: int) -> str:
    explicit = str(item.get("id") or item.get("record_uid") or "").strip()
    if explicit:
        return explicit
    # Append-only legacy rows do not all have IDs. Keep a deterministic identity
    # based on content and ordinal so backfill is repeatable without altering DTOs.
    return f"legacy-{hashlib.sha256(f'{collection}:{ordinal}:{_json(item)}'.encode()).hexdigest()}"


def ensure_schema(conn) -> None:
    concurrency.ensure_schema(conn)
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {META_TABLE} (
            singleton SMALLINT PRIMARY KEY DEFAULT 1 CHECK(singleton=1),
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            payload_hash TEXT NOT NULL,
            aggregate_revision BIGINT NOT NULL DEFAULT 0,
            schema_version INTEGER NOT NULL DEFAULT {SCHEMA_VERSION},
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    for table_name in RESOURCE_TABLES.values():
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            resource_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL DEFAULT 0,
            payload JSONB NOT NULL,
            payload_hash TEXT NOT NULL,
            resource_revision BIGINT NOT NULL DEFAULT 1,
            aggregate_revision BIGINT NOT NULL DEFAULT 0,
            deleted_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(resource_id)
        )
        """))
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_ordered "
            f"ON {table_name}(ordinal) WHERE deleted_at IS NULL"
        ))
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_aggregate_revision "
            f"ON {table_name}(aggregate_revision)"
        ))
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {MUTATION_TABLE} (
            idempotency_key TEXT PRIMARY KEY,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('started','completed','failed')),
            result JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            UNIQUE(actor, action, idempotency_key)
        )
    """))
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {CLAIM_TABLE} (
            room_key TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            booking_id TEXT NOT NULL DEFAULT '',
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            claim_revision BIGINT NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(employee_id, booking_id)
        )
    """))


def _split(state: dict[str, Any]) -> tuple[dict[str, Any], dict[tuple[str, str], tuple[int, dict[str, Any]]]]:
    # ``sync_changes`` only serializes and compares these values.  It never
    # mutates them, so copying the full aggregate here is pure lock-held work.
    # Callers keep the pre- and post-mutation snapshots distinct.
    meta = {key: value for key, value in state.items() if key not in RESOURCE_COLLECTIONS}
    resources: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for collection in RESOURCE_COLLECTIONS:
        for ordinal, raw in enumerate(state.get(collection) or []):
            if not isinstance(raw, dict):
                continue
            resources[(collection, _resource_id(collection, raw, ordinal))] = (ordinal, raw)
    return meta, resources


def schema_exists(conn) -> bool:
    # The migration creates every table in one transaction, so the meta table
    # is a cheap atomic readiness marker. Full table validation stays in the
    # deploy verifier instead of adding 17 catalog round trips to every action.
    return bool(conn.execute(
        text("SELECT to_regclass(:table_name)"), {"table_name": META_TABLE},
    ).scalar())


def sync_changes(
    conn, before: dict[str, Any] | None, after: dict[str, Any], aggregate_revision: int,
    *, force: bool = False,
) -> dict[str, int]:
    """Mirror only changed resource rows; safe to call repeatedly in one transaction."""
    if mode() == "off" and not force:
        return {"upserted": 0, "deleted": 0}
    if force:
        ensure_schema(conn)
    elif not schema_exists(conn):
        # Deploy creates/backfills the tables after the new release is copied.
        # Requests in that short window keep using the proven aggregate path.
        return {"upserted": 0, "deleted": 0}
    before_meta, old = _split(before or {})
    after_meta, new = _split(after)
    upserted = deleted = 0
    conn.execute(text(f"""
        INSERT INTO {META_TABLE}(singleton,payload,payload_hash,aggregate_revision,schema_version,updated_at)
        VALUES(1,CAST(:payload AS jsonb),:hash,:revision,:schema,NOW())
        ON CONFLICT(singleton) DO UPDATE SET payload=EXCLUDED.payload,
          payload_hash=EXCLUDED.payload_hash, aggregate_revision=EXCLUDED.aggregate_revision,
          schema_version=EXCLUDED.schema_version, updated_at=NOW()
    """), {"payload": _json(after_meta), "hash": _digest(after_meta), "revision": aggregate_revision, "schema": SCHEMA_VERSION})
    for key, (ordinal, payload) in new.items():
        if key in old and old[key] == (ordinal, payload):
            continue
        table_name = RESOURCE_TABLES[key[0]]
        conn.execute(text(f"""
            INSERT INTO {table_name}(resource_id,ordinal,payload,payload_hash,resource_revision,aggregate_revision,deleted_at,updated_at)
            VALUES(:id,:ordinal,CAST(:payload AS jsonb),:hash,1,:aggregate,NULL,NOW())
            ON CONFLICT(resource_id) DO UPDATE SET
              ordinal=EXCLUDED.ordinal, payload=EXCLUDED.payload, payload_hash=EXCLUDED.payload_hash,
              resource_revision={table_name}.resource_revision+1,
              aggregate_revision=EXCLUDED.aggregate_revision, deleted_at=NULL, updated_at=NOW()
        """), {"id": key[1], "ordinal": ordinal, "payload": _json(payload),
                 "hash": _digest(payload), "aggregate": aggregate_revision})
        upserted += 1
    for key in old.keys() - new.keys():
        table_name = RESOURCE_TABLES[key[0]]
        conn.execute(text(f"""
            UPDATE {table_name} SET deleted_at=NOW(), resource_revision=resource_revision+1,
              aggregate_revision=:aggregate, updated_at=NOW()
            WHERE resource_id=:id AND deleted_at IS NULL
        """), {"id": key[1], "aggregate": aggregate_revision})
        deleted += 1
    return {"upserted": upserted, "deleted": deleted}


def load_state(conn) -> tuple[dict[str, Any] | None, int]:
    if not schema_exists(conn):
        return None, 0
    meta = conn.execute(text(f"SELECT payload,aggregate_revision FROM {META_TABLE} WHERE singleton=1")).mappings().first()
    if not meta:
        return None, 0
    state = deepcopy(meta["payload"] if isinstance(meta["payload"], dict) else json.loads(meta["payload"]))
    for collection in RESOURCE_COLLECTIONS:
        state[collection] = []
    for kind, table_name in RESOURCE_TABLES.items():
        rows = conn.execute(text(f"""
            SELECT payload FROM {table_name}
            WHERE deleted_at IS NULL ORDER BY ordinal,resource_id
        """)).mappings().all()
        for row in rows:
            payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
            state[kind].append(deepcopy(payload))
    return state, int(meta["aggregate_revision"] or 0)


def parity(conn, aggregate_state: dict[str, Any], aggregate_revision: int) -> dict[str, Any]:
    relational, mirrored_revision = load_state(conn)
    return {
        "ok": relational is not None and _digest(relational) == _digest(aggregate_state),
        "aggregate_revision": int(aggregate_revision),
        "mirrored_revision": mirrored_revision,
        "aggregate_hash": _digest(aggregate_state),
        "relational_hash": _digest(relational) if relational is not None else "",
    }


def lock_resources(conn, resources: Iterable[tuple[str, str]]) -> list[str]:
    """Acquire transaction locks in canonical order to prevent deadlocks."""
    return concurrency.lock_resources(
        conn, ((f"live_tour_{kind}", resource_id) for kind, resource_id in resources if resource_id),
    )


def claim_room(conn, room_key: str, employee_id: str, booking_id: str, payload: dict[str, Any] | None = None) -> None:
    """Claim a physical room atomically; the PK rejects cross-browser duplicates."""
    conn.execute(text(f"""
        INSERT INTO {CLAIM_TABLE}(room_key,employee_id,booking_id,payload,claim_revision,updated_at)
        VALUES(:room,:employee,:booking,CAST(:payload AS jsonb),1,NOW())
        ON CONFLICT(room_key) DO UPDATE SET employee_id=EXCLUDED.employee_id,
          booking_id=EXCLUDED.booking_id,payload=EXCLUDED.payload,
          claim_revision={CLAIM_TABLE}.claim_revision+1,updated_at=NOW()
        WHERE {CLAIM_TABLE}.employee_id=EXCLUDED.employee_id
    """), {"room": room_key, "employee": employee_id, "booking": booking_id or "", "payload": _json(payload or {})})
    owner = conn.execute(text(f"SELECT employee_id FROM {CLAIM_TABLE} WHERE room_key=:room"), {"room": room_key}).scalar()
    if str(owner or "") != str(employee_id):
        raise RuntimeError("Live Tour room is already claimed by another employee")


def release_room(conn, room_key: str, employee_id: str) -> None:
    conn.execute(text(f"DELETE FROM {CLAIM_TABLE} WHERE room_key=:room AND employee_id=:employee"),
                 {"room": room_key, "employee": employee_id})

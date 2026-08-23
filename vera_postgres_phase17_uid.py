"""Phase 17.2: strict record_uid-canonical CRUD for leave_records.

PostgreSQL is the authority whenever Phase 17 is active. Every UPDATE/DELETE is
resolved to a stable record_uid first and the mutation itself is executed only by
record_uid. Legacy source_sheet_id/source_row is accepted solely as an ingress
compatibility locator and mirror-position metadata; it is never an UPDATE/DELETE
key and incoming UI values cannot move an existing canonical record.

Google Sheets remains a sync/optional/off mirror. A mirror failure never rewinds a
committed PostgreSQL mutation.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import text

import vera_postgres_phase3 as _phase3


PHASE17_UID_SCHEMA_VERSION = 172
PHASE17_UID_COMPONENT = "phase17_leave_record_uid_crud"
LEAVE_DATASET = "leave_primary"
_LOCK_KEY = "vera:phase4:leave_primary"
_CREATE_OPERATIONS = {"create", "append", "range_create", "create_single", "batch_create"}

_ORIGINAL_UPSERT = None
_ORIGINAL_BATCH_UPSERT = None
_ORIGINAL_DELETE = None


class Phase17LeaveUIDError(RuntimeError):
    pass


def _enabled(vpg) -> bool:
    fn = getattr(vpg, "phase17_is_enabled", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            return False
    try:
        import vera_postgres_phase17 as _phase17
        return bool(_phase17.is_active(vpg))
    except Exception:
        return False


def _event(vpg, event_type: str, detail: str = "") -> None:
    try:
        vpg.record_event(LEAVE_DATASET, str(event_type), str(detail or "")[:1800])
    except Exception:
        pass


def _ensure_schema(vpg) -> None:
    if not _enabled(vpg):
        return
    version_table = getattr(vpg, "SCHEMA_VERSION_TABLE", "vera_schema_version")
    with vpg.get_engine().begin() as conn:
        conn.execute(text("ALTER TABLE leave_records ADD COLUMN IF NOT EXISTS record_uid TEXT"))
        conn.execute(text("""
            UPDATE leave_records
            SET record_uid = 'lr-' || md5(
                COALESCE(source_sheet_id,'') || ':' ||
                COALESCE(source_row::text,'') || ':' || id::text
            )
            WHERE record_uid IS NULL OR BTRIM(record_uid)=''
        """))
        health = conn.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE record_uid IS NULL OR BTRIM(record_uid)='') AS missing_uid,
                COUNT(*) - COUNT(DISTINCT record_uid) AS duplicate_uid
            FROM leave_records
        """)).mappings().first() or {}
        if int(health.get("missing_uid") or 0) != 0:
            raise Phase17LeaveUIDError("Cannot enforce record_uid NOT NULL: missing UID remains")
        if int(health.get("duplicate_uid") or 0) != 0:
            raise Phase17LeaveUIDError("Cannot enforce record_uid uniqueness: duplicate UID exists")
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_leave_records_record_uid
            ON leave_records(record_uid)
        """))
        conn.execute(text("ALTER TABLE leave_records ALTER COLUMN record_uid SET NOT NULL"))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_leave_records_uid_source
            ON leave_records(record_uid, source_sheet_id, source_row)
        """))
        conn.execute(text(f"""
            INSERT INTO {version_table}(component, version, updated_at)
            VALUES (:component, :version, NOW())
            ON CONFLICT (component) DO UPDATE
            SET version=GREATEST({version_table}.version, EXCLUDED.version), updated_at=NOW()
        """), {"component": PHASE17_UID_COMPONENT, "version": PHASE17_UID_SCHEMA_VERSION})


@contextmanager
def _leave_lock(vpg):
    lock_conn = vpg.get_engine().connect()
    locked = False
    try:
        lock_conn.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), {"k": _LOCK_KEY})
        locked = True
        yield
    finally:
        if locked:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": _LOCK_KEY})
            except Exception:
                pass
        try:
            lock_conn.close()
        except Exception:
            pass


def _explicit_uid(raw: Mapping[str, Any]) -> str:
    return str(raw.get("record_uid") or raw.get("__record_uid") or "").strip()


def _new_uid() -> str:
    return "lr-" + uuid.uuid4().hex


def _source_identity(raw: Mapping[str, Any], required: bool = True) -> tuple[str, int]:
    source_id = str(raw.get("__source_sheet_id") or raw.get("source_sheet_id") or "leave_primary").strip()
    source_row = raw.get("__source_row", raw.get("source_row", 0))
    try:
        source_row = int(float(source_row or 0))
    except Exception:
        source_row = 0
    if required and (not source_id or source_row <= 0):
        raise Phase17LeaveUIDError("Leave create/legacy bridge requires source sheet id and positive source row")
    return source_id, source_row


def _fetch_uid_row(conn, uid: str):
    if not uid:
        return None
    row = conn.execute(text("SELECT * FROM leave_records WHERE record_uid=:u"), {"u": uid}).mappings().first()
    return dict(row) if row else None


def _fetch_source_row(conn, source_id: str, source_row: int):
    rows = conn.execute(text("""
        SELECT * FROM leave_records
        WHERE source_sheet_id=:s AND source_row=:r
        ORDER BY id
        LIMIT 2
    """), {"s": source_id, "r": int(source_row)}).mappings().all()
    if len(rows) > 1:
        raise Phase17LeaveUIDError(f"Ambiguous legacy locator {source_id}:{source_row}; refusing mutation")
    return dict(rows[0]) if rows else None


def _resolve_existing(conn, raw: Mapping[str, Any]):
    """Resolve compatibility input to one canonical UID; never mutates by source row."""
    uid = _explicit_uid(raw)
    if uid:
        row = _fetch_uid_row(conn, uid)
        if not row:
            raise Phase17LeaveUIDError(f"record_uid not found: {uid}")
        return uid, row, False
    source_id, source_row = _source_identity(raw, required=True)
    row = _fetch_source_row(conn, source_id, source_row)
    if not row:
        raise Phase17LeaveUIDError(f"Cannot bridge legacy locator {source_id}:{source_row} to canonical record_uid")
    uid = str(row.get("record_uid") or "").strip()
    if not uid:
        raise Phase17LeaveUIDError(f"Canonical row {source_id}:{source_row} has no record_uid")
    return uid, row, True


def _canonical_input(raw: Mapping[str, Any], existing: Mapping[str, Any], uid: str) -> dict:
    out = dict(raw or {})
    source_id = str(existing.get("source_sheet_id") or "leave_primary").strip()
    source_row = int(existing.get("source_row") or 0)
    if source_row <= 0:
        raise Phase17LeaveUIDError(f"Canonical UID {uid} has invalid mirror source_row")
    out["record_uid"] = uid
    out["__record_uid"] = uid
    out["source_sheet_id"] = source_id
    out["__source_sheet_id"] = source_id
    out["source_row"] = source_row
    out["__source_row"] = source_row
    return out


def _normalize(raw: Mapping[str, Any], source_row: int, uid: str, source_id: str) -> dict:
    canonical = dict(raw or {})
    canonical["record_uid"] = uid
    canonical["__record_uid"] = uid
    canonical["source_sheet_id"] = source_id
    canonical["__source_sheet_id"] = source_id
    canonical["source_row"] = int(source_row)
    canonical["__source_row"] = int(source_row)
    item = _phase3._leave_record(canonical, int(source_row))
    if not item:
        raise Phase17LeaveUIDError("Invalid leave record: employee/reason is required")
    try:
        payload = item.get("payload")
        payload_obj = json.loads(payload) if isinstance(payload, str) and payload.strip() else dict(payload or {})
        if not isinstance(payload_obj, dict):
            payload_obj = {}
    except Exception:
        payload_obj = {}
    payload_obj["__record_uid"] = uid
    payload_obj["__source_sheet_id"] = source_id
    payload_obj["__source_row"] = int(source_row)
    item["payload"] = json.dumps(payload_obj, ensure_ascii=False, default=str)
    item["source_sheet_id"] = source_id
    item["source_row"] = int(source_row)
    return item


_UPDATE_BY_UID_SQL = text("""
    UPDATE leave_records SET
        leave_date=:leave_date,
        employee_name=:employee_name,
        leave_reason=:leave_reason,
        leave_type=:leave_type,
        detail=:detail,
        calculated_days=:calculated_days,
        accumulated_leave=:accumulated_leave,
        penalty=:penalty,
        update_date=:update_date,
        update_time=:update_time,
        updated_by=:updated_by,
        weekday_label=:weekday_label,
        payload=CAST(:payload AS JSONB),
        updated_at=NOW()
    WHERE record_uid=:record_uid
""")

_INSERT_UID_SQL = text("""
    INSERT INTO leave_records (
        record_uid,source_sheet_id,source_row,leave_date,employee_name,leave_reason,
        leave_type,detail,calculated_days,accumulated_leave,penalty,update_date,
        update_time,updated_by,weekday_label,payload,created_at,updated_at
    ) VALUES (
        :record_uid,:source_sheet_id,:source_row,:leave_date,:employee_name,:leave_reason,
        :leave_type,:detail,:calculated_days,:accumulated_leave,:penalty,:update_date,
        :update_time,:updated_by,:weekday_label,CAST(:payload AS JSONB),NOW(),NOW()
    )
""")


def _params(normalized: Mapping[str, Any], uid: str) -> dict:
    keys = (
        "source_sheet_id", "source_row", "leave_date", "employee_name", "leave_reason",
        "leave_type", "detail", "calculated_days", "accumulated_leave", "penalty",
        "update_date", "update_time", "updated_by", "weekday_label", "payload",
    )
    out = {k: normalized.get(k) for k in keys}
    out["record_uid"] = uid
    return out


def _temporary_reindex(conn, rows: list[tuple[str, int]], finals: Mapping[str, int]) -> None:
    if not rows:
        return
    marker = 1_000_000_000
    for idx, (uid, old_row) in enumerate(rows, start=1):
        result = conn.execute(text("UPDATE leave_records SET source_row=:r WHERE record_uid=:u"), {
            "r": -(marker + int(old_row) * 10 + idx), "u": uid,
        })
        if int(result.rowcount or 0) != 1:
            raise Phase17LeaveUIDError(f"UID reindex affected {result.rowcount} rows: {uid}")
    for uid, _old_row in rows:
        final_row = int(finals[uid])
        result = conn.execute(text("""
            UPDATE leave_records
            SET source_row=:r,
                payload=jsonb_set(
                    jsonb_set(COALESCE(payload,'{}'::jsonb), '{__source_row}', to_jsonb(CAST(:r AS INTEGER)), TRUE),
                    '{__record_uid}', to_jsonb(CAST(:u AS TEXT)), TRUE
                ),
                updated_at=NOW()
            WHERE record_uid=:u
        """), {"r": final_row, "u": uid})
        if int(result.rowcount or 0) != 1:
            raise Phase17LeaveUIDError(f"UID final reindex affected {result.rowcount} rows: {uid}")


def _repair_create_collision(conn, source_id: str, first_new_row: int) -> None:
    if not _fetch_source_row(conn, source_id, first_new_row):
        return
    existing = conn.execute(text("""
        SELECT record_uid,source_row,id FROM leave_records
        WHERE source_sheet_id=:s AND source_row IS NOT NULL AND source_row > 0
        ORDER BY source_row,id
    """), {"s": source_id}).mappings().all()
    expected_first_new = len(existing) + 2
    if int(first_new_row) != int(expected_first_new):
        raise Phase17LeaveUIDError(
            f"Mirror source-row collision {source_id}:{first_new_row}; refusing to overwrite canonical identity"
        )
    moves: list[tuple[str, int]] = []
    finals: dict[str, int] = {}
    for pos, row in enumerate(existing, start=2):
        uid = str(row.get("record_uid") or "").strip()
        old = int(row.get("source_row") or 0)
        if not uid:
            raise Phase17LeaveUIDError("Existing canonical leave row has no record_uid")
        if old != pos:
            moves.append((uid, old)); finals[uid] = pos
    _temporary_reindex(conn, moves, finals)
    if _fetch_source_row(conn, source_id, first_new_row):
        raise Phase17LeaveUIDError(f"Could not free mirror source row {source_id}:{first_new_row}")


def _shift_after_delete(conn, deleted_by_sheet: Mapping[str, list[int]]) -> None:
    for source_id, deleted_rows in deleted_by_sheet.items():
        deleted = sorted({int(r) for r in deleted_rows if int(r) > 0})
        if not deleted:
            continue
        affected = conn.execute(text("""
            SELECT record_uid,source_row,id FROM leave_records
            WHERE source_sheet_id=:s AND source_row>:m ORDER BY source_row,id
        """), {"s": source_id, "m": min(deleted)}).mappings().all()
        moves: list[tuple[str, int]] = []
        finals: dict[str, int] = {}
        for row in affected:
            uid = str(row.get("record_uid") or "").strip()
            old = int(row.get("source_row") or 0)
            if not uid or old <= 0:
                raise Phase17LeaveUIDError("Cannot reindex canonical leave row without UID/source_row")
            shift = sum(1 for d in deleted if d < old)
            if shift:
                moves.append((uid, old)); finals[uid] = old - shift
        _temporary_reindex(conn, moves, finals)


def _mirror(vpg, mirror_fn, context: str):
    safe = getattr(vpg, "phase17_safe_mirror", None)
    return safe(mirror_fn, context=context) if callable(safe) else mirror_fn()


def _write_one_conn(conn, raw: Mapping[str, Any], operation: str) -> tuple[str, bool]:
    create = str(operation or "").strip().lower() in _CREATE_OPERATIONS
    if create:
        source_id, source_row = _source_identity(raw, required=True)
        uid = _explicit_uid(raw) or _new_uid()
        existing = _fetch_uid_row(conn, uid)
        if existing:
            canonical = _canonical_input(raw, existing, uid)
            source_id, source_row = _source_identity(canonical, required=True)
            normalized = _normalize(canonical, source_row, uid, source_id)
            result = conn.execute(_UPDATE_BY_UID_SQL, _params(normalized, uid))
            if int(result.rowcount or 0) != 1:
                raise Phase17LeaveUIDError(f"UID idempotent create/update affected {result.rowcount} rows: {uid}")
            return uid, False
        _repair_create_collision(conn, source_id, source_row)
        normalized = _normalize(raw, source_row, uid, source_id)
        conn.execute(_INSERT_UID_SQL, _params(normalized, uid))
        return uid, False

    uid, existing, bridged = _resolve_existing(conn, raw)
    canonical = _canonical_input(raw, existing, uid)
    source_id, source_row = _source_identity(canonical, required=True)
    normalized = _normalize(canonical, source_row, uid, source_id)
    result = conn.execute(_UPDATE_BY_UID_SQL, _params(normalized, uid))
    if int(result.rowcount or 0) != 1:
        raise Phase17LeaveUIDError(f"UID update affected {result.rowcount} rows: {uid}")
    return uid, bridged


def leave_upsert(vpg, record: Mapping[str, Any], mirror_fn, operation: str = "upsert"):
    if not _enabled(vpg):
        return _ORIGINAL_UPSERT(record, mirror_fn, operation=operation)
    raw = dict(record or {})
    with _leave_lock(vpg):
        with vpg.get_engine().begin() as conn:
            uid, bridged = _write_one_conn(conn, raw, operation)
        _event(vpg, "phase17_uid_pg_write", f"{operation}; uid={uid}; bridge={int(bridged)}")
        result = _mirror(vpg, mirror_fn, f"leave_uid:{operation}:{uid}")
        _event(vpg, "phase17_uid_mirror_complete", f"{operation}; uid={uid}")
        return result


def leave_batch_upsert(vpg, records: Iterable[Mapping[str, Any]], mirror_fn, operation: str = "batch_upsert"):
    rows = [dict(r or {}) for r in (records or []) if r is not None]
    if not _enabled(vpg):
        return _ORIGINAL_BATCH_UPSERT(rows, mirror_fn, operation=operation)
    if not rows:
        return _mirror(vpg, mirror_fn, f"leave_uid:{operation}:empty")
    with _leave_lock(vpg):
        uids: list[str] = []
        bridge_count = 0
        with vpg.get_engine().begin() as conn:
            for raw in rows:
                uid, bridged = _write_one_conn(conn, raw, operation)
                uids.append(uid); bridge_count += int(bridged)
        _event(vpg, "phase17_uid_pg_batch", f"{operation}; rows={len(uids)}; bridge={bridge_count}")
        result = _mirror(vpg, mirror_fn, f"leave_uid:{operation}:rows={len(uids)}")
        _event(vpg, "phase17_uid_mirror_complete", f"{operation}; rows={len(uids)}")
        return result


def leave_delete(vpg, records: Iterable[Mapping[str, Any]], mirror_fn, operation: str = "delete"):
    rows = [dict(r or {}) for r in (records or []) if r is not None]
    if not _enabled(vpg):
        return _ORIGINAL_DELETE(rows, mirror_fn, operation=operation)
    if not rows:
        return _mirror(vpg, mirror_fn, f"leave_uid:{operation}:empty")
    with _leave_lock(vpg):
        deleted_by_sheet: dict[str, list[int]] = {}
        uids: list[str] = []
        bridge_count = 0
        with vpg.get_engine().begin() as conn:
            for raw in rows:
                uid, existing, bridged = _resolve_existing(conn, raw)
                bridge_count += int(bridged)
                if uid in uids:
                    continue
                uids.append(uid)
                source_id = str(existing.get("source_sheet_id") or "leave_primary").strip()
                source_row = int(existing.get("source_row") or 0)
                if source_row <= 0:
                    raise Phase17LeaveUIDError(f"UID {uid} has invalid mirror source_row")
                deleted_by_sheet.setdefault(source_id, []).append(source_row)
            for uid in uids:
                result = conn.execute(text("DELETE FROM leave_records WHERE record_uid=:u"), {"u": uid})
                if int(result.rowcount or 0) != 1:
                    raise Phase17LeaveUIDError(f"UID delete affected {result.rowcount} rows: {uid}")
            _shift_after_delete(conn, deleted_by_sheet)
        _event(vpg, "phase17_uid_pg_delete", f"{operation}; rows={len(uids)}; bridge={bridge_count}")
        result = _mirror(vpg, mirror_fn, f"leave_uid:{operation}:rows={len(uids)}")
        _event(vpg, "phase17_uid_mirror_complete", f"{operation}; rows={len(uids)}")
        return result


def get_status(vpg) -> dict:
    result = {
        "enabled": bool(_enabled(vpg)),
        "schema_version": PHASE17_UID_SCHEMA_VERSION,
        "identity": "record_uid",
        "mutation_key": "record_uid_only",
        "source_row_role": "legacy_ingress_and_mirror_metadata_only",
        "postgres_canonical": bool(_enabled(vpg)),
        "fail_closed": True,
    }
    if _enabled(vpg):
        try:
            with vpg.get_engine().connect() as conn:
                row = conn.execute(text("""
                    SELECT
                        COUNT(*) AS rows,
                        COUNT(*) FILTER (WHERE record_uid IS NULL OR BTRIM(record_uid)='') AS missing_uid,
                        COUNT(DISTINCT record_uid) AS distinct_uid
                    FROM leave_records
                """)).mappings().first()
            result.update(dict(row or {}))
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def install(vpg) -> bool:
    global _ORIGINAL_UPSERT, _ORIGINAL_BATCH_UPSERT, _ORIGINAL_DELETE
    if vpg is None:
        return False
    if getattr(vpg, "_vera_phase17_uid_crud_installed", False):
        return True
    required = ("phase4_leave_upsert", "phase4_leave_batch_upsert", "phase4_leave_delete", "get_engine")
    if not all(callable(getattr(vpg, name, None)) for name in required):
        return False
    _ORIGINAL_UPSERT = vpg.phase4_leave_upsert
    _ORIGINAL_BATCH_UPSERT = vpg.phase4_leave_batch_upsert
    _ORIGINAL_DELETE = vpg.phase4_leave_delete
    if _enabled(vpg):
        _ensure_schema(vpg)
    vpg.phase4_leave_upsert = lambda record, mirror_fn, operation="upsert": leave_upsert(vpg, record, mirror_fn, operation=operation)
    vpg.phase4_leave_batch_upsert = lambda records, mirror_fn, operation="batch_upsert": leave_batch_upsert(vpg, records, mirror_fn, operation=operation)
    vpg.phase4_leave_delete = lambda records, mirror_fn, operation="delete": leave_delete(vpg, records, mirror_fn, operation=operation)
    vpg.phase17_leave_uid_status = lambda: get_status(vpg)
    vpg._vera_phase17_uid_crud_installed = True
    _event(vpg, "phase17_uid_crud_installed", "record_uid-only canonical CRUD v172 enabled")
    return True

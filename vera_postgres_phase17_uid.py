"""Phase 17.1: record_uid-canonical CRUD for leave_records.

Normal VERA leave UI still supplies the legacy Google Sheet row as compatibility
metadata. This module resolves that locator to a stable record_uid while holding
one PostgreSQL advisory lock, then performs UPDATE/DELETE strictly by record_uid.
Creates receive a new opaque UID before the optional Google Sheets mirror runs.

Google Sheets is never a canonical rollback target in this layer. Phase 17 mirror
policy is preserved (sync/optional/off), but committed PostgreSQL mutations are not
compensated when a mirror fails.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import text

import vera_postgres_phase3 as _phase3


PHASE17_UID_SCHEMA_VERSION = 171
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
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_leave_records_record_uid
            ON leave_records(record_uid)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_leave_records_uid_source
            ON leave_records(record_uid, source_sheet_id, source_row)
        """))
        conn.execute(text(f"""
            INSERT INTO {version_table}(component, version, updated_at)
            VALUES (:component, :version, NOW())
            ON CONFLICT (component) DO UPDATE
            SET version=GREATEST({version_table}.version, EXCLUDED.version),
                updated_at=NOW()
        """), {"component": PHASE17_UID_COMPONENT, "version": PHASE17_UID_SCHEMA_VERSION})


@contextmanager
def _leave_lock(vpg):
    conn = vpg.get_engine().connect()
    locked = False
    try:
        conn.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), {"k": _LOCK_KEY})
        locked = True
        yield
    finally:
        if locked:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": _LOCK_KEY})
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass


def _source_identity(raw: Mapping[str, Any]) -> tuple[str, int]:
    source_id = str(raw.get("__source_sheet_id") or raw.get("source_sheet_id") or "leave_primary").strip()
    source_row = raw.get("__source_row", raw.get("source_row", 0))
    try:
        source_row = int(float(source_row or 0))
    except Exception:
        source_row = 0
    if not source_id or source_row <= 0:
        raise ValueError("Phase 17 UID leave CRUD requires source sheet id and positive source row")
    return source_id, source_row


def _explicit_uid(raw: Mapping[str, Any]) -> str:
    return str(raw.get("record_uid") or raw.get("__record_uid") or "").strip()


def _new_uid() -> str:
    return "lr-" + uuid.uuid4().hex


def _normalize(raw: Mapping[str, Any], source_row: int) -> dict:
    item = _phase3._leave_record(dict(raw or {}), int(source_row))
    if not item:
        raise ValueError("Invalid leave record: employee/reason is required")
    payload = item.get("payload")
    if not isinstance(payload, str):
        payload = json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False, default=str)
    item["payload"] = payload
    return item


def _fetch_uid_row(conn, uid: str):
    if not uid:
        return None
    row = conn.execute(
        text("SELECT * FROM leave_records WHERE record_uid=:u"), {"u": uid}
    ).mappings().first()
    return dict(row) if row else None


def _fetch_source_row(conn, source_id: str, source_row: int):
    row = conn.execute(
        text("""
            SELECT * FROM leave_records
            WHERE source_sheet_id=:s AND source_row=:r
        """),
        {"s": source_id, "r": int(source_row)},
    ).mappings().first()
    return dict(row) if row else None


def _resolve_existing(conn, raw: Mapping[str, Any], allow_source_bridge: bool = True):
    uid = _explicit_uid(raw)
    if uid:
        row = _fetch_uid_row(conn, uid)
        if row:
            return uid, row
        raise Phase17LeaveUIDError(f"record_uid not found: {uid}")
    if not allow_source_bridge:
        return "", None
    source_id, source_row = _source_identity(raw)
    row = _fetch_source_row(conn, source_id, source_row)
    if not row:
        raise Phase17LeaveUIDError(
            f"Cannot resolve legacy Sheet locator {source_id}:{source_row} to record_uid"
        )
    uid = str(row.get("record_uid") or "").strip()
    if not uid:
        raise Phase17LeaveUIDError(
            f"Canonical leave row {source_id}:{source_row} has no record_uid"
        )
    return uid, row


_UPSERT_BY_UID_SQL = text("""
    UPDATE leave_records SET
        source_sheet_id=:source_sheet_id,
        source_row=:source_row,
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


def _temporary_reindex(conn, rows: list[tuple[str, int]], new_rows: Mapping[str, int]) -> None:
    """Move rows through unique negative positions, then to final positive rows."""
    if not rows:
        return
    marker = 1_000_000_000
    for idx, (uid, old_row) in enumerate(rows, start=1):
        tmp = -(marker + int(old_row) * 10 + idx)
        conn.execute(
            text("UPDATE leave_records SET source_row=:r WHERE record_uid=:u"),
            {"r": tmp, "u": uid},
        )
    for uid, _old_row in rows:
        final_row = int(new_rows[uid])
        conn.execute(text("""
            UPDATE leave_records
            SET source_row=:r,
                payload=jsonb_set(
                    COALESCE(payload,'{}'::jsonb),
                    '{__source_row}',
                    to_jsonb(CAST(:r AS INTEGER)),
                    TRUE
                ),
                updated_at=NOW()
            WHERE record_uid=:u
        """), {"r": final_row, "u": uid})


def _repair_create_collision(conn, source_id: str, first_new_row: int) -> None:
    collision = _fetch_source_row(conn, source_id, first_new_row)
    if not collision:
        return
    existing = conn.execute(text("""
        SELECT record_uid,source_row,id
        FROM leave_records
        WHERE source_sheet_id=:s AND source_row IS NOT NULL AND source_row > 0
        ORDER BY source_row,id
    """), {"s": source_id}).mappings().all()
    expected_first_new = len(existing) + 2
    if int(first_new_row) != int(expected_first_new):
        raise Phase17LeaveUIDError(
            "Source-row collision while creating leave record; refusing to overwrite a canonical UID "
            f"(source={source_id}:{first_new_row}, canonical_rows={len(existing)})"
        )
    moves: list[tuple[str, int]] = []
    finals: dict[str, int] = {}
    for pos, row in enumerate(existing, start=2):
        uid = str(row.get("record_uid") or "").strip()
        old = int(row.get("source_row") or 0)
        if not uid:
            raise Phase17LeaveUIDError("Existing canonical leave row has no record_uid")
        if old != pos:
            moves.append((uid, old))
            finals[uid] = pos
    _temporary_reindex(conn, moves, finals)
    if _fetch_source_row(conn, source_id, first_new_row):
        raise Phase17LeaveUIDError(
            f"Could not free mirror source row {source_id}:{first_new_row} without changing UID identity"
        )


def _shift_after_delete(conn, deleted_by_sheet: Mapping[str, list[int]]) -> None:
    for source_id, deleted_rows in deleted_by_sheet.items():
        deleted = sorted({int(r) for r in deleted_rows if int(r) > 0})
        if not deleted:
            continue
        affected = conn.execute(text("""
            SELECT record_uid,source_row,id
            FROM leave_records
            WHERE source_sheet_id=:s AND source_row>:m
            ORDER BY source_row,id
        """), {"s": source_id, "m": min(deleted)}).mappings().all()
        moves: list[tuple[str, int]] = []
        finals: dict[str, int] = {}
        for row in affected:
            uid = str(row.get("record_uid") or "").strip()
            old = int(row.get("source_row") or 0)
            if not uid or old <= 0:
                continue
            shift = sum(1 for d in deleted if d < old)
            new = old - shift
            if new != old:
                moves.append((uid, old))
                finals[uid] = new
        _temporary_reindex(conn, moves, finals)


def _mirror(vpg, mirror_fn, context: str):
    safe = getattr(vpg, "phase17_safe_mirror", None)
    if callable(safe):
        return safe(mirror_fn, context=context)
    return mirror_fn()


def _write_one_conn(conn, raw: Mapping[str, Any], operation: str) -> str:
    source_id, source_row = _source_identity(raw)
    create = str(operation or "").strip().lower() in _CREATE_OPERATIONS
    if create:
        explicit = _explicit_uid(raw)
        if explicit:
            existing = _fetch_uid_row(conn, explicit)
            if existing:
                normalized = _normalize(raw, source_row)
                result = conn.execute(_UPSERT_BY_UID_SQL, _params(normalized, explicit))
                if int(result.rowcount or 0) != 1:
                    raise Phase17LeaveUIDError(f"UID update affected {result.rowcount} rows: {explicit}")
                return explicit
        _repair_create_collision(conn, source_id, source_row)
        uid = explicit or _new_uid()
        normalized = _normalize(raw, source_row)
        conn.execute(_INSERT_UID_SQL, _params(normalized, uid))
        return uid

    uid, _existing = _resolve_existing(conn, raw, allow_source_bridge=True)
    normalized = _normalize(raw, source_row)
    result = conn.execute(_UPSERT_BY_UID_SQL, _params(normalized, uid))
    if int(result.rowcount or 0) != 1:
        raise Phase17LeaveUIDError(f"UID update affected {result.rowcount} rows: {uid}")
    return uid


def leave_upsert(vpg, record: Mapping[str, Any], mirror_fn, operation: str = "upsert"):
    if not _enabled(vpg):
        return _ORIGINAL_UPSERT(record, mirror_fn, operation=operation)
    raw = dict(record or {})
    with _leave_lock(vpg):
        with vpg.get_engine().begin() as conn:
            uid = _write_one_conn(conn, raw, operation)
        _event(vpg, "phase17_uid_pg_write", f"{operation}; uid={uid}")
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
        uids = []
        with vpg.get_engine().begin() as conn:
            for raw in rows:
                uids.append(_write_one_conn(conn, raw, operation))
        _event(vpg, "phase17_uid_pg_batch", f"{operation}; rows={len(uids)}")
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
        with vpg.get_engine().begin() as conn:
            for raw in rows:
                uid, existing = _resolve_existing(conn, raw, allow_source_bridge=True)
                if uid in uids:
                    continue
                uids.append(uid)
                source_id = str(existing.get("source_sheet_id") or "").strip()
                source_row = int(existing.get("source_row") or 0)
                deleted_by_sheet.setdefault(source_id, []).append(source_row)
            for uid in uids:
                result = conn.execute(
                    text("DELETE FROM leave_records WHERE record_uid=:u"), {"u": uid}
                )
                if int(result.rowcount or 0) != 1:
                    raise Phase17LeaveUIDError(f"UID delete affected {result.rowcount} rows: {uid}")
            _shift_after_delete(conn, deleted_by_sheet)
        _event(vpg, "phase17_uid_pg_delete", f"{operation}; rows={len(uids)}")
        result = _mirror(vpg, mirror_fn, f"leave_uid:{operation}:rows={len(uids)}")
        _event(vpg, "phase17_uid_mirror_complete", f"{operation}; rows={len(uids)}")
        return result


def get_status(vpg) -> dict:
    result = {
        "enabled": bool(_enabled(vpg)),
        "schema_version": PHASE17_UID_SCHEMA_VERSION,
        "identity": "record_uid",
        "source_row_role": "compatibility_mirror_metadata_only",
        "postgres_canonical": bool(_enabled(vpg)),
    }
    if _enabled(vpg):
        try:
            with vpg.get_engine().connect() as conn:
                row = conn.execute(text("""
                    SELECT
                        COUNT(*) AS rows,
                        COUNT(*) FILTER (WHERE record_uid IS NULL OR BTRIM(record_uid)='') AS missing_uid,
                        COUNT(DISTINCT record_uid) FILTER (WHERE record_uid IS NOT NULL AND BTRIM(record_uid)<>'') AS distinct_uid
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

    vpg.phase4_leave_upsert = lambda record, mirror_fn, operation="upsert": leave_upsert(
        vpg, record, mirror_fn, operation=operation
    )
    vpg.phase4_leave_batch_upsert = lambda records, mirror_fn, operation="batch_upsert": leave_batch_upsert(
        vpg, records, mirror_fn, operation=operation
    )
    vpg.phase4_leave_delete = lambda records, mirror_fn, operation="delete": leave_delete(
        vpg, records, mirror_fn, operation=operation
    )
    vpg.phase17_leave_uid_status = lambda: get_status(vpg)
    vpg._vera_phase17_uid_crud_installed = True
    _event(vpg, "phase17_uid_crud_installed", "record_uid canonical CRUD enabled")
    return True

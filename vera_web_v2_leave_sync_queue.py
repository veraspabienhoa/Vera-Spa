"""Durable PostgreSQL outbox for Web V2 leave -> Google Sheets mirroring."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from fastapi import Depends, HTTPException
from sqlalchemy import text

RELEASE = "leave-sync-queue-2026-09-02.1"
QUEUE_TABLE = "vera_leave_sheet_sync_queue"
_worker_started = False
_worker_lock = threading.Lock()


def _required_leave_type(record: dict[str, Any]) -> str:
    leave_type = str(record.get("leave_type") or "").strip()
    if not leave_type:
        raise HTTPException(
            400,
            "Lý do nghỉ chưa được cấu hình Loại nghỉ trong Nội quy/LoaiNghi.",
        )
    return leave_type


def _sheet_values_with_required_leave_type(*, api_module, headers: list[str], record: dict, source_row: int) -> list[Any]:
    normalized_headers = [api_module._norm(header) for header in headers]
    leave_type_header = api_module._norm("Loại nghỉ")
    if leave_type_header not in normalized_headers:
        raise RuntimeError("MainData chưa có cột Loại nghỉ trong A:M")
    row_values = api_module._sheet_values_for_record(headers, record, source_row)
    leave_type_index = normalized_headers.index(leave_type_header)
    if not str(row_values[leave_type_index] or "").strip():
        raise RuntimeError("Bản ghi lịch nghỉ chưa có Loại nghỉ nên chưa thể ghi MainData")
    return row_values


def _remove_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        if getattr(route, "path", "") == path and wanted in set(getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def _ensure_schema(engine_instance: Callable[[], Any]) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {QUEUE_TABLE} (
                id BIGSERIAL PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                record_uid TEXT NOT NULL UNIQUE,
                source_row INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                locked_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                last_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{QUEUE_TABLE}_pending ON {QUEUE_TABLE}(status, next_attempt_at, id)"))


def _allocate_source_row(conn, leave_sheet_id: str) -> int:
    value = conn.execute(text("""
        SELECT COALESCE(MAX(source_row), 1) + 1 FROM leave_records
        WHERE source_sheet_id=:sid AND source_row IS NOT NULL
    """), {"sid": leave_sheet_id}).scalar() or 2
    return max(2, int(value))


def _insert_leave_and_queue(conn, *, api_module, record: dict, source_row: int) -> None:
    payload = api_module._record_payload(record, source_row)
    conn.execute(text("""
        INSERT INTO leave_records(
            source_sheet_id, source_row, leave_date, employee_name, leave_reason,
            leave_type, detail, calculated_days, accumulated_leave, penalty,
            update_date, update_time, updated_by, weekday_label, payload, record_uid,
            created_at, updated_at
        ) VALUES (
            :sid, :srow, :leave_date, :employee_name, :leave_reason,
            :leave_type, :detail, :calculated_days, :accumulated_leave, :penalty,
            :update_date, :update_time, :updated_by, :weekday_label, CAST(:payload AS jsonb), :record_uid,
            NOW(), NOW()
        )
    """), {**record, "sid": api_module.LEAVE_SHEET_ID, "srow": source_row, "payload": api_module.json_text(payload)})
    conn.execute(text(f"""
        INSERT INTO {QUEUE_TABLE}(idempotency_key,record_uid,source_row,status,attempts,next_attempt_at,created_at,updated_at)
        VALUES (:key,:uid,:source_row,'pending',0,NOW(),NOW(),NOW())
        ON CONFLICT (idempotency_key) DO NOTHING
    """), {"key": f"leave:create:{record['record_uid']}", "uid": record["record_uid"], "source_row": source_row})
    try:
        with conn.begin_nested():
            conn.execute(text("""
                INSERT INTO vera_sync_event(dataset_key,event_type,detail,created_at)
                VALUES ('leave_primary','web_v2_leave_create_queued',:detail,NOW())
            """), {"detail": f"record_uid={record['record_uid']}; source_row={source_row}; actor={record['updated_by']}"})
    except Exception:
        pass


def _claim_one(engine_instance):
    with engine_instance().begin() as conn:
        row = conn.execute(text(f"""
            SELECT id,record_uid,source_row,attempts FROM {QUEUE_TABLE}
            WHERE status IN ('pending','retry') AND next_attempt_at<=NOW()
            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
        """)).mappings().first()
        if not row:
            return None
        conn.execute(text(f"UPDATE {QUEUE_TABLE} SET status='processing',locked_at=NOW(),updated_at=NOW() WHERE id=:id"), {"id": row["id"]})
        return dict(row)


def _record_for_uid(engine_instance, uid: str):
    with engine_instance().connect() as conn:
        row = conn.execute(text("""
            SELECT record_uid,source_row,leave_date,employee_name,leave_reason,leave_type,detail,
                   calculated_days,accumulated_leave,penalty,update_date,update_time,updated_by,weekday_label
            FROM leave_records WHERE record_uid=:uid
        """), {"uid": uid}).mappings().first()
        return dict(row) if row else None


def _mark_done(engine_instance, item_id: int) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {QUEUE_TABLE} SET status='done',completed_at=NOW(),last_error=NULL,locked_at=NULL,updated_at=NOW()
            WHERE id=:id
        """), {"id": item_id})


def _mark_retry(engine_instance, item, exc: Exception) -> None:
    attempts = int(item.get("attempts") or 0) + 1
    delay = min(3600, 15 * (2 ** min(attempts - 1, 8)))
    status = "failed" if attempts >= 12 else "retry"
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {QUEUE_TABLE}
            SET status=:status,attempts=:attempts,next_attempt_at=NOW()+(:delay*INTERVAL '1 second'),
                last_error=:error,locked_at=NULL,updated_at=NOW() WHERE id=:id
        """), {"id": item["id"], "status": status, "attempts": attempts, "delay": delay, "error": f"{type(exc).__name__}: {exc}"[:2000]})


def _process_one(*, engine_instance, api_module) -> bool:
    item = _claim_one(engine_instance)
    if not item:
        return False
    try:
        record = _record_for_uid(engine_instance, str(item["record_uid"]))
        if not record:
            _mark_done(engine_instance, int(item["id"]))
            return True
        source_row = int(record.get("source_row") or item["source_row"])
        ws = api_module._google_client().open_by_key(api_module.LEAVE_SHEET_ID).worksheet("MainData")
        values = ws.get_all_values()
        headers = values[0][:13] if values else []
        if not headers:
            raise RuntimeError("MainData chưa có header A:M")
        row_values = _sheet_values_with_required_leave_type(
            api_module=api_module,
            headers=headers,
            record=record,
            source_row=source_row,
        )
        ws.update(
            range_name=f"A{source_row}:M{source_row}",
            values=[row_values],
            value_input_option="USER_ENTERED",
        )
        _mark_done(engine_instance, int(item["id"]))
        return True
    except Exception as exc:
        _mark_retry(engine_instance, item, exc)
        return True


def _worker_loop(*, engine_instance, api_module) -> None:
    while True:
        try:
            if not _process_one(engine_instance=engine_instance, api_module=api_module):
                time.sleep(3)
        except Exception:
            time.sleep(5)


def _start_worker(*, engine_instance, api_module) -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(target=_worker_loop, kwargs={"engine_instance": engine_instance, "api_module": api_module}, name="vera-leave-sheet-sync", daemon=True).start()
        _worker_started = True


def install_leave_sync_queue(app, *, engine_instance, current_identity, require_feature, validate_and_prepare, identity_type, api_module) -> None:
    if getattr(app.state, "leave_sync_queue_installed", False):
        return
    globals().update({"identity_type": identity_type, "leave_create_type": api_module.LeaveCreate})
    _ensure_schema(engine_instance)
    original = _remove_route(app, "/v2/leave/records", "POST")
    if not callable(original):
        raise RuntimeError("Không tìm thấy route đăng ký lịch nghỉ để cài hàng đợi đồng bộ.")

    @app.post("/v2/leave/records")
    def create_leave_queued(body: leave_create_type, ident: identity_type = Depends(current_identity)):
        conn = engine_instance().connect()
        tx = conn.begin()
        try:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
            require_feature(conn, ident, "leave_create")
            if api_module._registration_role_locked(conn, ident.role):
                raise HTTPException(403, "Quyền đăng ký nghỉ của vai trò này đang bị Admin tạm khóa.")
            record, warnings = validate_and_prepare(conn, body, ident)
            record["leave_type"] = _required_leave_type(record)
            source_row = _allocate_source_row(conn, api_module.LEAVE_SHEET_ID)
            record["source_row"] = source_row
            _insert_leave_and_queue(conn, api_module=api_module, record=record, source_row=source_row)
            tx.commit()
            return {"ok": True, "record_uid": record["record_uid"], "record": record, "warnings": warnings, "mirror_pending": True, "message": "Đã ghi lịch nghỉ THÀNH CÔNG"}
        except HTTPException:
            if tx.is_active: tx.rollback()
            raise
        except Exception as exc:
            if tx.is_active: tx.rollback()
            raise HTTPException(500, f"Không ghi được lịch nghỉ: {type(exc).__name__}: {exc}") from exc
        finally:
            conn.close()

    @app.post("/v2/leave/sync-pending")
    def sync_pending(ident: identity_type = Depends(current_identity)):
        if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được đồng bộ MainData thủ công.")
        processed = 0
        for _ in range(200):
            if not _process_one(engine_instance=engine_instance, api_module=api_module): break
            processed += 1
        with engine_instance().connect() as conn:
            pending = conn.execute(text(f"SELECT COUNT(*) FROM {QUEUE_TABLE} WHERE status IN ('pending','retry','processing')")).scalar() or 0
            failed = conn.execute(text(f"SELECT COUNT(*) FROM {QUEUE_TABLE} WHERE status='failed'")).scalar() or 0
        return {"ok": True, "processed": processed, "pending": int(pending), "failed": int(failed)}

    @app.get("/v2/leave/sync-queue/health")
    def sync_queue_health():
        with engine_instance().connect() as conn:
            counts = conn.execute(text(f"SELECT status,COUNT(*) AS n FROM {QUEUE_TABLE} GROUP BY status")).mappings().all()
        return {"ok": True, "release": RELEASE, "durable": True, "idempotency": "record_uid+source_row", "counts": {str(row["status"]): int(row["n"]) for row in counts}}

    _start_worker(engine_instance=engine_instance, api_module=api_module)
    app.state.leave_sync_queue_installed = True
    app.state.leave_sync_queue_release = RELEASE

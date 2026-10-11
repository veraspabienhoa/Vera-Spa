"""Durable PostgreSQL outbox for Web V2 leave -> Google Sheets mirroring."""
from __future__ import annotations

from typing import Any, Callable
from contextlib import contextmanager

import gspread
import requests
from google.auth.transport.requests import AuthorizedSession, Request as GoogleAuthRequest

from fastapi import Depends, HTTPException
from sqlalchemy import text
import vera_resource_concurrency as resource_concurrency

RELEASE = "leave-sync-queue-2026-09-02.1"
QUEUE_TABLE = "vera_leave_sheet_sync_queue"


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
        resource_concurrency.ensure_schema(conn)
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
    return resource_concurrency.next_counter(
        conn, scope="leave_sheet", counter_key=leave_sheet_id,
        floor=max(1, int(value) - 1),
    )


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
        # Recover a crashed process without touching a live/locked owner.
        conn.execute(text(f"""WITH expired AS (
            SELECT id FROM {QUEUE_TABLE} WHERE status='processing'
              AND (locked_at IS NULL OR locked_at < NOW()-INTERVAL '10 minutes')
            FOR UPDATE SKIP LOCKED
        ) UPDATE {QUEUE_TABLE} q SET status='retry',locked_at=NULL,
            next_attempt_at=NOW(),updated_at=NOW()
            FROM expired e WHERE q.id=e.id"""))
        row = conn.execute(text(f"""
            SELECT id,record_uid,source_row,attempts FROM {QUEUE_TABLE}
            WHERE status IN ('pending','retry') AND next_attempt_at<=NOW()
            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
        """)).mappings().first()
        if not row:
            return None
        lease = conn.execute(text(f"""UPDATE {QUEUE_TABLE}
            SET status='processing',locked_at=clock_timestamp(),updated_at=NOW()
            WHERE id=:id RETURNING locked_at"""), {"id": row["id"]}).scalar_one()
        return {**dict(row), 'locked_at': lease}


def _record_for_uid(engine_instance, uid: str):
    with engine_instance().connect() as conn:
        row = conn.execute(text("""
            SELECT record_uid,source_row,leave_date,employee_name,leave_reason,leave_type,detail,
                   calculated_days,accumulated_leave,penalty,update_date,update_time,updated_by,weekday_label
            FROM leave_records WHERE record_uid=:uid
        """), {"uid": uid}).mappings().first()
        return dict(row) if row else None


def _mark_done(engine_instance, item) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {QUEUE_TABLE} SET status='done',completed_at=NOW(),last_error=NULL,locked_at=NULL,updated_at=NOW()
            WHERE id=:id AND status='processing' AND locked_at=:locked_at
        """), {"id": item['id'], "locked_at": item['locked_at']})


def _mark_retry(engine_instance, item, exc: Exception) -> None:
    attempts = int(item.get("attempts") or 0) + 1
    delay = min(3600, 15 * (2 ** min(attempts - 1, 8)))
    status = "failed" if attempts >= 12 else "retry"
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            UPDATE {QUEUE_TABLE}
            SET status=:status,attempts=:attempts,next_attempt_at=NOW()+(:delay*INTERVAL '1 second'),
                last_error=:error,locked_at=NULL,updated_at=NOW()
            WHERE id=:id AND status='processing' AND locked_at=:locked_at
        """), {"id": item["id"], "locked_at": item['locked_at'], "status": status,
                 "attempts": attempts, "delay": delay, "error": type(exc).__name__})


class BoundedMirrorSession(AuthorizedSession):
    def request(self, method, url, **kwargs):
        # Bound both the actual Sheets request and credential refresh retries.
        # A private session avoids changing the shared browser/API client.
        kwargs['timeout'] = (5, 30)
        kwargs['max_allowed_time'] = min(float(kwargs.get('max_allowed_time') or 45), 45)
        return super().request(method, url, **kwargs)


@contextmanager
def _mirror_client(api_module):
    credentials = api_module._google_client().http_client.auth
    # Supply the public auth_request hook: google-auth's refresh_timeout field
    # is not an enforced deadline in all supported versions. A plain requests
    # session has no automatic retries; clamp the actual token request timeout.
    auth_session = requests.Session()
    auth_transport = GoogleAuthRequest(session=auth_session)
    def auth_request(*args, **kwargs):
        kwargs['timeout'] = (5, 10)
        return auth_transport(*args, **kwargs)
    session = BoundedMirrorSession(credentials, auth_request=auth_request, max_refresh_attempts=1)
    try:
        client = gspread.Client(auth=credentials, session=session)
        client.http_client.set_timeout((5, 30))
        yield client
    finally:
        session.close()
        auth_session.close()


def _renew_claim(engine_instance, item) -> bool:
    with engine_instance().begin() as conn:
        lease = conn.execute(text(f"""UPDATE {QUEUE_TABLE}
            SET locked_at=clock_timestamp(),updated_at=NOW()
            WHERE id=:id AND status='processing' AND locked_at=:locked_at
            RETURNING locked_at"""),
            {'id': item['id'], 'locked_at': item['locked_at']}).scalar_one_or_none()
    if lease is None:
        return False
    item['locked_at'] = lease
    return True


def _process_one(*, engine_instance, api_module) -> bool:
    item = _claim_one(engine_instance)
    if not item:
        return False
    try:
        record = _record_for_uid(engine_instance, str(item["record_uid"]))
        if not record:
            _mark_done(engine_instance, item)
            return True
        source_row = int(record.get("source_row") or item["source_row"])
        # Renew the committed token before every outbound step. A near-expired
        # claim gets a full lease; a detected stale owner cannot start the next
        # remote step. Sheets cannot fence a request that is already in flight.
        if not _renew_claim(engine_instance, item):
            return True
        with _mirror_client(api_module) as client:
            spreadsheet = client.open_by_key(api_module.LEAVE_SHEET_ID)
            if not _renew_claim(engine_instance, item):
                return True
            ws = spreadsheet.worksheet("MainData")
            if not _renew_claim(engine_instance, item):
                return True
            values = ws.get_all_values()
            headers = values[0][:13] if values else []
            if not headers:
                raise RuntimeError("MainData chưa có header A:M")
            row_values = _sheet_values_with_required_leave_type(
                api_module=api_module, headers=headers, record=record, source_row=source_row,
            )
            if not _renew_claim(engine_instance, item):
                return True
            ws.update(
                range_name=f"A{source_row}:M{source_row}", values=[row_values],
                value_input_option="USER_ENTERED",
            )
        _mark_done(engine_instance, item)
        return True
    except Exception as exc:
        _mark_retry(engine_instance, item, exc)
        return True


def _lease_current(engine_instance, item) -> bool:
    with engine_instance().connect() as conn:
        return bool(conn.execute(text(f"""SELECT 1 FROM {QUEUE_TABLE}
            WHERE id=:id AND status='processing' AND locked_at=:locked_at"""),
            {'id': item['id'], 'locked_at': item['locked_at']}).scalar())


def _worker_loop(stop, *, engine_instance, api_module) -> None:
    while not stop.is_set():
        try:
            if not _process_one(engine_instance=engine_instance, api_module=api_module):
                stop.wait(3)
            else:
                # A busy queue still reports progress and honors graceful stop.
                stop.wait(0)
        except Exception:
            stop.wait(5)


def install_leave_sync_queue(app, *, engine_instance, current_identity, require_feature, validate_and_prepare, identity_type, api_module) -> None:
    if getattr(app.state, "leave_sync_queue_installed", False):
        return
    globals().update({"identity_type": identity_type, "leave_create_type": api_module.LeaveCreate})
    original = _remove_route(app, "/v2/leave/records", "POST")
    if not callable(original):
        raise RuntimeError("Không tìm thấy route đăng ký lịch nghỉ để cài hàng đợi đồng bộ.")

    @app.post("/v2/leave/records")
    def create_leave_queued(body: leave_create_type, ident: identity_type = Depends(current_identity)):
        conn = engine_instance().connect()
        tx = conn.begin()
        try:
            resource_concurrency.lock_transition(
                conn,
                [("leave_employee", body.employee_name)],
                legacy_keys=["vera:phase4:leave_primary"],
            )
            role = str(getattr(ident, "role", "") or "").strip().lower()
            employee_policy = api_module.load_employee_self_service_policy(conn)
            if role not in api_module._EMPLOYEE_SELF_SERVICE_ROLES or not employee_policy["enabled"]:
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

    from vera_worker_runtime import register_worker
    register_worker(app, engine_instance=engine_instance, name='vera-leave-sheet-sync',
        target=lambda stop: _worker_loop(stop, engine_instance=engine_instance, api_module=api_module),
        prepare=lambda: _ensure_schema(engine_instance))
    app.state.leave_sync_queue_installed = True
    app.state.leave_sync_queue_release = RELEASE

"""Detailed leave-change audit + 30-day Admin-only revision archive for Web V2.

The archive is enforced with a PostgreSQL trigger on ``leave_records`` so the
pre-edit/pre-delete version is captured in the same database transaction as the
business write.  The Admin change feed is rebuilt from this structured log and
shows exact field-level differences instead of a generic activity message.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import Depends, HTTPException, Query
from sqlalchemy import bindparam, text


ARCHIVE_TABLE = "vera_v2_leave_change_detail"
ARCHIVE_DAYS = 30

FIELD_LABELS = {
    "leave_date": "Ngày",
    "employee_name": "Tên nhân viên",
    "leave_reason": "Lý do nghỉ",
    "leave_type": "Loại nghỉ",
    "detail": "Chi tiết",
    "calculated_days": "Số ngày tính",
    "accumulated_leave": "Số ngày phép cộng dồn",
    "penalty": "Phạt vi phạm",
    "updated_by": "Người cập nhật",
    "record_uid": "Mã bản ghi",
}
IMPORTANT_FIELDS = list(FIELD_LABELS)
IGNORED_DIFF_FIELDS = {"id", "sheet_row", "created_at", "updated_at"}


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return dict(parsed) if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _field_changes(old_data: dict[str, Any], new_data: dict[str, Any], event_type: str) -> list[dict[str, str]]:
    if event_type == "insert":
        keys = [key for key in IMPORTANT_FIELDS if key in new_data]
    elif event_type == "delete":
        keys = [key for key in IMPORTANT_FIELDS if key in old_data]
    else:
        ordered = IMPORTANT_FIELDS + sorted((set(old_data) | set(new_data)) - set(IMPORTANT_FIELDS))
        keys = [key for key in ordered if key not in IGNORED_DIFF_FIELDS and old_data.get(key) != new_data.get(key)]
    output = []
    for key in keys:
        before = "" if event_type == "insert" else _text_value(old_data.get(key))
        after = "" if event_type == "delete" else _text_value(new_data.get(key))
        if event_type == "update" and before == after:
            continue
        output.append({
            "field": key,
            "label": FIELD_LABELS.get(key, key),
            "before": before,
            "after": after,
        })
    return output


def _summary(event_type: str, old_data: dict[str, Any], new_data: dict[str, Any], actor: str) -> str:
    source = new_data if event_type != "delete" else old_data
    employee = str(source.get("employee_name") or "").strip() or "Không rõ nhân viên"
    leave_date = str(source.get("leave_date") or "").strip()
    reason = str(source.get("leave_reason") or "").strip()
    action = {"insert": "Đăng ký mới", "update": "Sửa lịch nghỉ", "delete": "Xóa lịch nghỉ"}.get(event_type, event_type)
    parts = [action, employee]
    if leave_date:
        parts.append(leave_date)
    if reason:
        parts.append(reason)
    if actor:
        parts.append(f"thực hiện bởi {actor}")
    return " · ".join(parts)


def _remove_route(app, path: str, method: str):
    method = method.upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def _ensure_schema(engine_instance: Callable[[], Any]) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {ARCHIVE_TABLE} (
                id BIGSERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                record_uid TEXT NOT NULL DEFAULT '',
                employee_name TEXT NOT NULL DEFAULT '',
                leave_date TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'leave_records_trigger',
                old_data JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                new_data JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '{ARCHIVE_DAYS} days')
            )
        """))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{ARCHIVE_TABLE}_created ON {ARCHIVE_TABLE}(created_at DESC)"))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{ARCHIVE_TABLE}_record ON {ARCHIVE_TABLE}(record_uid, created_at DESC)"))
        conn.execute(text(f"""
            CREATE OR REPLACE FUNCTION vera_v2_capture_leave_change_detail()
            RETURNS trigger AS $$
            DECLARE
                oldj jsonb := CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) ELSE '{{}}'::jsonb END;
                newj jsonb := CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) ELSE '{{}}'::jsonb END;
                event_name text := lower(TG_OP);
                actor_name text := '';
            BEGIN
                DELETE FROM {ARCHIVE_TABLE} WHERE expires_at < NOW();
                IF TG_OP IN ('INSERT','UPDATE') THEN
                    actor_name := COALESCE(newj->>'updated_by', newj->>'updated_by_username', '');
                ELSE
                    actor_name := COALESCE(oldj->>'updated_by', oldj->>'updated_by_username', '');
                END IF;
                INSERT INTO {ARCHIVE_TABLE}(
                    event_type, record_uid, employee_name, leave_date, actor,
                    old_data, new_data, created_at, expires_at
                ) VALUES (
                    event_name,
                    COALESCE(newj->>'record_uid', oldj->>'record_uid', ''),
                    COALESCE(newj->>'employee_name', oldj->>'employee_name', ''),
                    COALESCE(newj->>'leave_date', oldj->>'leave_date', ''),
                    actor_name,
                    oldj, newj, NOW(), NOW() + INTERVAL '{ARCHIVE_DAYS} days'
                );
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        conn.execute(text("DROP TRIGGER IF EXISTS trg_vera_v2_leave_change_detail ON leave_records"))
        conn.execute(text("""
            CREATE TRIGGER trg_vera_v2_leave_change_detail
            AFTER INSERT OR UPDATE OR DELETE ON leave_records
            FOR EACH ROW EXECUTE FUNCTION vera_v2_capture_leave_change_detail()
        """))


def install_admin_audit_archive_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature,
    identity_type,
    leave_update_type,
    leave_delete_type,
) -> None:
    if getattr(app.state, "leave_audit_archive_installed", False):
        return

    # Install the trigger immediately at process start. If this fails, startup
    # fails too, preventing a deployment that could silently lose revisions.
    _ensure_schema(engine_instance)

    original_update = _remove_route(app, "/v2/leave/records/{record_uid}", "PATCH")
    original_delete = _remove_route(app, "/v2/leave/records", "DELETE")
    _remove_route(app, "/v2/admin/changes", "GET")
    if not callable(original_update) or not callable(original_delete):
        raise RuntimeError("Không tìm thấy route sửa/xóa lịch nghỉ để cài lưu phiên bản 30 ngày.")

    def _stamp_actor(event_type: str, record_uids: list[str], actor: str) -> None:
        uids = [str(uid or "").strip() for uid in record_uids if str(uid or "").strip()]
        if not uids:
            return
        stmt = text(f"""
            UPDATE {ARCHIVE_TABLE}
            SET actor=:actor
            WHERE event_type=:event_type
              AND record_uid IN :uids
              AND created_at >= NOW() - INTERVAL '5 minutes'
        """).bindparams(bindparam("uids", expanding=True))
        with engine_instance().begin() as conn:
            conn.execute(stmt, {"actor": str(actor or ""), "event_type": event_type, "uids": uids})

    @app.patch("/v2/leave/records/{record_uid}")
    def update_leave_archived(record_uid: str, body: leave_update_type, ident: identity_type = Depends(current_identity)):
        result = original_update(record_uid=record_uid, body=body, ident=ident)
        _stamp_actor("update", [record_uid], ident.employee_username)
        return result

    @app.delete("/v2/leave/records")
    def delete_leave_archived(body: leave_delete_type, ident: identity_type = Depends(current_identity)):
        record_uids = list(body.record_uids or [])
        result = original_delete(body=body, ident=ident)
        _stamp_actor("delete", record_uids, ident.employee_username)
        return result

    @app.get("/v2/admin/changes")
    def admin_changes_detailed(
        days: int = Query(default=7, ge=1, le=31),
        ident: identity_type = Depends(current_identity),
    ):
        if str(ident.role or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được xem nhật ký và bản lưu lịch nghỉ đã sửa/xóa.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "audit_admin_view")
            conn.execute(text(f"DELETE FROM {ARCHIVE_TABLE} WHERE expires_at < NOW()"))
            rows = conn.execute(text(f"""
                SELECT id, event_type, record_uid, employee_name, leave_date,
                       actor, source, old_data, new_data, created_at, expires_at
                FROM {ARCHIVE_TABLE}
                WHERE created_at >= NOW() - (:days * INTERVAL '1 day')
                ORDER BY created_at DESC, id DESC
                LIMIT 1500
            """), {"days": days}).mappings().all()
            archive_rows = conn.execute(text(f"""
                SELECT id, event_type, record_uid, employee_name, leave_date,
                       actor, source, old_data, new_data, created_at, expires_at
                FROM {ARCHIVE_TABLE}
                WHERE event_type IN ('update','delete')
                  AND created_at >= NOW() - INTERVAL '{ARCHIVE_DAYS} days'
                  AND expires_at >= NOW()
                ORDER BY created_at DESC, id DESC
                LIMIT 3000
            """)).mappings().all()

        def serialize(row):
            old_data = _json_dict(row.get("old_data"))
            new_data = _json_dict(row.get("new_data"))
            event_type = str(row.get("event_type") or "")
            actor = str(row.get("actor") or "")
            return {
                "id": int(row.get("id") or 0),
                "event_type": event_type,
                "record_uid": str(row.get("record_uid") or ""),
                "employee_name": str(row.get("employee_name") or ""),
                "leave_date": str(row.get("leave_date") or ""),
                "actor": actor,
                "source": str(row.get("source") or ""),
                "detail": _summary(event_type, old_data, new_data, actor),
                "field_changes": _field_changes(old_data, new_data, event_type),
                "old_data": old_data,
                "new_data": new_data,
                "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
                "expires_at": row["expires_at"].isoformat() if row.get("expires_at") else "",
            }

        changes = [serialize(row) for row in rows]
        archive = [serialize(row) for row in archive_rows]
        return {
            "changes": changes,
            "count": len(changes),
            "days": days,
            "archive": archive,
            "archive_count": len(archive),
            "archive_days": ARCHIVE_DAYS,
        }

    app.state.leave_audit_archive_installed = True

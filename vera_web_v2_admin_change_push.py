"""Immediate lock-screen Web Push for Admin when leave-system changes occur.

This module wraps the final canonical leave write routes after all policy/audit
wrappers are installed. Successful create/update/delete operations enqueue a
background push containing the exact audit summary and field-level changes.
Only active Admin push subscriptions receive these notifications.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import BackgroundTasks, Depends
from sqlalchemy import bindparam, text

import vera_web_v2_admin_audit_archive as audit


RELEASE = "4.2-admin-instant-change-push"
APP_URL = "https://veraspabienhoa.github.io/Vera-Spa/"


def _remove_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def _compact_body(event_type: str, old_data: dict[str, Any], new_data: dict[str, Any], actor: str) -> str:
    summary = audit._summary(event_type, old_data, new_data, actor)
    changes = audit._field_changes(old_data, new_data, event_type)
    detail_parts: list[str] = []
    for change in changes:
        field = str(change.get("field") or "")
        if field in {"record_uid", "updated_by"}:
            continue
        label = str(change.get("label") or field)
        before = str(change.get("before") or "—")
        after = str(change.get("after") or "—")
        if event_type == "insert":
            text_value = f"{label}: {after}"
        elif event_type == "delete":
            text_value = f"{label}: {before}"
        else:
            text_value = f"{label}: {before} → {after}"
        detail_parts.append(text_value)
        if len(detail_parts) >= 4:
            break
    body = summary
    if detail_parts:
        body += "\n" + " · ".join(detail_parts)
    return body[:900]


def _dispatch_admin_change_pushes(
    *,
    engine_instance: Callable[[], Any],
    api_module,
    event_type: str,
    record_uids: list[str],
    actor: str,
) -> None:
    """Best-effort delivery; a push failure must never undo a business write."""
    try:
        uids = [str(value or "").strip() for value in record_uids if str(value or "").strip()]
        if not uids:
            return
        with engine_instance().connect() as conn:
            private_key = api_module._vault_secret(conn, "vera_v2_vapid_private_key")
            subject = api_module._vault_secret(conn, "vera_v2_vapid_subject") or APP_URL
            if not private_key:
                return
            stmt = text(f"""
                SELECT id, event_type, record_uid, employee_name, leave_date,
                       actor, old_data, new_data, created_at
                FROM {audit.ARCHIVE_TABLE}
                WHERE event_type=:event_type
                  AND record_uid IN :uids
                  AND created_at >= NOW() - INTERVAL '10 minutes'
                ORDER BY id DESC
            """).bindparams(bindparam("uids", expanding=True))
            rows = conn.execute(stmt, {"event_type": event_type, "uids": uids}).mappings().all()
            latest: dict[str, dict[str, Any]] = {}
            for row in rows:
                uid = str(row.get("record_uid") or "")
                if uid and uid not in latest:
                    latest[uid] = dict(row)
            subscriptions = conn.execute(text("""
                SELECT s.subscription_id::text AS subscription_id,
                       s.endpoint, s.p256dh, s.auth_secret
                FROM vera_v2_push_subscription s
                JOIN vera_v2_user_profile p ON p.auth_user_id=s.auth_user_id
                WHERE s.is_active=true
                  AND p.is_active=true
                  AND lower(COALESCE(p.role,''))='admin'
                ORDER BY s.updated_at DESC
            """)).mappings().all()

        if not latest or not subscriptions:
            return

        delivery_results: list[dict[str, Any]] = []
        for uid in uids:
            row = latest.get(uid)
            if not row:
                continue
            old_data = audit._json_dict(row.get("old_data"))
            new_data = audit._json_dict(row.get("new_data"))
            effective_actor = str(row.get("actor") or actor or "")
            action_label = {
                "insert": "Đăng ký mới",
                "update": "Sửa lịch nghỉ",
                "delete": "Xóa lịch nghỉ",
            }.get(event_type, "Thay đổi hệ thống")
            created_at = row.get("created_at")
            timestamp = int(created_at.timestamp() * 1000) if isinstance(created_at, datetime) else 0
            payload = {
                "title": f"VERA SPA · {action_label}",
                "body": _compact_body(event_type, old_data, new_data, effective_actor),
                "url": APP_URL,
                "tag": f"vera-system-change-{row['id']}",
                "kind": "admin-system-change",
                "change_id": int(row["id"]),
                "dismissible": True,
                "timestamp": timestamp,
            }
            for subscription in subscriptions:
                delivery = {**dict(subscription), "payload": payload}
                ok, status, error_text = api_module._send_web_push(delivery, private_key, subject)
                inactive = (not ok) and status in {404, 410}
                delivery_results.append({
                    "subscription_id": subscription["subscription_id"],
                    "ok": bool(ok),
                    "inactive": bool(inactive),
                    "last_error": str(error_text or "")[:1000],
                })

        if delivery_results:
            with engine_instance().begin() as conn:
                for result in delivery_results:
                    conn.execute(text("""
                        UPDATE vera_v2_push_subscription
                        SET is_active=CASE WHEN :inactive THEN false ELSE is_active END,
                            last_success_at=CASE WHEN :ok THEN NOW() ELSE last_success_at END,
                            failure_count=CASE WHEN :ok THEN 0 ELSE failure_count + 1 END,
                            last_error=CASE WHEN :ok THEN NULL ELSE :last_error END,
                            updated_at=NOW()
                        WHERE subscription_id=CAST(:subscription_id AS uuid)
                    """), result)
    except Exception:
        # Background notifications are intentionally non-blocking and must not
        # surface as a failed leave write after the database/sheet commit.
        return


def install_admin_change_push(
    app,
    *,
    engine_instance: Callable[[], Any],
    api_module,
    current_identity,
    identity_type,
    leave_create_type,
    leave_update_type,
    leave_delete_type,
) -> None:
    if getattr(app.state, "admin_change_push_installed", False):
        return

    # This module enables postponed annotations.  FastAPI resolves the nested
    # route annotations against module globals, not this installer's local
    # arguments.  Publish the concrete models before registering the wrapper
    # routes; otherwise ``body`` becomes an unresolved ForwardRef, every write
    # returns 422 (missing query parameter ``body``), and OpenAPI returns 500.
    globals().update({
        "identity_type": identity_type,
        "leave_create_type": leave_create_type,
        "leave_update_type": leave_update_type,
        "leave_delete_type": leave_delete_type,
    })

    original_create = _remove_route(app, "/v2/leave/records", "POST")
    original_update = _remove_route(app, "/v2/leave/records/{record_uid}", "PATCH")
    original_delete = _remove_route(app, "/v2/leave/records", "DELETE")
    if not all(callable(item) for item in (original_create, original_update, original_delete)):
        raise RuntimeError("Không tìm thấy đủ route lịch nghỉ để cài thông báo Admin tức thời.")

    def enqueue(background_tasks: BackgroundTasks, event_type: str, record_uids: list[str], actor: str) -> None:
        background_tasks.add_task(
            _dispatch_admin_change_pushes,
            engine_instance=engine_instance,
            api_module=api_module,
            event_type=event_type,
            record_uids=record_uids,
            actor=actor,
        )

    @app.post("/v2/leave/records")
    def create_leave_with_admin_push(
        body: leave_create_type,
        background_tasks: BackgroundTasks,
        ident: identity_type = Depends(current_identity),
    ):
        result = original_create(body=body, ident=ident)
        uid = str((result or {}).get("record_uid") or "") if isinstance(result, dict) else ""
        if uid:
            enqueue(background_tasks, "insert", [uid], ident.employee_username)
        return result

    @app.patch("/v2/leave/records/{record_uid}")
    def update_leave_with_admin_push(
        record_uid: str,
        body: leave_update_type,
        background_tasks: BackgroundTasks,
        ident: identity_type = Depends(current_identity),
    ):
        result = original_update(record_uid=record_uid, body=body, ident=ident)
        enqueue(background_tasks, "update", [record_uid], ident.employee_username)
        return result

    @app.delete("/v2/leave/records")
    def delete_leave_with_admin_push(
        body: leave_delete_type,
        background_tasks: BackgroundTasks,
        ident: identity_type = Depends(current_identity),
    ):
        uids = list(body.record_uids or [])
        result = original_delete(body=body, ident=ident)
        enqueue(background_tasks, "delete", uids, ident.employee_username)
        return result

    @app.get("/v2/admin-change-push/health")
    def admin_change_push_health():
        return {
            "ok": True,
            "release": RELEASE,
            "events": ["insert", "update", "delete"],
            "target_role": "admin",
            "lock_screen_detail": True,
            "dismissible": True,
        }

    app.state.admin_change_push_installed = True
    app.state.admin_change_push_release = RELEASE

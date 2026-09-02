"""Reliable employee Web Push outbox for PostgreSQL auto penalties."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

import vera_auto_check as auto_check


RELEASE = "auto-penalty-employee-push-2026-09-02-v1"
APP_URL = "https://veraspabienhoa.github.io/Vera-Spa/"


def _money(value: Any) -> str:
    try:
        amount = int(round(float(value or 0)))
    except Exception:
        amount = 0
    return f"{amount:,}".replace(",", ".") + "đ"


def _vault_secret(conn, name: str) -> str:
    value = conn.execute(text("""
        SELECT decrypted_secret FROM vault.decrypted_secrets
        WHERE name=:name LIMIT 1
    """), {"name": name}).scalar_one_or_none()
    return str(value or "").strip()


def _claim(engine, limit: int) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        auto_check.ensure_schema(conn)
        return [dict(row) for row in conn.execute(text("""
            WITH candidates AS (
              SELECT id FROM vera_auto_check_event
              WHERE status='added' AND employee_notified_at IS NULL
                AND (employee_notify_claimed_at IS NULL
                     OR employee_notify_claimed_at < NOW() - INTERVAL '5 minutes')
              ORDER BY created_at, id
              FOR UPDATE SKIP LOCKED
              LIMIT :limit
            )
            UPDATE vera_auto_check_event event
            SET employee_notify_claimed_at=NOW(), employee_notify_attempted_at=NOW(),
                employee_notify_error=NULL
            FROM candidates
            WHERE event.id=candidates.id
            RETURNING event.id,event.work_date,event.employee_name,event.reason,
                      event.source,event.minutes,event.detail,event.leave_record_uid
        """), {"limit": max(1, min(200, int(limit)))}).mappings()]


def _subscriptions(conn, employee: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text("""
        SELECT subscription_id::text AS subscription_id,endpoint,p256dh,auth_secret
        FROM vera_v2_push_subscription
        WHERE is_active=true
          AND lower(btrim(employee_username))=lower(btrim(:employee))
        ORDER BY updated_at DESC
    """), {"employee": employee}).mappings()]


def _penalty(conn, uid: str | None) -> float:
    if not uid:
        return 0.0
    return float(conn.execute(text("""
        SELECT penalty FROM leave_records WHERE record_uid=:uid LIMIT 1
    """), {"uid": uid}).scalar_one_or_none() or 0)


def _send(subscription: dict[str, Any], payload: dict[str, Any], private_key: str, subject: str):
    from pywebpush import WebPushException, webpush
    try:
        response = webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth_secret"]},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
            timeout=15,
        )
        return True, getattr(response, "status_code", None), ""
    except WebPushException as exc:
        return False, getattr(getattr(exc, "response", None), "status_code", None), str(exc)[:1000]
    except Exception as exc:
        return False, None, str(exc)[:1000]


def notify_pending(engine, limit: int = 100) -> dict[str, int]:
    """Send each recorded auto penalty once; failed/no-subscription items retry."""
    result = {"claimed": 0, "notified": 0, "pending": 0, "sent": 0, "failed": 0}
    try:
        events = _claim(engine, limit)
    except Exception:
        # Notification must never roll back or interrupt penalty recording.
        result["failed"] = 1
        return result
    result["claimed"] = len(events)
    for event in events:
        error = ""
        sent = 0
        try:
            with engine.connect() as conn:
                subscriptions = _subscriptions(conn, event["employee_name"])
                penalty = _penalty(conn, event.get("leave_record_uid"))
                private_key = _vault_secret(conn, "vera_v2_vapid_private_key")
                subject = _vault_secret(conn, "vera_v2_vapid_subject") or APP_URL
            if not subscriptions:
                error = "Nhân viên chưa bật thông báo Web Push."
            elif not private_key:
                error = "Thiếu khóa VAPID để gửi Web Push."
            else:
                minutes = int(round(float(event.get("minutes") or 0)))
                minute_text = f" ({minutes} phút)" if minutes > 0 else ""
                payload = {
                    "kind": "auto-penalty-recorded",
                    "title": "VERA SPA · Hệ thống đã ghi phạt",
                    "body": (
                        f"{event['employee_name']}: {event['reason']}{minute_text}. "
                        f"Mức phạt {_money(penalty)}."
                    ),
                    "url": APP_URL,
                    "tag": f"vera-auto-penalty-{event['id']}",
                    "employee": event["employee_name"],
                    "event_id": event["id"],
                }
                errors = []
                for subscription in subscriptions:
                    ok, status, send_error = _send(subscription, payload, private_key, subject)
                    sent += int(ok)
                    result["sent"] += int(ok)
                    result["failed"] += int(not ok)
                    if send_error:
                        errors.append(send_error)
                    with engine.begin() as conn:
                        conn.execute(text("""
                            UPDATE vera_v2_push_subscription SET
                              is_active=CASE WHEN :inactive THEN false ELSE is_active END,
                              last_success_at=CASE WHEN :ok THEN NOW() ELSE last_success_at END,
                              failure_count=CASE WHEN :ok THEN 0 ELSE failure_count+1 END,
                              last_error=CASE WHEN :ok THEN NULL ELSE :error END,updated_at=NOW()
                            WHERE subscription_id=CAST(:subscription_id AS uuid)
                        """), {"subscription_id": subscription["subscription_id"], "ok": ok,
                               "inactive": (not ok and status in {404, 410}), "error": send_error})
                error = " | ".join(errors)[:2000]
        except Exception as exc:
            error = str(exc)[:2000]
            result["failed"] += 1

        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE vera_auto_check_event SET
                  employee_notified_at=CASE WHEN :sent > 0 THEN NOW() ELSE employee_notified_at END,
                  employee_notify_claimed_at=NULL,
                  employee_notify_error=CASE WHEN :sent > 0 THEN NULL ELSE :error END
                WHERE id=:id
            """), {"id": event["id"], "sent": sent, "error": error or "Không gửi được thông báo."})
        if sent > 0:
            result["notified"] += 1
        else:
            result["pending"] += 1
    return result

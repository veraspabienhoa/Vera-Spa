"""Operational Web Push alerts for Live Tour projection queue health."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any

from sqlalchemy import text

import vera_postgres_job_queue as job_queue


RELEASE = "live-tour-queue-alerts-2026-09-16.1"
CATEGORY = "live_tour_queue_alert"
APP_URL = "https://app.veraspa.vn/"
MONITOR_SECONDS = 60
LAST_SUCCESS_MAX_SECONDS = 600
OLDEST_PENDING_MAX_SECONDS = 600
ALERT_COOLDOWN_SECONDS = 1800
FAILED_DELIVERY_RETRY_SECONDS = 300
ALERT_ROLES = ("admin", "quanly")


def evaluate(metrics: dict[str, Any]) -> list[str]:
    """Return active alert condition names for the current queue metrics."""
    conditions: list[str] = []
    last_success_age = metrics.get("last_success_age")
    oldest_pending = metrics.get("oldest_pending")
    if last_success_age is not None and float(last_success_age) > LAST_SUCCESS_MAX_SECONDS:
        conditions.append("last_success_age")
    if oldest_pending is not None and float(oldest_pending) > OLDEST_PENDING_MAX_SECONDS:
        conditions.append("oldest_pending")
    if int(metrics.get("failed") or 0) > 0:
        conditions.append("failed")
    if int(metrics.get("stale_processing") or 0) > 0:
        conditions.append("stale_processing")
    return conditions


def _state_key(queue_name: str) -> str:
    return f"queue:{queue_name}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _elapsed_seconds(value: Any, now: datetime) -> float:
    parsed = _parse_time(value)
    if parsed is None:
        return float("inf")
    return max(0.0, (now - parsed).total_seconds())


def _load_state(conn, queue_name: str) -> dict[str, Any]:
    value = conn.execute(text("""
        SELECT value_json FROM vera_app_setting
        WHERE category=:category AND setting_key=:key LIMIT 1
    """), {"category": CATEGORY, "key": _state_key(queue_name)}).scalar_one_or_none()
    return dict(value) if isinstance(value, dict) else {}


def _save_state(conn, queue_name: str, state: dict[str, Any]) -> None:
    conn.execute(text("""
        INSERT INTO vera_app_setting(
          category,setting_key,value_json,source,updated_by,revision,created_at,updated_at
        ) VALUES (
          :category,:key,CAST(:value AS jsonb),'live_tour_queue_alert','system',1,NOW(),NOW()
        )
        ON CONFLICT(category,setting_key) DO UPDATE SET
          value_json=EXCLUDED.value_json,
          source='live_tour_queue_alert',updated_by='system',
          revision=vera_app_setting.revision+1,updated_at=NOW()
    """), {
        "category": CATEGORY,
        "key": _state_key(queue_name),
        "value": json.dumps(state, ensure_ascii=False, separators=(",", ":")),
    })


def _try_lock(conn, queue_name: str) -> bool:
    value = conn.execute(text("""
        SELECT pg_try_advisory_xact_lock(hashtext(:key))
    """), {"key": f"vera:live-tour-queue-alert:{queue_name}"}).scalar_one()
    return bool(value)


def _claim_event(engine_instance, queue_name: str, conditions: list[str]) -> tuple[str | None, dict[str, Any]]:
    """Claim one alert/recovery delivery across all API replicas."""
    now = _now()
    signature = "|".join(sorted(conditions))
    with engine_instance().begin() as conn:
        if not _try_lock(conn, queue_name):
            return None, {}
        state = _load_state(conn, queue_name)
        before = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
        active_signature = str(state.get("active_signature") or "")
        event: str | None = None

        if conditions:
            state["pending_recovery_signature"] = ""
            state["active_conditions"] = list(conditions)
            if active_signature != signature:
                state["active_signature"] = signature
                state["active_since"] = _iso(now)
                event = "alert"
            elif (
                _elapsed_seconds(state.get("last_alert_at"), now) >= ALERT_COOLDOWN_SECONDS
                and _elapsed_seconds(state.get("last_attempt_at"), now) >= FAILED_DELIVERY_RETRY_SECONDS
            ):
                event = "alert"
        else:
            if active_signature:
                if state.get("last_alert_at"):
                    state["pending_recovery_signature"] = active_signature
                state["active_signature"] = ""
                state["active_conditions"] = []
                state["recovered_at"] = _iso(now)
            if (
                state.get("pending_recovery_signature")
                and _elapsed_seconds(state.get("last_attempt_at"), now) >= FAILED_DELIVERY_RETRY_SECONDS
            ):
                event = "recovery"

        if event:
            state["last_attempt_at"] = _iso(now)
            state["last_attempt_event"] = event
        after = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
        if before != after:
            _save_state(conn, queue_name, state)
        return event, state


def _admin_subscriptions(conn) -> list[dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT DISTINCT ON (s.subscription_id)
          s.subscription_id::text AS subscription_id,s.endpoint,s.p256dh,s.auth_secret
        FROM vera_v2_push_subscription s
        JOIN vera_v2_user_profile profile ON profile.auth_user_id=s.auth_user_id
        WHERE s.is_active=true AND profile.is_active=true
          AND lower(COALESCE(profile.role,'')) IN ('admin','quanly')
        ORDER BY s.subscription_id,s.updated_at DESC
    """)).mappings().all()
    return [dict(row) for row in rows]


def _vault_secret(conn, name: str) -> str:
    env_name = {
        "vera_v2_vapid_private_key": "VERA_V2_VAPID_PRIVATE_KEY",
        "vera_v2_vapid_subject": "VERA_V2_VAPID_SUBJECT",
    }.get(name)
    if env_name:
        value = str(os.getenv(env_name) or "").strip()
        if value:
            return value
    if conn.execute(text("SELECT to_regclass('vault.decrypted_secrets')")).scalar_one_or_none() is None:
        return ""
    value = conn.execute(text("""
        SELECT decrypted_secret FROM vault.decrypted_secrets
        WHERE name=:name LIMIT 1
    """), {"name": name}).scalar_one_or_none()
    return str(value or "").strip()


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


def _update_subscription(engine_instance, subscription_id: str, ok: bool, status: int | None, error: str) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text("""
            UPDATE vera_v2_push_subscription SET
              is_active=CASE WHEN :inactive THEN false ELSE is_active END,
              last_success_at=CASE WHEN :ok THEN NOW() ELSE last_success_at END,
              failure_count=CASE WHEN :ok THEN 0 ELSE failure_count+1 END,
              last_error=CASE WHEN :ok THEN NULL ELSE :error END,
              updated_at=NOW()
            WHERE subscription_id=CAST(:subscription_id AS uuid)
        """), {
            "subscription_id": subscription_id,
            "ok": ok,
            "inactive": (not ok and status in {404, 410}),
            "error": error,
        })


def _minutes(value: Any) -> str:
    try:
        return f"{float(value) / 60:.1f} phút"
    except (TypeError, ValueError):
        return "không xác định"


def _condition_text(condition: str, metrics: dict[str, Any]) -> str:
    if condition == "last_success_age":
        return f"chưa có projection thành công trong {_minutes(metrics.get('last_success_age'))}"
    if condition == "oldest_pending":
        return f"job pending lâu nhất {_minutes(metrics.get('oldest_pending'))}"
    if condition == "failed":
        return f"failed={int(metrics.get('failed') or 0)}"
    if condition == "stale_processing":
        return f"processing quá lease={int(metrics.get('stale_processing') or 0)}"
    return condition


def _payload(event: str, metrics: dict[str, Any], conditions: list[str]) -> dict[str, Any]:
    if event == "alert":
        title = "VERA SPA · Cảnh báo Live Tour Queue"
        body = "Live Tour projection queue bất thường: " + "; ".join(
            _condition_text(item, metrics) for item in conditions
        )
        kind = "live-tour-queue-alert"
    else:
        title = "VERA SPA · Live Tour Queue đã phục hồi"
        age = metrics.get("last_success_age")
        detail = f"Projection gần nhất cách {_minutes(age)}" if age is not None else "Queue đã trở lại trạng thái bình thường"
        body = f"{detail}; retry={int(metrics.get('retry') or 0)}; failed={int(metrics.get('failed') or 0)}."
        kind = "live-tour-queue-recovery"
    return {
        "kind": kind,
        "title": title,
        "body": body,
        "url": APP_URL,
        "tag": "vera-live-tour-queue-health",
        "queue": "live_tour_projection",
    }


def _deliver(engine_instance, event: str, metrics: dict[str, Any], conditions: list[str]) -> tuple[int, str]:
    with engine_instance().connect() as conn:
        subscriptions = _admin_subscriptions(conn)
        private_key = _vault_secret(conn, "vera_v2_vapid_private_key")
        subject = _vault_secret(conn, "vera_v2_vapid_subject") or APP_URL
    if not subscriptions:
        return 0, "Không có Web Push subscription đang hoạt động cho admin/quản lý."
    if not private_key:
        return 0, "Thiếu VAPID private key."

    payload = _payload(event, metrics, conditions)
    sent = 0
    errors: list[str] = []
    for subscription in subscriptions:
        ok, status, error = _send(subscription, payload, private_key, subject)
        sent += int(ok)
        if error:
            errors.append(error)
        _update_subscription(
            engine_instance,
            str(subscription["subscription_id"]),
            ok,
            status,
            error,
        )
    if sent > 0:
        return sent, " | ".join(errors)[:2000]
    return 0, (" | ".join(errors) or "Không gửi được Web Push.")[:2000]


def _record_delivery(engine_instance, queue_name: str, event: str, sent: int, error: str) -> None:
    now = _now()
    with engine_instance().begin() as conn:
        if not _try_lock(conn, queue_name):
            return
        state = _load_state(conn, queue_name)
        state["last_sent_count"] = int(sent)
        if sent > 0:
            state["last_error"] = ""
            if event == "alert":
                state["last_alert_at"] = _iso(now)
            else:
                state["last_recovery_at"] = _iso(now)
                state["pending_recovery_signature"] = ""
        else:
            state["last_error"] = str(error or "Không gửi được cảnh báo.")[:2000]
        _save_state(conn, queue_name, state)


def monitor_once(
    engine_instance,
    queue_name: str,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate and, if due, send one alert/recovery notification."""
    metrics = dict(metrics or job_queue.health_metrics(engine_instance, queue_name))
    conditions = evaluate(metrics)
    event, _ = _claim_event(engine_instance, queue_name, conditions)
    if not event:
        return {"event": "none", "conditions": conditions, "sent": 0}
    sent, error = _deliver(engine_instance, event, metrics, conditions)
    _record_delivery(engine_instance, queue_name, event, sent, error)
    log = logging.getLogger(__name__)
    if event == "alert":
        log.warning("Live Tour queue alert: conditions=%s sent=%s error=%s", conditions, sent, error)
    else:
        log.info("Live Tour queue recovery: sent=%s error=%s", sent, error)
    return {"event": event, "conditions": conditions, "sent": sent, "error": error}


def _channel_status(engine_instance) -> dict[str, Any]:
    try:
        with engine_instance().connect() as conn:
            subscriptions = _admin_subscriptions(conn)
            private_key = _vault_secret(conn, "vera_v2_vapid_private_key")
        return {
            "type": "web_push",
            "audience": "admin+quanly",
            "subscriptions": len(subscriptions),
            "vapid_configured": bool(private_key),
            "ready": bool(subscriptions and private_key),
        }
    except Exception as exc:
        return {
            "type": "web_push",
            "audience": "admin+quanly",
            "subscriptions": None,
            "vapid_configured": None,
            "ready": False,
            "error": str(exc)[:500],
        }


def health_status(engine_instance, queue_name: str, metrics: dict[str, Any]) -> dict[str, Any]:
    """Expose thresholds and alert delivery state without mutating it."""
    try:
        with engine_instance().connect() as conn:
            state = _load_state(conn, queue_name)
    except Exception as exc:
        state = {"last_error": f"Không đọc được alert state: {exc}"[:500]}
    conditions = evaluate(metrics)
    return {
        "release": RELEASE,
        "monitor_seconds": MONITOR_SECONDS,
        "cooldown_seconds": ALERT_COOLDOWN_SECONDS,
        "failed_delivery_retry_seconds": FAILED_DELIVERY_RETRY_SECONDS,
        "thresholds": {
            "last_success_age": LAST_SUCCESS_MAX_SECONDS,
            "oldest_pending": OLDEST_PENDING_MAX_SECONDS,
            "failed": 0,
            "stale_processing": 0,
        },
        "active": bool(conditions),
        "conditions": conditions,
        "active_since": state.get("active_since"),
        "last_alert_at": state.get("last_alert_at"),
        "last_recovery_at": state.get("last_recovery_at"),
        "last_attempt_at": state.get("last_attempt_at"),
        "last_sent_count": int(state.get("last_sent_count") or 0),
        "last_error": str(state.get("last_error") or ""),
        "channel": _channel_status(engine_instance),
    }

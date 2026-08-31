"""Enhanced purchase reconciliation status, details, and push alerts.

Rules:
- KHỚP: absolute difference < 0.5 VND (effectively zero).
- GẦN KHỚP: difference is non-zero and absolute difference <= 5,000 VND.
- KHÔNG KHỚP: absolute difference > 5,000 VND.

When a new or changed KHÔNG KHỚP state is detected, send a detailed Web Push
notification to active admin, quanly, and letan subscriptions. Alert state is
persisted per business date so ordinary page refreshes do not spam users.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import hashlib
from typing import Any, Callable

from fastapi import BackgroundTasks, Depends, Query
from sqlalchemy import text

import vera_web_v2_purchase_reconcile as base


RELEASE = "purchase-reconcile-2026-08-31-v2"
NEAR_MATCH_LIMIT = 5_000.0
ALERT_TABLE = "vera_v2_purchase_reconcile_alert"
APP_URL = "https://veraspabienhoa.github.io/Vera-Spa/"
TARGET_ROLES = ("admin", "quanly", "letan")


def _status_for_difference(difference: float) -> str:
    absolute = abs(float(difference or 0))
    if absolute < 0.5:
        return "KHỚP"
    if absolute <= NEAR_MATCH_LIMIT:
        return "GẦN KHỚP"
    return "KHÔNG KHỚP"


def _money_label(value: Any) -> str:
    try:
        amount = int(round(float(value or 0)))
    except Exception:
        amount = 0
    return f"{amount:,}".replace(",", ".") + "đ"


def _compact_detail(items: list[dict[str, Any]], *, label_key: str, limit: int = 5) -> str:
    if not items:
        return "Không có dòng tương ứng"
    parts: list[str] = []
    for item in items[:limit]:
        label = str(item.get(label_key) or "—").strip() or "—"
        parts.append(f"{label}: {_money_label(item.get('amount'))}")
    remaining = len(items) - limit
    if remaining > 0:
        parts.append(f"+{remaining} dòng khác")
    return " · ".join(parts)


def _enhanced_comparison(
    purchase_rows: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    purchase_by_date: dict[date, float] = defaultdict(float)
    ledger_by_date: dict[date, float] = defaultdict(float)
    purchase_details: dict[date, list[dict[str, Any]]] = defaultdict(list)
    ledger_details: dict[date, list[dict[str, Any]]] = defaultdict(list)

    for row in purchase_rows:
        target = row["date"]
        amount = float(row.get("amount") or 0)
        purchase_by_date[target] += amount
        purchase_details[target].append({
            "item": str(row.get("item") or "").strip(),
            "amount": amount,
            "buyer": str(row.get("buyer") or "").strip(),
        })

    for row in ledger_rows:
        if not row.get("is_purchase"):
            continue
        target = row["date"]
        amount = float(row.get("amount") or 0)
        ledger_by_date[target] += amount
        ledger_details[target].append({
            "note": str(row.get("note") or "").strip(),
            "amount": amount,
        })

    output: list[dict[str, Any]] = []
    for target in sorted(set(purchase_by_date) | set(ledger_by_date), reverse=True):
        purchase_total = round(purchase_by_date.get(target, 0.0), 2)
        ledger_total = round(ledger_by_date.get(target, 0.0), 2)
        difference = round(purchase_total - ledger_total, 2)
        status = _status_for_difference(difference)
        purchases = purchase_details.get(target, [])
        ledgers = ledger_details.get(target, [])
        output.append({
            "date": target.isoformat(),
            "date_label": base._fmt_date(target),
            "purchase_total": purchase_total,
            "ledger_purchase_total": ledger_total,
            "difference": difference,
            # Compatibility: only >5,000 is a blocking mismatch now.
            "matched": status != "KHÔNG KHỚP",
            "exact_match": status == "KHỚP",
            "status": status,
            "purchase_details": purchases,
            "ledger_details": ledgers,
            "purchase_detail_text": _compact_detail(purchases, label_key="item"),
            "ledger_detail_text": _compact_detail(ledgers, label_key="note"),
        })
    return output


def _remove_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def _ensure_alert_table(conn) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {ALERT_TABLE} (
            business_date date PRIMARY KEY,
            purchase_total numeric(18,2) NOT NULL DEFAULT 0,
            ledger_total numeric(18,2) NOT NULL DEFAULT 0,
            difference numeric(18,2) NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT '',
            signature text NOT NULL DEFAULT '',
            last_notified_at timestamptz NULL,
            updated_at timestamptz NOT NULL DEFAULT NOW()
        )
    """))


def _signature(row: dict[str, Any]) -> str:
    material = "|".join([
        str(row.get("date") or ""),
        f"{float(row.get('purchase_total') or 0):.2f}",
        f"{float(row.get('ledger_purchase_total') or 0):.2f}",
        f"{float(row.get('difference') or 0):.2f}",
        str(row.get("status") or ""),
        str(row.get("purchase_detail_text") or ""),
        str(row.get("ledger_detail_text") or ""),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _notification_body(row: dict[str, Any]) -> str:
    lines = [
        f"{row.get('date_label') or row.get('date')} · KHÔNG KHỚP",
        (
            f"BaoCaoMuaHang: {_money_label(row.get('purchase_total'))} · "
            f"Thu Chi: {_money_label(row.get('ledger_purchase_total'))} · "
            f"Chênh lệch: {_money_label(row.get('difference'))}"
        ),
        f"Mua hàng: {row.get('purchase_detail_text') or '—'}",
        f"Thu Chi: {row.get('ledger_detail_text') or '—'}",
    ]
    return "\n".join(lines)[:900]


def _dispatch_mismatch_alerts(
    *,
    engine_instance: Callable[[], Any],
    api_module,
    comparison_rows: list[dict[str, Any]],
) -> None:
    """Best-effort deduplicated push. Notification errors never break reports."""
    try:
        if not comparison_rows:
            return

        pending: list[dict[str, Any]] = []
        subscriptions: list[dict[str, Any]] = []
        private_key = ""
        subject = APP_URL

        with engine_instance().begin() as conn:
            _ensure_alert_table(conn)
            for row in comparison_rows:
                business_date = str(row.get("date") or "").strip()
                if not business_date:
                    continue
                signature = _signature(row)
                previous = conn.execute(text(f"""
                    SELECT status, signature, last_notified_at
                    FROM {ALERT_TABLE}
                    WHERE business_date=CAST(:business_date AS date)
                """), {"business_date": business_date}).mappings().first()

                should_notify = (
                    row.get("status") == "KHÔNG KHỚP"
                    and (
                        not previous
                        or str(previous.get("status") or "") != "KHÔNG KHỚP"
                        or str(previous.get("signature") or "") != signature
                        or previous.get("last_notified_at") is None
                    )
                )

                conn.execute(text(f"""
                    INSERT INTO {ALERT_TABLE} (
                        business_date, purchase_total, ledger_total, difference,
                        status, signature, updated_at
                    ) VALUES (
                        CAST(:business_date AS date), :purchase_total, :ledger_total,
                        :difference, :status, :signature, NOW()
                    )
                    ON CONFLICT (business_date) DO UPDATE SET
                        purchase_total=EXCLUDED.purchase_total,
                        ledger_total=EXCLUDED.ledger_total,
                        difference=EXCLUDED.difference,
                        status=EXCLUDED.status,
                        signature=EXCLUDED.signature,
                        updated_at=NOW()
                """), {
                    "business_date": business_date,
                    "purchase_total": float(row.get("purchase_total") or 0),
                    "ledger_total": float(row.get("ledger_purchase_total") or 0),
                    "difference": float(row.get("difference") or 0),
                    "status": str(row.get("status") or ""),
                    "signature": signature,
                })
                if should_notify:
                    pending.append({**row, "signature": signature})

            if pending:
                private_key = api_module._vault_secret(conn, "vera_v2_vapid_private_key")
                subject = api_module._vault_secret(conn, "vera_v2_vapid_subject") or APP_URL
                subscriptions = [dict(row) for row in conn.execute(text("""
                    SELECT s.subscription_id::text AS subscription_id,
                           s.endpoint, s.p256dh, s.auth_secret,
                           lower(COALESCE(p.role,'')) AS role
                    FROM vera_v2_push_subscription s
                    JOIN vera_v2_user_profile p ON p.auth_user_id=s.auth_user_id
                    WHERE s.is_active=true
                      AND p.is_active=true
                      AND lower(COALESCE(p.role,'')) IN ('admin','quanly','letan')
                    ORDER BY s.updated_at DESC
                """)).mappings().all()]

        if not pending or not private_key or not subscriptions:
            return

        delivery_results: list[dict[str, Any]] = []
        successful_dates: set[str] = set()
        timestamp = int(datetime.now().timestamp() * 1000)
        for row in pending:
            business_date = str(row.get("date") or "")
            payload = {
                "title": "VERA SPA · Đối chiếu mua hàng KHÔNG KHỚP",
                "body": _notification_body(row),
                "url": APP_URL,
                "tag": f"vera-purchase-mismatch-{business_date}-{row['signature'][:12]}",
                "kind": "purchase-reconcile-mismatch",
                "business_date": business_date,
                "difference": float(row.get("difference") or 0),
                "dismissible": True,
                "timestamp": timestamp,
            }
            row_success = False
            for subscription in subscriptions:
                delivery = {**subscription, "payload": payload}
                ok, status_code, error_text = api_module._send_web_push(
                    delivery, private_key, subject
                )
                inactive = (not ok) and status_code in {404, 410}
                delivery_results.append({
                    "subscription_id": subscription["subscription_id"],
                    "ok": bool(ok),
                    "inactive": bool(inactive),
                    "last_error": str(error_text or "")[:1000],
                })
                row_success = row_success or bool(ok)
            if row_success:
                successful_dates.add(business_date)

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
            for business_date in successful_dates:
                conn.execute(text(f"""
                    UPDATE {ALERT_TABLE}
                    SET last_notified_at=NOW(), updated_at=NOW()
                    WHERE business_date=CAST(:business_date AS date)
                """), {"business_date": business_date})
    except Exception:
        return


def install_purchase_reconcile_v2(
    app,
    *,
    engine_instance: Callable[[], Any],
    api_module,
    current_identity,
    identity_type,
) -> None:
    if getattr(app.state, "purchase_reconcile_v2_installed", False):
        return

    globals()["identity_type"] = identity_type
    base._comparison = _enhanced_comparison
    original = _remove_route(app, "/v2/revenue/purchase-reconcile", "GET")
    if not callable(original):
        raise RuntimeError("Không tìm thấy route đối chiếu mua hàng để cài V2.")

    @app.get("/v2/revenue/purchase-reconcile")
    def purchase_reconcile_v2(
        background_tasks: BackgroundTasks,
        preset: str = Query(default="this_month", max_length=30),
        start_date: date | None = Query(default=None, alias="start"),
        end_date: date | None = Query(default=None, alias="end"),
        ident: identity_type = Depends(current_identity),
    ):
        result = original(
            preset=preset,
            start_date=start_date,
            end_date=end_date,
            ident=ident,
        )
        rows = list((result or {}).get("comparison_rows") or [])
        exact_count = sum(1 for row in rows if row.get("status") == "KHỚP")
        near_count = sum(1 for row in rows if row.get("status") == "GẦN KHỚP")
        mismatch_count = sum(1 for row in rows if row.get("status") == "KHÔNG KHỚP")
        overall_status = (
            "KHÔNG KHỚP" if mismatch_count
            else "GẦN KHỚP" if near_count
            else "KHỚP"
        )
        result.update({
            "release": RELEASE,
            "near_match_limit": NEAR_MATCH_LIMIT,
            "exact_match_count": exact_count,
            "near_match_count": near_count,
            "mismatch_count": mismatch_count,
            "all_match": bool(rows) and exact_count == len(rows),
            "all_acceptable": mismatch_count == 0,
            "overall_status": overall_status,
            "alert_roles": list(TARGET_ROLES),
        })
        background_tasks.add_task(
            _dispatch_mismatch_alerts,
            engine_instance=engine_instance,
            api_module=api_module,
            comparison_rows=rows,
        )
        return result

    @app.get("/v2/revenue/purchase-reconcile-v2/health")
    def purchase_reconcile_v2_health():
        return {
            "ok": True,
            "release": RELEASE,
            "near_match_limit": NEAR_MATCH_LIMIT,
            "statuses": ["KHỚP", "GẦN KHỚP", "KHÔNG KHỚP"],
            "alert_roles": list(TARGET_ROLES),
            "alert_detail": True,
            "deduplicated": True,
        }

    app.state.purchase_reconcile_v2_installed = True
    app.state.purchase_reconcile_v2_release = RELEASE

"""Authenticated automatic checker for purchase reconciliation mismatch alerts.

A lightweight Web V2 watcher calls this endpoint periodically. Only admin,
quanly, and letan sessions cause source data to be read. The checker scans the
current month and reuses the V2 deduplicated push dispatcher, so repeated checks
never spam unchanged mismatch alerts.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import BackgroundTasks, Depends

import vera_web_v2_purchase_reconcile as base
import vera_web_v2_purchase_reconcile_v2 as v2


RELEASE = "purchase-reconcile-alert-check-2026-08-31-v1"


def install_purchase_reconcile_alert_check(
    app,
    *,
    engine_instance,
    api_module,
    current_identity,
    identity_type,
    norm,
    google_client,
) -> None:
    if getattr(app.state, "purchase_reconcile_alert_check_installed", False):
        return

    globals()["identity_type"] = identity_type

    @app.get("/v2/revenue/purchase-reconcile/alert-check")
    def purchase_reconcile_alert_check(
        background_tasks: BackgroundTasks,
        ident: identity_type = Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role not in v2.TARGET_ROLES:
            return {"ok": True, "skipped": True, "reason": "role_not_target"}

        today = datetime.now(base.VN_TZ).date()
        start = today.replace(day=1)
        end = today

        purchase_content = base._drive_download_purchase_report()
        purchase_all = base._parse_purchase_report(purchase_content, norm)
        revenue_values = (
            google_client()
            .open_by_key(base.REVENUE_SPREADSHEET_ID)
            .worksheet(base.REVENUE_WORKSHEET)
            .get_all_values()
        )
        ledger_all = base._parse_revenue_input(revenue_values, norm)
        purchase_rows = base._filtered(purchase_all, start, end)
        ledger_rows = base._filtered(ledger_all, start, end)
        comparison_rows = base._comparison(purchase_rows, ledger_rows)

        background_tasks.add_task(
            v2._dispatch_mismatch_alerts,
            engine_instance=engine_instance,
            api_module=api_module,
            comparison_rows=comparison_rows,
        )
        return {
            "ok": True,
            "release": RELEASE,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "mismatch_count": sum(1 for row in comparison_rows if row.get("status") == "KHÔNG KHỚP"),
            "near_match_count": sum(1 for row in comparison_rows if row.get("status") == "GẦN KHỚP"),
        }

    @app.get("/v2/revenue/purchase-reconcile/alert-check/health")
    def purchase_reconcile_alert_check_health():
        return {
            "ok": True,
            "release": RELEASE,
            "target_roles": list(v2.TARGET_ROLES),
            "range": "current_month",
            "deduplicated": True,
        }

    app.state.purchase_reconcile_alert_check_installed = True
    app.state.purchase_reconcile_alert_check_release = RELEASE

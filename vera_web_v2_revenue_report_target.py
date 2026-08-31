"""Point the Doanh thu report link at the last populated Input row."""
from __future__ import annotations

import os
from typing import Any, Callable

from fastapi import Depends


RELEASE = "revenue-report-input-last-row-2026-08-31-v1"
INPUT_SHEET_GID = os.getenv("VERA_REVENUE_INPUT_GID", "2058724516").strip() or "2058724516"


def _find_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            app.router.routes.remove(route)
            return route.endpoint
    raise RuntimeError(f"Cannot find {wanted} {path} to enhance")


def _input_last_row_url(base_url: str, transaction_count: Any) -> str:
    """Input is a transaction log: one header row + one Thu/Chi row per transaction."""
    try:
        count = max(0, int(transaction_count or 0))
    except (TypeError, ValueError):
        count = 0
    last_row = max(1, count + 1)
    clean = str(base_url or "").split("#", 1)[0]
    separator = "&" if "?" in clean else "?"
    # gid selects Input; range selects/focuses the final data row so Sheets opens there.
    return f"{clean}{separator}gid={INPUT_SHEET_GID}#gid={INPUT_SHEET_GID}&range=A{last_row}"


def install_revenue_report_target(
    app,
    *,
    current_identity,
) -> None:
    if getattr(app.state, "revenue_report_target_installed", False):
        return

    original_summary = _find_route(app, "/v2/revenue/summary", "GET")

    @app.get("/v2/revenue/summary")
    def revenue_summary_with_input_target(ident=Depends(current_identity)):
        payload = original_summary(ident=ident)
        result = dict(payload) if isinstance(payload, dict) else {"data": payload}
        result["report_url"] = _input_last_row_url(
            str(result.get("report_url") or ""),
            result.get("transaction_count"),
        )
        result["report_sheet"] = "Input"
        result["report_last_row"] = max(1, int(result.get("transaction_count") or 0) + 1)
        result["report_target_release"] = RELEASE
        return result

    app.state.revenue_report_target_installed = True
    app.state.revenue_report_target_release = RELEASE

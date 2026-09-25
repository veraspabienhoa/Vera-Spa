"""Calculate KTV payroll directly from canonical Live Tour employee TIP rows."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import Depends, HTTPException, Query
from sqlalchemy import text

import vera_web_v2_payroll as payroll
import vera_live_tour_resource_store as resource_store
from vera_web_v2_payroll_timesoft_auto import _workbook


RELEASE = "payroll-live-tour-tip-2026-09-20"


def _find_route(app, path: str, method: str):
    for route in app.router.routes:
        if getattr(route, "path", "") == path and method in (getattr(route, "methods", set()) or set()):
            return route
    return None


def _row_date(row: dict[str, Any]) -> date | None:
    raw = str(row.get("business_date") or row.get("effective_at") or row.get("created_at") or "").strip()
    try:
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return None


def _live_tour_tip_rows(conn, start: date, end: date) -> list[dict[str, Any]]:
    if resource_store.enabled():
        payload, _, _ = resource_store.read(conn, collections={"reports"})
    else:
        payload = conn.execute(text("""
            SELECT jsonb_build_object('reports',value_json->'reports') FROM vera_app_setting
            WHERE category='live_tour' AND setting_key='state'
            LIMIT 1
        """)).scalar_one_or_none()
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    state = payload if isinstance(payload, dict) else {}
    rows = []
    for report in state.get("reports") or []:
        if not isinstance(report, dict):
            continue
        business_date = _row_date(report)
        employee = str(report.get("employee_name") or "").strip()
        tip = payroll._number(report.get("tip"))
        if business_date is None or not start <= business_date <= end or not employee or tip <= 0:
            continue
        rows.append({
            "time": business_date.strftime("%d/%m/%Y"),
            "item": "TIP",
            "amount": tip,
            "employee": employee,
        })
    return rows


def install_payroll_live_tour_tip_routes(
    app,
    *,
    engine_instance,
    current_identity,
    require_feature,
    identity_type,
) -> None:
    if getattr(app.state, "payroll_live_tour_tip_installed", False):
        return
    calculate_route = _find_route(app, "/v2/payroll/calculate", "POST")
    if calculate_route is None:
        raise RuntimeError("Live Tour TIP payroll cannot find the canonical calculate route.")
    calculate = calculate_route.endpoint

    @app.get("/v2/payroll-live-tour-tip/health")
    def health():
        return {"ok": True, "release": RELEASE, "source": "live_tour.reports.tip"}

    @app.post("/v2/payroll/calculate-from-tips")
    async def calculate_from_tips(
        month: str = Query(...),
        period_no: int = Query(..., ge=1, le=2),
        ident: identity_type = Depends(current_identity),
    ):
        start, end, label = payroll._period(month, period_no)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            rows = _live_tour_tip_rows(conn, start, end)
        if not rows:
            raise HTTPException(409, f"Không có dữ liệu TIP nhân viên trong {label}.")
        result = await calculate(
            month=month,
            period_no=period_no,
            payload=_workbook(rows),
            ident=ident,
        )
        output = dict(result or {})
        summary = dict(output.get("source_summary") or {})
        summary.update({
            "source": "TIP nhân viên từ Live Tour",
            "tip_rows": len(rows),
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
        })
        output["source_summary"] = summary
        output["source_name"] = f"TIP Live Tour · {label}"
        output["tip_source_release"] = RELEASE
        return output

    app.state.payroll_live_tour_tip_installed = True
    app.state.payroll_live_tour_tip_release = RELEASE

"""Revenue summary and leave-list read enhancements for VERA SPA Web V2."""
from __future__ import annotations

from datetime import date
import os
import re
from typing import Any, Callable

from fastapi import Depends, HTTPException, Query
from sqlalchemy import text

import vera_web_v2_permissions as permissions


RELEASE = "revenue-leave-list-2026-08-29"
REVENUE_FEATURE = "revenue_view"
REVENUE_SPREADSHEET_ID = os.getenv(
    "VERA_REVENUE_SHEET_ID",
    "1KLYz2iQSfNU0xOfrl8V9iz9-dQKMkwyUicuuiGsqC4U",
)
REVENUE_WORKSHEET = os.getenv("VERA_REVENUE_SHEET_NAME", "Input")


def _find_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            app.router.routes.remove(route)
            return route.endpoint
    raise RuntimeError(f"Cannot find {wanted} {path} to enhance")


def _money(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    cleaned = re.sub(r"[^0-9,.\-]", "", raw)
    if not cleaned:
        return 0.0
    if "," in cleaned and "." in cleaned:
        decimal = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        cleaned = cleaned.replace(thousands, "").replace(decimal, ".")
    elif cleaned.count(",") == 1 and len(cleaned.rsplit(",", 1)[1]) <= 2:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") == 1 and len(cleaned.rsplit(".", 1)[1]) <= 2:
        pass
    else:
        cleaned = cleaned.replace(",", "").replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _revenue_summary(values: list[list[Any]], norm: Callable[[Any], str]) -> dict[str, Any]:
    if not values:
        raise HTTPException(503, "Sheet Input chưa có dữ liệu.")
    headers = [norm(value) for value in values[0]]
    try:
        type_index = headers.index(norm("Loại giao dịch"))
        amount_index = headers.index(norm("Số tiền"))
    except ValueError as exc:
        raise HTTPException(503, "Sheet Input phải có cột 'Loại giao dịch' và 'Số tiền'.") from exc

    income = expense = 0.0
    transaction_count = 0
    for row in values[1:]:
        tx_type = norm(row[type_index] if type_index < len(row) else "")
        if tx_type not in {"thu", "chi"}:
            continue
        amount = _money(row[amount_index] if amount_index < len(row) else 0)
        if tx_type == "thu":
            income += amount
        else:
            expense += amount
        transaction_count += 1
    return {
        "total_income": round(income, 2),
        "total_expense": round(expense, 2),
        "balance": round(income - expense, 2),
        "transaction_count": transaction_count,
    }


def _progressive_detail_map(conn, start_date: date, end_date: date, progressive_key) -> dict[str, str]:
    rows = conn.execute(text("""
        SELECT record_uid, leave_date, leave_reason, COALESCE(detail,'') AS detail,
               source_row, id
        FROM leave_records
        WHERE leave_date BETWEEN :start_date AND :end_date
        ORDER BY leave_date, COALESCE(source_row, 2147483647), id
    """), {"start_date": start_date, "end_date": end_date}).mappings().all()
    counters: dict[tuple[date, str], int] = {}
    output: dict[str, str] = {}
    for row in rows:
        key = str(progressive_key(row.get("leave_reason")) or "")
        if not key:
            continue
        bucket = (row["leave_date"], key)
        counters[bucket] = counters.get(bucket, 0) + 1
        ordinal = counters[bucket]
        detail = str(row.get("detail") or "").strip()
        if re.match(r"^\s*Người\s+Thứ\s+\d+", detail, flags=re.IGNORECASE):
            output[str(row["record_uid"])] = detail
        else:
            prefix = f"Người Thứ {ordinal}"
            output[str(row["record_uid"])] = f"{prefix} | {detail}" if detail else prefix
    return output


def install_revenue_leave_list_routes(
    app, *, engine_instance, current_identity, require_feature, feature_allowed,
    norm, progressive_key, google_client,
) -> None:
    if getattr(app.state, "revenue_leave_list_installed", False):
        return

    permissions.FEATURE_GROUPS.setdefault("Doanh thu", {})[REVENUE_FEATURE] = "Xem Doanh thu"
    permissions.FEATURES[REVENUE_FEATURE] = "Xem Doanh thu"
    permissions.DEFAULT_ROLE_FEATURES.setdefault("admin", set()).add(REVENUE_FEATURE)

    original_records = _find_route(app, "/v2/leave/records", "GET")
    original_daily_stats = _find_route(app, "/v2/leave/daily-stats", "GET")

    @app.get("/v2/revenue/health")
    def revenue_health():
        return {"ok": True, "release": RELEASE, "worksheet": REVENUE_WORKSHEET}

    @app.get("/v2/leave/list-enhancements/health")
    def leave_list_enhancements_health():
        return {"ok": True, "release": RELEASE, "progressive_detail": True, "manager_stats_scope": ["admin", "quanly", "letan"]}

    @app.get("/v2/revenue/summary")
    def revenue_summary(ident=Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
        try:
            worksheet = google_client().open_by_key(REVENUE_SPREADSHEET_ID).worksheet(REVENUE_WORKSHEET)
            values = worksheet.get_all_values()
        except Exception as exc:
            raise HTTPException(503, f"Không đọc được Quản lý Thu Chi · sheet {REVENUE_WORKSHEET}: {type(exc).__name__}.") from exc
        return {"ok": True, "release": RELEASE, "source": "Quản lý Thu Chi", "worksheet": REVENUE_WORKSHEET, **_revenue_summary(values, norm)}

    @app.get("/v2/leave/records")
    def leave_records_enhanced(
        date_value: date | None = Query(default=None, alias="date"),
        start_date: date | None = Query(default=None, alias="start"),
        end_date: date | None = Query(default=None, alias="end"),
        ident=Depends(current_identity),
    ):
        payload = original_records(date_value=date_value, start_date=start_date, end_date=end_date, ident=ident)
        records = list(payload.get("records") or [])
        if not records:
            return payload
        effective_start = date_value or start_date
        effective_end = date_value or end_date
        if not effective_start or not effective_end:
            return payload
        with engine_instance().connect() as conn:
            detail_map = _progressive_detail_map(conn, effective_start, effective_end, progressive_key)
        for item in records:
            enriched = detail_map.get(str(item.get("record_uid") or ""))
            if enriched:
                item["detail"] = enriched
        return {**payload, "records": records}

    @app.get("/v2/leave/daily-stats")
    def leave_daily_stats_scoped(
        start_date: date = Query(alias="start"),
        end_date: date = Query(alias="end"),
        employee: str = Query(default="", max_length=200),
        ident=Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        requested_employee = str(employee or "").strip()
        if role not in {"admin", "quanly", "letan"}:
            requested_employee = str(getattr(ident, "employee_username", "") or "").strip()
        return original_daily_stats(start_date=start_date, end_date=end_date, employee=requested_employee, ident=ident)

    app.state.revenue_leave_list_installed = True
    app.state.revenue_leave_list_release = RELEASE

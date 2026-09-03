"""Revenue summary and leave-list read enhancements for VERA SPA Web V2."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
import json
import os
import re
from typing import Any, Callable

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
import requests
from sqlalchemy import text

import vera_web_v2_permissions as permissions


RELEASE = "revenue-leave-list-2026-09-01.1-all-stats-visible"
REVENUE_FEATURE = "revenue_view"
REVENUE_TIP_FEATURE = "revenue_tip_edit"
REVENUE_TIP_SETTING = "current_period_tip"
REVENUE_SPREADSHEET_ID = os.getenv(
    "VERA_REVENUE_SHEET_ID",
    "1KLYz2iQSfNU0xOfrl8V9iz9-dQKMkwyUicuuiGsqC4U",
)
REVENUE_WORKSHEET = os.getenv("VERA_REVENUE_SHEET_NAME", "Input")
REVENUE_REPORT_URL = os.getenv(
    "VERA_REVENUE_REPORT_URL",
    "https://docs.google.com/spreadsheets/d/1KLYz2iQSfNU0xOfrl8V9iz9-dQKMkwyUicuuiGsqC4U/edit?usp=drivesdk",
)
REVENUE_ENTRY_FORM_URL = os.getenv(
    "VERA_REVENUE_ENTRY_FORM_URL",
    "https://docs.google.com/forms/d/e/1FAIpQLSeJp1bLrl8zSyESu_K0eo6NxdKsm85p4fxGXPXigPlmgkAs7w/viewform",
)
VN_TZ = timezone(timedelta(hours=7))
REVENUE_CURRENT_DATE_COLUMN_INDEX = 4  # Sheet Input, column E.
DATE_IN_TEXT_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*([./-])\s*(\d{1,2})\s*\2\s*(\d{4})(?!\d)"
)


class RevenueTipUpdate(BaseModel):
    amount: float = Field(ge=0, le=10_000_000_000_000)


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


def _dates_in_text(value: Any) -> list[date]:
    raw = str(value or "").strip()
    if not raw:
        return []
    parsed_dates: list[date] = []
    for match in DATE_IN_TEXT_RE.finditer(raw):
        try:
            parsed_dates.append(date(int(match.group(4)), int(match.group(3)), int(match.group(1))))
        except (TypeError, ValueError):
            pass
    return parsed_dates


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw.split(" ", 1)[0], "%Y-%m-%d").date()
    except ValueError:
        parsed_dates = _dates_in_text(raw)
        return parsed_dates[0] if parsed_dates else None


def _revenue_summary(values: list[list[Any]], norm: Callable[[Any], str]) -> dict[str, Any]:
    if not values:
        raise HTTPException(503, "Sheet Input chưa có dữ liệu.")
    headers = [norm(value) for value in values[0]]
    try:
        type_index = headers.index(norm("Loại giao dịch"))
        amount_index = headers.index(norm("Số tiền"))
    except ValueError as exc:
        raise HTTPException(503, "Sheet Input phải có cột 'Loại giao dịch' và 'Số tiền'.") from exc

    try:
        date_index = headers.index(norm("Ngày giao dịch"))
    except ValueError:
        date_index = -1

    income = expense = 0.0
    transaction_count = 0
    transaction_dates: list[date] = []
    input_column_e_dates: list[date] = []
    for row in values[1:]:
        if REVENUE_CURRENT_DATE_COLUMN_INDEX < len(row):
            input_column_e_dates.extend(_dates_in_text(row[REVENUE_CURRENT_DATE_COLUMN_INDEX]))
        tx_type = norm(row[type_index] if type_index < len(row) else "")
        if tx_type not in {"thu", "chi"}:
            continue
        amount = _money(row[amount_index] if amount_index < len(row) else 0)
        if tx_type == "thu":
            income += amount
        else:
            expense += amount
        transaction_count += 1
        if date_index >= 0:
            parsed = _parse_date(row[date_index] if date_index < len(row) else "")
            if parsed:
                transaction_dates.append(parsed)

    start_date = min(transaction_dates) if transaction_dates else None
    if input_column_e_dates:
        current_date = max(input_column_e_dates)
        current_date_source = "input_column_e"
    elif transaction_dates:
        current_date = max(transaction_dates)
        current_date_source = "transaction_date_fallback"
    else:
        current_date = datetime.now(VN_TZ).date()
        current_date_source = "server_date_fallback"
    return {
        "total_income": round(income, 2),
        "total_expense": round(expense, 2),
        "transaction_count": transaction_count,
        "start_date": start_date.isoformat() if start_date else "",
        "current_date": current_date.isoformat(),
        "start_date_label": start_date.strftime("%d/%m/%Y") if start_date else "—",
        "current_date_label": current_date.strftime("%d/%m/%Y"),
        "current_date_source": current_date_source,
    }


def _period_tip(conn, start_date_text: str) -> float:
    payload = conn.execute(text("""
        SELECT value_json
        FROM vera_app_setting
        WHERE category='revenue' AND setting_key=:key
        LIMIT 1
    """), {"key": REVENUE_TIP_SETTING}).scalar_one_or_none()
    if not isinstance(payload, dict):
        return 0.0
    if str(payload.get("period_start") or "") != str(start_date_text or ""):
        return 0.0
    return max(0.0, _money(payload.get("amount", 0)))


def _save_period_tip(conn, start_date_text: str, amount: float, actor: str) -> None:
    payload = {
        "period_start": str(start_date_text or ""),
        "amount": round(max(0.0, float(amount)), 2),
    }
    conn.execute(text("""
        INSERT INTO vera_app_setting(
            category, setting_key, value_json, source, updated_by,
            revision, created_at, updated_at
        ) VALUES (
            'revenue', :key, CAST(:payload AS jsonb), 'web_v2', :actor,
            1, NOW(), NOW()
        )
        ON CONFLICT(category, setting_key) DO UPDATE SET
            value_json=EXCLUDED.value_json,
            source='web_v2',
            updated_by=EXCLUDED.updated_by,
            revision=vera_app_setting.revision+1,
            updated_at=NOW()
    """), {
        "key": REVENUE_TIP_SETTING,
        "payload": json.dumps(payload, ensure_ascii=False),
        "actor": str(actor or ""),
    })


def _read_public_revenue_values() -> list[list[str]]:
    response = requests.get(
        f"https://docs.google.com/spreadsheets/d/{REVENUE_SPREADSHEET_ID}/gviz/tq",
        params={"tqx": "out:csv", "sheet": REVENUE_WORKSHEET},
        timeout=30,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    values = list(csv.reader(response.text.splitlines()))
    if not values:
        raise RuntimeError("Public Google Sheets response is empty")
    return values


def _read_revenue_values(google_client) -> list[list[Any]]:
    credential_error: Exception | None = None
    try:
        worksheet = google_client().open_by_key(REVENUE_SPREADSHEET_ID).worksheet(REVENUE_WORKSHEET)
        return worksheet.get_all_values()
    except Exception as exc:
        credential_error = exc

    # Quản lý Thu Chi is intentionally shared read-only. VPS deployments do
    # not have Google Application Default Credentials, so use the official
    # Google Visualization CSV endpoint as a credential-free read fallback.
    try:
        return _read_public_revenue_values()
    except Exception as public_exc:
        raise HTTPException(
            503,
            f"Không đọc được Quản lý Thu Chi · sheet {REVENUE_WORKSHEET}: "
            f"{type(credential_error).__name__} / {type(public_exc).__name__}.",
        ) from public_exc


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

    revenue_group = permissions.FEATURE_GROUPS.setdefault("Doanh thu", {})
    revenue_group[REVENUE_FEATURE] = "Xem Doanh thu"
    revenue_group[REVENUE_TIP_FEATURE] = "Nhập Tiền TIP trong kỳ"
    permissions.FEATURES[REVENUE_FEATURE] = "Xem Doanh thu"
    permissions.FEATURES[REVENUE_TIP_FEATURE] = "Nhập Tiền TIP trong kỳ"
    permissions.DEFAULT_ROLE_FEATURES.setdefault("admin", set()).update({REVENUE_FEATURE, REVENUE_TIP_FEATURE})

    original_records = _find_route(app, "/v2/leave/records", "GET")
    original_daily_stats = _find_route(app, "/v2/leave/daily-stats", "GET")

    @app.get("/v2/revenue/health")
    def revenue_health():
        return {
            "ok": True,
            "release": RELEASE,
            "worksheet": REVENUE_WORKSHEET,
            "period_metadata": True,
            "current_date_source": "Input!E:E latest parsed date",
            "period_tip": True,
            "balance_formula": "total_income-total_expense-period_tip",
            "entry_form": True,
            "report_link": True,
        }

    @app.get("/v2/leave/list-enhancements/health")
    def leave_list_enhancements_health():
        return {
            "ok": True,
            "release": RELEASE,
            "progressive_detail": True,
            "stats_scope": "all_registered_employees",
            "penalty_visibility": "permission_gated",
        }

    @app.get("/v2/revenue/summary")
    def revenue_summary(ident=Depends(current_identity)):
        values = _read_revenue_values(google_client)
        summary = _revenue_summary(values, norm)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            tip = _period_tip(conn, summary.get("start_date", ""))
            can_edit_tip = bool(feature_allowed(conn, ident, REVENUE_TIP_FEATURE))
        summary["period_tip"] = round(tip, 2)
        summary["balance"] = round(summary["total_income"] - summary["total_expense"] - tip, 2)
        return {
            "ok": True,
            "release": RELEASE,
            "source": "Quản lý Thu Chi",
            "worksheet": REVENUE_WORKSHEET,
            "entry_form_url": REVENUE_ENTRY_FORM_URL,
            "report_url": REVENUE_REPORT_URL,
            "can_edit_tip": can_edit_tip,
            **summary,
        }

    @app.put("/v2/revenue/tip")
    def save_revenue_tip(body: RevenueTipUpdate, ident=Depends(current_identity)):
        values = _read_revenue_values(google_client)
        summary = _revenue_summary(values, norm)
        period_start = str(summary.get("start_date") or "")
        if not period_start:
            raise HTTPException(409, "Chưa xác định được ngày bắt đầu kỳ Doanh thu để lưu Tiền TIP.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_TIP_FEATURE)
            _save_period_tip(conn, period_start, body.amount, getattr(ident, "employee_username", ""))
        tip = round(float(body.amount), 2)
        balance = round(summary["total_income"] - summary["total_expense"] - tip, 2)
        return {
            "ok": True,
            "release": RELEASE,
            "period_tip": tip,
            "balance": balance,
            "period_start": period_start,
            "message": f"Đã lưu Tiền TIP trong kỳ: {round(tip):,}đ.".replace(",", "."),
        }

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
        requested_employee = str(employee or "").strip()
        return original_daily_stats(start_date=start_date, end_date=end_date, employee=requested_employee, ident=ident)

    app.state.revenue_leave_list_installed = True
    app.state.revenue_leave_list_release = RELEASE

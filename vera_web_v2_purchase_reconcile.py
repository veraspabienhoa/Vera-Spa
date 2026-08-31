"""Purchase-report reconciliation for VERA SPA Web V2 Revenue page.

Compares the live BaoCaoMuaHang.xlsb Google Drive file against
Quản lý Thu Chi / Input, grouped by the actual business date.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import os
import re
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession
from fastapi import Depends, HTTPException, Query
from pyxlsb import open_workbook

from vera_web_v2_revenue_leave_list import (
    REVENUE_FEATURE,
    REVENUE_SPREADSHEET_ID,
    REVENUE_WORKSHEET,
    _dates_in_text,
    _money,
    _parse_date,
)


RELEASE = "purchase-reconcile-2026-08-31-v1"
VN_TZ = timezone(timedelta(hours=7))
PURCHASE_REPORT_FILE_ID = os.getenv(
    "VERA_PURCHASE_REPORT_FILE_ID",
    "1adbYotED7NuCfTwfqLMc9XXk24Z8ADWz",
).strip()
PURCHASE_REPORT_WORKSHEET = os.getenv("VERA_PURCHASE_REPORT_SHEET_NAME", "Input").strip() or "Input"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DATE_RANGE_PRESETS = {
    "today", "yesterday", "this_week", "last_week", "this_month", "last_month", "custom"
}


def _excel_serial_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
        except (OverflowError, ValueError):
            return None
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            pass
    return None


def _fmt_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _resolve_range(
    preset: str,
    start_date: date | None,
    end_date: date | None,
    today: date | None = None,
) -> tuple[date, date]:
    key = str(preset or "this_month").strip().lower()
    if key not in DATE_RANGE_PRESETS:
        raise HTTPException(400, "Bộ lọc thời gian không hợp lệ.")
    now_date = today or datetime.now(VN_TZ).date()

    if key == "today":
        return now_date, now_date
    if key == "yesterday":
        target = now_date - timedelta(days=1)
        return target, target
    if key == "this_week":
        start = now_date - timedelta(days=now_date.weekday())
        return start, start + timedelta(days=6)
    if key == "last_week":
        this_start = now_date - timedelta(days=now_date.weekday())
        start = this_start - timedelta(days=7)
        return start, start + timedelta(days=6)
    if key == "this_month":
        start = now_date.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, next_month - timedelta(days=1)
    if key == "last_month":
        this_start = now_date.replace(day=1)
        end = this_start - timedelta(days=1)
        return end.replace(day=1), end

    if not start_date or not end_date:
        raise HTTPException(400, "Tùy chỉnh cần đủ Từ ngày và Đến ngày.")
    if end_date < start_date:
        raise HTTPException(400, "Đến ngày phải bằng hoặc sau Từ ngày.")
    if (end_date - start_date).days > 730:
        raise HTTPException(400, "Khoảng tùy chỉnh tối đa 731 ngày.")
    return start_date, end_date


def _drive_download_purchase_report() -> bytes:
    if not PURCHASE_REPORT_FILE_ID:
        raise HTTPException(503, "Chưa cấu hình file BaoCaoMuaHang trên Google Drive.")
    try:
        credentials, _ = google.auth.default(scopes=[DRIVE_SCOPE])
        session = AuthorizedSession(credentials)
        response = session.get(
            f"https://www.googleapis.com/drive/v3/files/{PURCHASE_REPORT_FILE_ID}?alt=media",
            timeout=30,
        )
        if response.status_code != 200:
            raise HTTPException(
                503,
                f"Không đọc được BaoCaoMuaHang từ Google Drive (HTTP {response.status_code}).",
            )
        content = bytes(response.content or b"")
        if not content:
            raise HTTPException(503, "File BaoCaoMuaHang trên Google Drive đang trống.")
        return content
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Không đọc được BaoCaoMuaHang: {type(exc).__name__}.") from exc


def _header_index(keys: list[str], wanted: str, fallback: int | None = None) -> int | None:
    try:
        return keys.index(wanted)
    except ValueError:
        return fallback


def _parse_purchase_report(content: bytes, norm) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with open_workbook(BytesIO(content)) as workbook:
            if PURCHASE_REPORT_WORKSHEET not in workbook.sheets:
                raise HTTPException(
                    503,
                    f"BaoCaoMuaHang không có sheet '{PURCHASE_REPORT_WORKSHEET}'.",
                )
            with workbook.get_sheet(PURCHASE_REPORT_WORKSHEET) as worksheet:
                header_map: dict[str, int | None] | None = None
                for raw_row in worksheet.rows():
                    values = [cell.v for cell in raw_row]
                    if header_map is None:
                        keys = [norm(value) for value in values]
                        if norm("Ngày nhập") in keys and norm("Thành Tiền") in keys:
                            header_map = {
                                "date": _header_index(keys, norm("Ngày nhập"), 0),
                                "item": _header_index(keys, norm("Chi tiết hàng hóa"), 1),
                                "qty": _header_index(keys, norm("Số lượng"), 2),
                                "unit_price": _header_index(keys, norm("Đơn giá"), 3),
                                "amount": _header_index(keys, norm("Thành Tiền"), 4),
                                "buyer": _header_index(keys, norm("Ghi chú/ Người đặt mua hàng"), 5),
                                "entered_date": 6,
                                "entered_time": 7,
                                "user": _header_index(keys, norm("User"), 8),
                            }
                        continue

                    date_index = int(header_map["date"] or 0)
                    amount_index = int(header_map["amount"] or 4)
                    business_date = _excel_serial_date(values[date_index] if date_index < len(values) else None)
                    if not business_date:
                        continue
                    amount = _money(values[amount_index] if amount_index < len(values) else 0)
                    item_index = int(header_map["item"] or 1)
                    qty_index = int(header_map["qty"] or 2)
                    unit_index = int(header_map["unit_price"] or 3)
                    buyer_index = int(header_map["buyer"] or 5)
                    user_index = int(header_map["user"] or 8)
                    rows.append({
                        "date": business_date,
                        "date_label": _fmt_date(business_date),
                        "item": str(values[item_index] or "").strip() if item_index < len(values) else "",
                        "quantity": _money(values[qty_index] if qty_index < len(values) else 0),
                        "unit_price": _money(values[unit_index] if unit_index < len(values) else 0),
                        "amount": amount,
                        "buyer": str(values[buyer_index] or "").strip() if buyer_index < len(values) else "",
                        "user": str(values[user_index] or "").strip() if user_index < len(values) else "",
                    })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Không đọc được cấu trúc BaoCaoMuaHang.xlsb: {type(exc).__name__}.") from exc

    if not rows:
        raise HTTPException(503, "BaoCaoMuaHang chưa có dòng dữ liệu mua hàng hợp lệ.")
    return rows


def _transaction_business_date(row: list[Any], headers: list[str], norm) -> tuple[date | None, str]:
    def cell(name: str, fallback_index: int | None = None):
        key = norm(name)
        try:
            index = headers.index(key)
        except ValueError:
            index = fallback_index
        return row[index] if index is not None and index < len(row) else ""

    note = cell("Ghi chú", 4)
    note_dates = _dates_in_text(note)
    if note_dates:
        return note_dates[-1], "note"
    parsed = _parse_date(cell("Ngày giao dịch", 3))
    if parsed:
        return parsed, "transaction_date"
    timestamp_dates = _dates_in_text(cell("Dấu thời gian", 0))
    if timestamp_dates:
        return timestamp_dates[-1], "timestamp"
    return None, ""


def _parse_revenue_input(values: list[list[Any]], norm) -> list[dict[str, Any]]:
    if not values:
        raise HTTPException(503, "Quản lý Thu Chi · Input chưa có dữ liệu.")
    headers = [norm(value) for value in values[0]]
    try:
        type_index = headers.index(norm("Loại giao dịch"))
        amount_index = headers.index(norm("Số tiền"))
    except ValueError as exc:
        raise HTTPException(503, "Sheet Input phải có cột B 'Loại giao dịch' và cột C 'Số tiền'.") from exc

    note_index = _header_index(headers, norm("Ghi chú"), 4)
    email_index = _header_index(headers, norm("Địa chỉ email"), 5)
    rows: list[dict[str, Any]] = []
    for raw in values[1:]:
        tx_type = str(raw[type_index] if type_index < len(raw) else "").strip()
        type_key = norm(tx_type)
        if type_key not in {"thu", "chi"}:
            continue
        amount = _money(raw[amount_index] if amount_index < len(raw) else 0)
        business_date, date_source = _transaction_business_date(raw, headers, norm)
        if not business_date:
            continue
        note = str(raw[note_index] if note_index is not None and note_index < len(raw) else "").strip()
        note_key = norm(note)
        is_purchase = type_key == "chi" and bool(re.match(r"^mua(?:\s|$)", note_key))
        rows.append({
            "date": business_date,
            "date_label": _fmt_date(business_date),
            "type": tx_type,
            "amount": amount,
            "note": note,
            "email": str(raw[email_index] if email_index is not None and email_index < len(raw) else "").strip(),
            "date_source": date_source,
            "is_purchase": is_purchase,
        })
    return rows


def _filtered(rows: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    return [row for row in rows if start <= row["date"] <= end]


def _comparison(
    purchase_rows: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    purchase_by_date: dict[date, float] = defaultdict(float)
    ledger_by_date: dict[date, float] = defaultdict(float)
    for row in purchase_rows:
        purchase_by_date[row["date"]] += float(row.get("amount") or 0)
    for row in ledger_rows:
        if row.get("is_purchase"):
            ledger_by_date[row["date"]] += float(row.get("amount") or 0)

    output: list[dict[str, Any]] = []
    for target in sorted(set(purchase_by_date) | set(ledger_by_date), reverse=True):
        purchase_total = round(purchase_by_date.get(target, 0.0), 2)
        ledger_total = round(ledger_by_date.get(target, 0.0), 2)
        difference = round(purchase_total - ledger_total, 2)
        output.append({
            "date": target.isoformat(),
            "date_label": _fmt_date(target),
            "purchase_total": purchase_total,
            "ledger_purchase_total": ledger_total,
            "difference": difference,
            "matched": abs(difference) < 0.5,
        })
    return output


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        item = dict(row)
        if isinstance(item.get("date"), date):
            item["date"] = item["date"].isoformat()
        output.append(item)
    return output


def install_purchase_reconcile_routes(
    app, *, engine_instance, current_identity, require_feature, norm, google_client,
) -> None:
    if getattr(app.state, "purchase_reconcile_installed", False):
        return

    @app.get("/v2/revenue/purchase-reconcile/health")
    def purchase_reconcile_health():
        return {
            "ok": True,
            "release": RELEASE,
            "purchase_source": "BaoCaoMuaHang.xlsb",
            "ledger_source": f"Quản lý Thu Chi · {REVENUE_WORKSHEET}",
            "comparison": "daily_purchase_total_vs_input_chi_purchase_rows",
            "presets": sorted(DATE_RANGE_PRESETS),
        }

    @app.get("/v2/revenue/purchase-reconcile")
    def purchase_reconcile(
        preset: str = Query(default="this_month", max_length=30),
        start_date: date | None = Query(default=None, alias="start"),
        end_date: date | None = Query(default=None, alias="end"),
        ident=Depends(current_identity),
    ):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)

        start, end = _resolve_range(preset, start_date, end_date)
        purchase_content = _drive_download_purchase_report()
        purchase_all = _parse_purchase_report(purchase_content, norm)
        try:
            revenue_values = google_client().open_by_key(REVENUE_SPREADSHEET_ID).worksheet(REVENUE_WORKSHEET).get_all_values()
        except Exception as exc:
            raise HTTPException(
                503,
                f"Không đọc được Quản lý Thu Chi · sheet {REVENUE_WORKSHEET}: {type(exc).__name__}.",
            ) from exc
        ledger_all = _parse_revenue_input(revenue_values, norm)

        purchase_rows = _filtered(purchase_all, start, end)
        ledger_rows = _filtered(ledger_all, start, end)
        compare_rows = _comparison(purchase_rows, ledger_rows)
        mismatches = [row for row in compare_rows if not row["matched"]]
        purchase_total = round(sum(float(row.get("amount") or 0) for row in purchase_rows), 2)
        ledger_purchase_total = round(
            sum(float(row.get("amount") or 0) for row in ledger_rows if row.get("is_purchase")), 2
        )
        ledger_income = round(
            sum(float(row.get("amount") or 0) for row in ledger_rows if norm(row.get("type")) == "thu"), 2
        )
        ledger_expense = round(
            sum(float(row.get("amount") or 0) for row in ledger_rows if norm(row.get("type")) == "chi"), 2
        )

        return {
            "ok": True,
            "release": RELEASE,
            "preset": preset,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_date_label": _fmt_date(start),
            "end_date_label": _fmt_date(end),
            "purchase_source": "BaoCaoMuaHang.xlsb",
            "purchase_worksheet": PURCHASE_REPORT_WORKSHEET,
            "ledger_source": "Quản lý Thu Chi",
            "ledger_worksheet": REVENUE_WORKSHEET,
            "purchase_total": purchase_total,
            "ledger_purchase_total": ledger_purchase_total,
            "difference": round(purchase_total - ledger_purchase_total, 2),
            "ledger_income": ledger_income,
            "ledger_expense": ledger_expense,
            "purchase_row_count": len(purchase_rows),
            "ledger_row_count": len(ledger_rows),
            "comparison_rows": compare_rows,
            "mismatch_count": len(mismatches),
            "all_match": len(mismatches) == 0,
            "purchase_rows": _serialize_rows(sorted(purchase_rows, key=lambda row: row["date"], reverse=True)),
            "ledger_rows": _serialize_rows(sorted(ledger_rows, key=lambda row: row["date"], reverse=True)),
        }

    app.state.purchase_reconcile_installed = True
    app.state.purchase_reconcile_release = RELEASE

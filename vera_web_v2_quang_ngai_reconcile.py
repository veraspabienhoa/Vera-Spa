"""Quang Ngai reconciliation and exports, with no external-source fallback."""
from datetime import date, datetime
from typing import Any
from io import BytesIO
import re
from fastapi import Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
import vera_quang_ngai_store as revenue_store
import vera_quang_ngai_purchase_store as purchase_store
from vera_web_v2_purchase_reconcile import _resolve_range, _parse_date, _fmt_date, _filtered, VN_TZ, DATE_RANGE_PRESETS
from vera_web_v2_purchase_reconcile_v2 import _enhanced_comparison as _comparison
RELEASE='quang-ngai-v1'
REVENUE_FEATURE='quang_ngai'
PURCHASE_REPORT_WORKSHEET='Input'

def _live_ledger(conn, source, preset, start, end):
    """The register follows its own filters, independently of saved report dates."""
    all_dates = str(preset).strip().lower() == 'all'
    first, last = (None, None) if all_dates else (start, end)
    rows = revenue_store.list_entries(conn, start_date=first, end_date=last)
    if all_dates:
        days = [_parse_date(row.get('date')) for row in rows]
        days = [day for day in days if day]
        today = datetime.now(VN_TZ).date()
        start = min(days) if days else today
        end = max([today, *days])
    return rows, start, end


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        item = dict(row)
        if isinstance(item.get("date"), date):
            item["date"] = item["date"].isoformat()
        output.append(item)
    return output


def _ledger_export(rows: list[dict[str, Any]]) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Doanh thu-Chi phí"
    headers = ["Ngày", "Loại giao dịch", "Số tiền", "Ghi chú", "Ngày nhập", "Giờ nhập", "Người nhập"]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F513F")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in rows:
        transaction_date = _parse_date(row.get("date"))
        entered_date = _parse_date(row.get("entered_date")) or _parse_date(row.get("entered_date_label"))
        sheet.append([
            transaction_date or row.get("date_label") or "", row.get("type") or "", float(row.get("amount") or 0),
            row.get("note") or "", entered_date or row.get("entered_date_label") or "",
            row.get("entered_time") or "", row.get("entered_by") or "",
        ])
    for column in ("A", "E"):
        for cell in sheet[column][1:]:
            if isinstance(cell.value, (date, datetime)):
                cell.number_format = "dd-mm-yyyy"
    for cell in sheet["C"][1:]:
        cell.number_format = '#,##0"đ"'
    widths = [14, 18, 18, 48, 14, 12, 26.55]
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream


def install_purchase_reconcile_routes(
    app, *, engine_instance, current_identity, require_feature, norm, google_client,
) -> None:
    if getattr(app.state, "purchase_reconcile_installed", False):
        return

    @app.get('/v2/quang-ngai/purchase-summary')
    def revenue_purchases(preset: str = 'this_month', start: date | None = None,
                          end: date | None = None, ident=Depends(current_identity)):
        first, last = _resolve_range(preset, start, end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            rows = purchase_store.report_rows(conn, first, last)
        return {'purchase_rows': _serialize_rows(rows), 'purchase_total': sum(row['amount'] for row in rows),
                'start_date': first.isoformat(), 'end_date': last.isoformat(), 'source': 'purchases'}

    @app.get("/v2/quang-ngai/purchase-reconcile/health")
    def purchase_reconcile_health():
        return {
            "ok": True,
            "release": RELEASE,
            "purchase_source": "BaoCaoMuaHang.xlsb",
            "ledger_source": "Quảng Ngãi · vera_quang_ngai_entry",
            "comparison": "daily_purchase_total_vs_input_chi_purchase_rows",
            "presets": sorted(DATE_RANGE_PRESETS),
        }

    @app.get("/v2/quang-ngai/purchase-reconcile")
    def purchase_reconcile(
        preset: str = Query(default="this_month", max_length=30),
        start_date: date | None = Query(default=None, alias="start"),
        end_date: date | None = Query(default=None, alias="end"),
        canonical: bool = False,
        report_end: date | None = None,
        live_ledger: bool = False,
        ident=Depends(current_identity),
    ):
        start, end = _resolve_range(preset, start_date, end_date)
        if canonical and not live_ledger and report_end is not None:
            end = min(end, report_end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            shared = {'source': 'manual', 'revision': 0}
            if live_ledger:
                ledger_all, start, end = _live_ledger(conn, shared['source'], preset, start, end)
            purchase_all = purchase_store.report_rows(conn, start, end)
            if not live_ledger and (shared["source"] == "auto" or canonical):
                start, end = (start, end)
                ledger_all = revenue_store.list_entries(conn, start_date=start, end_date=end)
            elif not live_ledger:
                ledger_all = revenue_store.list_entries(conn, start_date=start, end_date=end)
        server_source = purchase_all is not None
        for row in ledger_all:
            row["is_purchase"] = bool(row.get("is_purchase")) or (norm(row.get("type")) == "chi" and bool(re.match(r"^mua(?:\s|$)", norm(row.get("note")))))
            parsed_date = _parse_date(row.get("date"))
            row["date"] = parsed_date
            row["date_label"] = _fmt_date(parsed_date) if parsed_date else ""

        purchase_rows = _filtered(purchase_all, start, end)
        ledger_rows = [row for row in ledger_all if row.get("date")]
        compare_rows = _comparison(purchase_rows, ledger_rows)
        mismatches = [row for row in compare_rows if row['status'] == 'KHÔNG KHỚP']
        near_count = sum(row['status'] == 'GẦN KHỚP' for row in compare_rows)
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
            "source": shared["source"], "source_revision": shared["revision"], "canonical": canonical, "live_ledger": live_ledger,
            "preset": preset,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_date_label": _fmt_date(start),
            "end_date_label": _fmt_date(end),
            "purchase_source": "Quảng Ngãi · Nhập mua" if server_source else "BaoCaoMuaHang.xlsb",
            "purchase_worksheet": PURCHASE_REPORT_WORKSHEET,
            "ledger_source": "Quảng Ngãi",
            "ledger_worksheet": "vera_quang_ngai_entry",
            "purchase_total": purchase_total,
            "ledger_purchase_total": ledger_purchase_total,
            "difference": round(purchase_total - ledger_purchase_total, 2),
            "ledger_income": ledger_income,
            "ledger_expense": ledger_expense,
            "purchase_row_count": len(purchase_rows),
            "ledger_row_count": len(ledger_rows),
            "comparison_rows": compare_rows,
            "mismatch_count": len(mismatches),
            "near_match_count": near_count,
            "overall_status": "KHÔNG KHỚP" if mismatches else "GẦN KHỚP" if near_count else "KHỚP",
            "all_match": len(mismatches) == 0,
            "purchase_rows": _serialize_rows(sorted(purchase_rows, key=lambda row: row["date"], reverse=True)),
            "ledger_rows": _serialize_rows(sorted(ledger_rows, key=lambda row: row["date"], reverse=True)),
        }

    @app.get("/v2/quang-ngai/ledger/export.xlsx")
    def export_revenue_ledger(
        preset: str = Query(default="this_month", max_length=30),
        start_date: date | None = Query(default=None, alias="start"),
        end_date: date | None = Query(default=None, alias="end"),
        transaction_date: date | None = Query(default=None),
        entered_date: date | None = Query(default=None),
        transaction_type: str = Query(default="", max_length=30),
        amount: str = Query(default="", max_length=40),
        note: str = Query(default="", max_length=300),
        entered_by: str = Query(default="", max_length=200),
        canonical: bool = False,
        report_end: date | None = None,
        live_ledger: bool = False,
        ident=Depends(current_identity),
    ):
        start, end = _resolve_range(preset, start_date, end_date)
        if canonical and not live_ledger and report_end is not None:
            end = min(end, report_end)
        if canonical and not live_ledger:
            start, end = (start, end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            source = {'source': 'manual', 'revision': 0}['source']
            if live_ledger:
                rows, start, end = _live_ledger(conn, source, preset, start, end)
            else:
                rows = revenue_store.list_entries(conn, start_date=start, end_date=end)
        type_key, note_key, entered_by_key = norm(transaction_type), norm(note), norm(entered_by)
        amount_digits = re.sub(r"\D", "", amount)
        rows = [row for row in rows if (
            (not transaction_date or _parse_date(row.get("date")) == transaction_date)
            and (not entered_date or _parse_date(row.get("entered_date_label")) == entered_date)
            and (not type_key or norm(row.get("type")) == type_key)
            and (not note_key or note_key in norm(row.get("note")))
            and (not entered_by_key or entered_by_key in norm(row.get("entered_by")))
            and (not amount_digits or amount_digits in str(round(float(row.get("amount") or 0))))
        )]
        filename = f"QuangNgai_ChiPhi_{start:%d-%m-%Y}_{end:%d-%m-%Y}.xlsx"
        return StreamingResponse(
            _ledger_export(sorted(rows, key=lambda row: row["date"], reverse=True)),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    app.state.purchase_reconcile_installed = True
    app.state.purchase_reconcile_release = RELEASE

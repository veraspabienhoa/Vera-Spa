"""Build canonical Payroll Excel input from TimeSoft snapshots already synced to PostgreSQL.

The browser may still upload the official TimeSoft Excel file manually.  This
module adds a second source path that reconstructs the same four fields consumed
by the canonical payroll calculator (time, item, amount, employee) from the
long-lived ``timesoft_summary_invoice_YYYYMMDD`` datasets written by
``timesoft_sync_job.py``.  The resulting workbook deliberately uses the exact
TimeSoft header expected by ``vera_web_v2_payroll._read_source`` so all Payroll
3.7/3.8 validation and deduction rules remain the single calculation path.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import numbers
import re
from typing import Any, Callable, Iterator
from urllib.parse import quote

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import text

import vera_web_v2_payroll as payroll


RELEASE = "payroll-timesoft-auto-2026-08-29.1"
VN_TZ = timezone(timedelta(hours=7))
DATASET_PREFIX = "timesoft_summary_invoice_"

TIME_KEYS = (
    "thoi gian", "create time", "createtime", "create time str", "createtimestr",
    "create date", "createdate", "create date str", "createdatestr", "invoice date",
    "invoicedate", "invoice time", "invoicetime", "date", "time",
)
ITEM_KEYS = (
    "san pham dich vu pt", "san pham dich vu", "product name", "productname",
    "product service name", "productservicename", "service name", "servicename",
    "item name", "itemname", "product", "service", "item",
)
AMOUNT_KEYS = (
    "tong tien", "total money", "totalmoney", "total amount", "totalamount",
    "line amount", "lineamount", "amount", "total price", "totalprice", "price", "money",
)
EMPLOYEE_KEYS = (
    "nv tu van", "nhan vien tu van", "employee name", "employeename", "staff name",
    "staffname", "consultant name", "consultantname", "advisor name", "advisorname",
    "employeeinfo name", "employee info name", "name employee",
)


def _clean_key(value: Any, norm: Callable[[Any], str]) -> str:
    return norm(str(value or "").replace(".", " ").replace("_", " ").replace("-", " "))


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bytes, bool, numbers.Number, date, datetime))


def _leaf_contexts(node: Any, inherited: dict[str, Any] | None = None, prefix: str = "") -> Iterator[dict[str, Any]]:
    inherited = dict(inherited or {})
    if isinstance(node, dict):
        current = dict(inherited)
        children: list[tuple[str, Any]] = []
        for raw_key, value in node.items():
            key = f"{prefix}.{raw_key}" if prefix else str(raw_key)
            if _scalar(value):
                current[key] = value
            elif isinstance(value, (dict, list, tuple)):
                children.append((key, value))
        if not children:
            yield current
            return
        for key, child in children:
            yielded = False
            for context in _leaf_contexts(child, current, key):
                yielded = True
                yield context
            if not yielded:
                yield current
        return
    if isinstance(node, (list, tuple)):
        if not node:
            yield inherited
            return
        for index, child in enumerate(node):
            child_prefix = f"{prefix}.{index}" if prefix else str(index)
            if _scalar(child):
                context = dict(inherited)
                context[child_prefix] = child
                yield context
            else:
                yield from _leaf_contexts(child, inherited, child_prefix)
        return
    context = dict(inherited)
    context[prefix or "value"] = node
    yield context


def _preferred_value(context: dict[str, Any], aliases: tuple[str, ...], norm) -> Any:
    items = [(_clean_key(key, norm), value) for key, value in context.items()]
    normalized_aliases = [_clean_key(alias, norm) for alias in aliases]
    for alias in normalized_aliases:
        for key, value in items:
            if key == alias and str(value or "").strip():
                return value
    for alias in normalized_aliases:
        for key, value in items:
            if (key.endswith(" " + alias) or alias in key) and str(value or "").strip():
                return value
    return None


def _tip_item(context: dict[str, Any], norm) -> str:
    direct = _preferred_value(context, ITEM_KEYS, norm)
    candidates = [direct] if direct is not None else []
    candidates.extend(value for value in context.values() if isinstance(value, str))
    for value in candidates:
        item = str(value or "").strip()
        if re.match(payroll.TIP_ITEM_PATTERN, item, flags=re.IGNORECASE):
            return item
    return ""


def _employee_value(context: dict[str, Any], known_names: dict[str, str], norm) -> str:
    direct = _preferred_value(context, EMPLOYEE_KEYS, norm)
    if direct is not None:
        direct_text = str(direct or "").strip()
        if direct_text:
            return known_names.get(norm(direct_text), direct_text)
    for value in context.values():
        if not isinstance(value, str):
            continue
        canonical = known_names.get(norm(value))
        if canonical:
            return canonical
    return ""


def _number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, numbers.Number):
        return int(round(float(value)))
    raw = str(value or "").strip()
    if not raw:
        return None
    negative = raw.startswith("-")
    digits = re.sub(r"[^0-9]", "", raw)
    if not digits:
        return None
    return (-1 if negative else 1) * int(digits)


def _amount_value(context: dict[str, Any], norm) -> int | None:
    direct = _preferred_value(context, AMOUNT_KEYS, norm)
    parsed = _number(direct)
    if parsed is not None:
        return parsed
    scored: list[tuple[int, int]] = []
    for raw_key, value in context.items():
        number = _number(value)
        if number is None:
            continue
        key = _clean_key(raw_key, norm)
        score = 0
        if "tong tien" in key or "total money" in key or "total amount" in key:
            score += 10
        if "amount" in key or "money" in key or "price" in key:
            score += 6
        if "discount" in key or "giam gia" in key or "quantity" in key or "so luong" in key:
            score -= 12
        if score > 0:
            scored.append((score, number))
    return max(scored, default=(0, None), key=lambda item: item[0])[1]


def _time_value(context: dict[str, Any], target_date: date, norm) -> Any:
    value = _preferred_value(context, TIME_KEYS, norm)
    if value is None or str(value or "").strip() == "":
        return datetime.combine(target_date, datetime.min.time())
    return value


def _known_employee_names(conn, norm) -> dict[str, str]:
    rows = conn.execute(text("""
        SELECT username, COALESCE(full_name,'') AS full_name
        FROM employees
        WHERE lower(COALESCE(role,'')) IN ('nhanvien','leader')
    """)).mappings().all()
    output: dict[str, str] = {}
    for row in rows:
        username = str(row.get("username") or "").strip()
        full_name = str(row.get("full_name") or "").strip()
        if username:
            output[norm(username)] = username
        if full_name and username:
            output[norm(full_name)] = username
    return output


def _dataset_row(conn, target_date: date) -> tuple[bool, list[Any]]:
    key = f"{DATASET_PREFIX}{target_date.strftime('%Y%m%d')}"
    row = conn.execute(text("""
        SELECT payload, row_count
        FROM vera_dataset_cache
        WHERE dataset_key=:key
        LIMIT 1
    """), {"key": key}).mappings().first()
    if row is None:
        return False, []
    payload = row.get("payload")
    if isinstance(payload, dict):
        payload = payload.get("rows") or payload.get("data") or []
    if not isinstance(payload, list):
        payload = []
    return True, payload


def _period_dates(start: date, end: date) -> list[date]:
    today = datetime.now(VN_TZ).date()
    effective_end = min(end, today)
    if effective_end < start:
        raise HTTPException(409, "Kỳ lương này chưa bắt đầu nên TimeSoft chưa có dữ liệu để tính.")
    return [start + timedelta(days=index) for index in range((effective_end - start).days + 1)]


def _canonical_tip_rows(conn, start: date, end: date, norm) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    known_names = _known_employee_names(conn, norm)
    required_dates = _period_dates(start, end)
    missing_dates: list[date] = []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    sample_keys: set[str] = set()
    source_records = 0

    for target_date in required_dates:
        exists, payload = _dataset_row(conn, target_date)
        if not exists:
            missing_dates.append(target_date)
            continue
        source_records += len(payload)
        for record in payload:
            if isinstance(record, dict):
                sample_keys.update(str(key) for key in record.keys())
            for context in _leaf_contexts(record):
                item = _tip_item(context, norm)
                if not item:
                    continue
                employee = _employee_value(context, known_names, norm)
                amount = _amount_value(context, norm)
                if not employee or amount is None:
                    continue
                time_value = _time_value(context, target_date, norm)
                signature = (target_date.isoformat(), norm(item), int(amount), norm(employee))
                if signature in seen:
                    continue
                seen.add(signature)
                rows.append({
                    "time": time_value,
                    "item": item,
                    "amount": int(amount),
                    "employee": employee,
                })

    if missing_dates:
        labels = ", ".join(value.strftime("%d/%m/%Y") for value in missing_dates[:12])
        more = f" (+{len(missing_dates) - 12} ngày)" if len(missing_dates) > 12 else ""
        raise HTTPException(
            409,
            f"TimeSoft chưa đồng bộ đủ PostgreSQL cho kỳ lương. Thiếu: {labels}{more}. "
            "Hãy chạy đồng bộ TimeSoft hoặc dùng Upload Excel.",
        )
    if not rows:
        keys = ", ".join(sorted(sample_keys)[:18]) or "(không có cột nguồn)"
        raise HTTPException(
            422,
            "Đã có snapshot TimeSoft nhưng chưa nhận diện được dòng TIP phù hợp để tính lương. "
            f"Cột nguồn mẫu: {keys}. Có thể tiếp tục dùng Upload Excel trong khi kiểm tra mapping TimeSoft.",
        )

    return rows, {
        "source": "TimeSoft tự động qua PostgreSQL",
        "required_days": len(required_dates),
        "source_records": source_records,
        "tip_rows": len(rows),
    }


def _workbook(rows: list[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Báo cáo doanh thu hóa đơn"
    worksheet.append([])
    worksheet.append([])
    worksheet.append(list(payroll.TIMESOFT_PAYROLL_HEADERS))
    for index, row in enumerate(rows, start=1):
        values = [""] * len(payroll.TIMESOFT_PAYROLL_HEADERS)
        values[0] = index
        values[1] = row.get("time")
        values[5] = row.get("item")
        values[6] = row.get("amount")
        values[8] = row.get("employee")
        worksheet.append(values)
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def install_payroll_timesoft_auto_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature,
    identity_type,
    norm,
) -> None:
    if getattr(app.state, "payroll_timesoft_auto_installed", False):
        return

    @app.get("/v2/payroll-timesoft-auto/health")
    def payroll_timesoft_auto_health():
        return {
            "ok": True,
            "release": RELEASE,
            "source": "timesoft_summary_invoice_YYYYMMDD",
            "fallback": "manual_excel_upload",
            "canonical_excel_compatible": True,
        }

    @app.get("/v2/payroll/timesoft-source.xlsx")
    def payroll_timesoft_source(
        month: str = Query(...),
        period_no: int = Query(..., ge=1, le=2),
        ident: identity_type = Depends(current_identity),
    ):
        start, end, label = payroll._period(month, period_no)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            rows, summary = _canonical_tip_rows(conn, start, end, norm)
        content = _workbook(rows)
        filename = f"TimeSoft_Auto_{month}_Ky{period_no}.xlsx"
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Vera-TimeSoft-Source": "postgresql",
            "X-Vera-TimeSoft-Tip-Rows": str(summary["tip_rows"]),
            "X-Vera-Payroll-Period": label,
        }
        return StreamingResponse(
            BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )

    app.state.payroll_timesoft_auto_installed = True
    app.state.payroll_timesoft_auto_release = RELEASE

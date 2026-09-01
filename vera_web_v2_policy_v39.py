"""VERA Web V2 V3.9 business-policy additions.

- Employees who start/resume work on or after day 16 are capped at 3 paid-leave
  days for that calendar month.
- Re-activation is stamped in PostgreSQL so the cap also applies to staff who
  were temporarily away during days 1-15.
- Payroll TimeSoft input always reads the worksheet named
  ``Báo cáo doanh thu hóa đơn``.
- A small authenticated detector lets the browser select month/period from the
  actual dates contained in that worksheet before payroll calculation.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Callable

import pandas as pd
from fastapi import Body, Depends, HTTPException
from sqlalchemy import text

import vera_web_v2_api_shared as _shared
import vera_web_v2_payroll as _payroll
import vera_web_v2_staff as _staff

RELEASE = "3.9-policy-payroll-named-report-sheet"
LATE_MONTH_PAID_LIMIT = 3.0
ACTIVE_STATUS = "Đang làm việc"


def _remove_route(app, path: str, method: str):
    method = method.upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            pass
    return None


def _effective_start_or_resume(row: dict[str, Any]) -> date | None:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    resume = _parse_date(payload.get("return_to_work_date") or payload.get("Ngày làm lại gần nhất"))
    return resume or _parse_date(row.get("employment_start_date"))


def _read_payroll_source(content: bytes) -> pd.DataFrame:
    """Use the canonical reader so policy installers cannot change the sheet."""
    return _payroll._read_source(content)


def _period_from_source(source: pd.DataFrame) -> tuple[str, int, date, date]:
    dated = source.dropna(subset=["time"]).copy()
    if dated.empty:
        raise HTTPException(
            400,
            f"Sheet '{_payroll.PAYROLL_SOURCE_WORKSHEET}' không có ngày hợp lệ ở cột B "
            "để tự nhận Kỳ lương.",
        )
    item_norm = dated["item"].astype(str).str.strip().str.casefold()
    tips = dated[item_norm.str.match(_payroll.TIP_ITEM_PATTERN, na=False)].copy()
    sample = tips if not tips.empty else dated
    groups: Counter[tuple[int, int, int]] = Counter()
    latest: dict[tuple[int, int, int], date] = {}
    for value in sample["time"].tolist():
        d = pd.Timestamp(value).date()
        key = (d.year, d.month, 1 if d.day <= 15 else 2)
        groups[key] += 1
        latest[key] = max(latest.get(key, d), d)
    if not groups:
        raise HTTPException(
            400,
            f"Không xác định được Kỳ lương từ sheet '{_payroll.PAYROLL_SOURCE_WORKSHEET}'.",
        )
    year, month, period_no = max(groups, key=lambda key: (groups[key], latest[key]))
    month_text = f"{year:04d}-{month:02d}"
    start, end, _ = _payroll._period(month_text, period_no)
    return month_text, period_no, start, end


def install_policy_v39(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature,
    vn_tz,
) -> None:
    if getattr(app.state, "policy_v39_installed", False):
        return

    original_validate = _shared._validate_and_prepare

    def validate_with_late_month_cap(
        conn,
        body,
        ident,
        *,
        exclude_record_uid="",
        skip_registration_timing=False,
        record_uid="",
        existing_ordinal=None,
    ):
        record, warnings = original_validate(
            conn, body, ident,
            exclude_record_uid=exclude_record_uid,
            skip_registration_timing=skip_registration_timing,
            record_uid=record_uid,
            existing_ordinal=existing_ordinal,
        )
        if str(getattr(ident, "role", "") or "").strip().lower() == "admin":
            return record, warnings
        if float(record.get("calculated_days") or 0) <= 0:
            return record, warnings
        try:
            group_now = _shared._policy_group(conn, record.get("leave_reason", ""))
        except Exception:
            group_now = ""
        if group_now != "co_phep":
            return record, warnings

        employee = conn.execute(text("""
            SELECT employment_start_date, payload
            FROM employees
            WHERE lower(btrim(username))=lower(btrim(:username))
            LIMIT 1
        """), {"username": record.get("employee_name", "")}).mappings().first()
        if not employee:
            return record, warnings
        effective = _effective_start_or_resume(dict(employee))
        target = body.leave_date
        if not effective or effective.year != target.year or effective.month != target.month or effective.day < 16:
            return record, warnings

        rows = conn.execute(text("""
            SELECT leave_reason, calculated_days
            FROM leave_records
            WHERE lower(btrim(employee_name))=lower(btrim(:employee))
              AND leave_date >= :start AND leave_date <= :end
              AND (:uid = '' OR record_uid <> :uid)
        """), {
            "employee": record.get("employee_name", ""),
            "start": target.replace(day=1),
            "end": _payroll._period(f"{target.year:04d}-{target.month:02d}", 2)[1],
            "uid": str(exclude_record_uid or ""),
        }).mappings().all()
        used = 0.0
        for row in rows:
            try:
                if _shared._policy_group(conn, row.get("leave_reason", "")) == "co_phep":
                    used += max(0.0, float(row.get("calculated_days") or 0))
            except Exception:
                continue
        requested = max(0.0, float(record.get("calculated_days") or 0))
        if used + requested > LATE_MONTH_PAID_LIMIT + 1e-9:
            raise HTTPException(
                400,
                f"Nhân viên bắt đầu/làm lại từ {effective.strftime('%d/%m/%Y')} (từ ngày 16). "
                f"Tháng {target.month}/{target.year} chỉ được tối đa 3 ngày nghỉ CÓ phép; "
                f"đã dùng {used:g} ngày, đăng ký thêm {requested:g} ngày.",
            )
        return record, warnings

    _shared._validate_and_prepare = validate_with_late_month_cap
    _shared._api._validate_and_prepare = validate_with_late_month_cap

    # Stamp the exact date a temporarily-away employee is switched back active.
    original_staff_update = _remove_route(app, "/v2/staff/{username}", "PATCH")
    if not callable(original_staff_update):
        raise RuntimeError("Không tìm thấy route sửa nhân viên để cài ngày làm lại.")

    @app.patch("/v2/staff/{username}")
    def update_staff_with_resume_date(username: str, body: _staff.StaffUpdate, ident=Depends(current_identity)):
        with engine_instance().connect() as conn:
            before = conn.execute(text("""
                SELECT COALESCE(payload->>'Trạng thái làm việc', payload->>'employment_status', 'Đang làm việc')
                FROM employees WHERE lower(btrim(username))=lower(btrim(:username)) LIMIT 1
            """), {"username": username}).scalar_one_or_none()
        result = original_staff_update(username=username, body=body, ident=ident)
        requested = getattr(body, "employment_status", None)
        if requested == ACTIVE_STATUS and str(before or ACTIVE_STATUS) != ACTIVE_STATUS:
            resume_text = datetime.now(vn_tz).strftime("%d/%m/%Y")
            with engine_instance().begin() as conn:
                conn.execute(text("""
                    UPDATE employees
                    SET payload=jsonb_set(
                        COALESCE(payload,'{}'::jsonb), '{return_to_work_date}',
                        to_jsonb(CAST(:resume_date AS text)), true
                    ), updated_at=NOW()
                    WHERE lower(btrim(username))=lower(btrim(:username))
                """), {"resume_date": resume_text, "username": username})
        return result

    @app.post("/v2/payroll/detect-period")
    def detect_payroll_period(
        payload: bytes = Body(..., media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ident=Depends(current_identity),
    ):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
        source = _read_payroll_source(payload)
        month, period_no, start, end = _period_from_source(source)
        return {
            "ok": True,
            "month": month,
            "period_no": period_no,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "sheet_name": _payroll.PAYROLL_SOURCE_WORKSHEET,
            "message": (
                f"Đã nhận Kỳ {period_no} - Tháng {int(month[-2:])}/{month[:4]} "
                f"từ sheet '{_payroll.PAYROLL_SOURCE_WORKSHEET}'."
            ),
        }

    @app.get("/v2/policy-v39/health")
    def policy_v39_health():
        return {
            "ok": True,
            "release": RELEASE,
            "payroll_sheet": _payroll.PAYROLL_SOURCE_WORKSHEET,
            "auto_penalty_minutes": 5,
        }

    app.state.policy_v39_installed = True

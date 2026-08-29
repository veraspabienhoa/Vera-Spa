"""VERA SPA Web V2 policy 4.0.

Rules in this patch:
- The monthly maximum of two weekend registrations applies only to Group 3:
  Nghỉ CUỐI TUẦN CÓ phép, Đi trễ CUỐI TUẦN CÓ phép, Về sớm CUỐI TUẦN CÓ phép.
- Quản lý and Lễ tân may backfill past dates only when the canonical Nội quy
  registration rule accepts the row as Loại nghỉ = Vi phạm.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

import pandas as pd

from vera_leave_registration_shared import norm


RELEASE = "4.0-weekend-group3-past-violations"
GROUP3_WEEKEND_REASONS = (
    "Nghỉ CUỐI TUẦN CÓ phép",
    "Đi trễ CUỐI TUẦN CÓ phép",
    "Về sớm CUỐI TUẦN CÓ phép",
)
GROUP3_WEEKEND_REASON_KEYS = frozenset(norm(value) for value in GROUP3_WEEKEND_REASONS)
PAST_VIOLATION_ROLES = {"quanly", "letan"}
VN_TZ = timezone(timedelta(hours=7))


def _reason_key(value: Any) -> str:
    return norm(str(value or "").replace("🔴", "").strip())


def _parse_date(value: Any):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return parsed.date() if pd.notna(parsed) else None


def group3_monthly_weekend_registration_limit(
    all_leave_df,
    employee_name,
    start_date,
    end_date,
    reason="",
    max_weekend_dates=2,
):
    """Apply the two-weekend/month rule only to the three Group-3 reasons."""
    if _reason_key(reason) not in GROUP3_WEEKEND_REASON_KEYS:
        return True, ""

    selected_weekends = []
    current = start_date
    while current <= end_date:
        if current.weekday() >= 5:
            selected_weekends.append(current)
        current += timedelta(days=1)
    if not selected_weekends:
        return True, ""

    quota_df = all_leave_df.copy() if isinstance(all_leave_df, pd.DataFrame) else pd.DataFrame()
    if not quota_df.empty and "Lý do nghỉ" in quota_df.columns:
        group3_mask = quota_df["Lý do nghỉ"].astype(str).apply(
            lambda value: _reason_key(value) in GROUP3_WEEKEND_REASON_KEYS
        )
        quota_df = quota_df[group3_mask].copy()

    employee_key = norm(employee_name)
    selected_by_month: dict[tuple[int, int], set[date]] = {}
    for target in selected_weekends:
        selected_by_month.setdefault((target.year, target.month), set()).add(target)

    for (year, month), selected_dates in sorted(selected_by_month.items()):
        existing_dates: set[date] = set()
        if not quota_df.empty and {"Ngày", "Tên nhân viên"}.issubset(quota_df.columns):
            frame = quota_df.copy()
            frame["__date"] = frame["Ngày"].apply(_parse_date)
            frame["__employee"] = frame["Tên nhân viên"].astype(str).apply(norm)
            existing_dates = set(
                frame[
                    frame["__date"].notna()
                    & frame["__employee"].eq(employee_key)
                    & frame["__date"].apply(
                        lambda value: value.year == year and value.month == month and value.weekday() >= 5
                    )
                ]["__date"].tolist()
            )

        new_dates = set(selected_dates) - existing_dates
        projected = len(existing_dates) + len(new_dates)
        if projected > int(max_weekend_dates):
            selected_text = ", ".join(sorted(value.strftime("%d/%m/%Y") for value in selected_dates))
            return False, (
                f"Nhân viên {employee_name} chỉ được đăng ký tối đa {max_weekend_dates} lần cuối tuần "
                f"trong tháng {month:02d}/{year} cho Nhóm 3. "
                f"Đã có {len(existing_dates)} lần Nhóm 3; đăng ký này có ngày cuối tuần: {selected_text}."
            )
    return True, ""


def _now(runtime: Mapping[str, Any]) -> datetime:
    provider = runtime.get("now_vn")
    value = provider() if callable(provider) else datetime.now(VN_TZ)
    if value.tzinfo is None:
        value = value.replace(tzinfo=VN_TZ)
    return value.astimezone(VN_TZ)


def _past_violation_dates_are_allowed(payload: Mapping[str, Any], runtime: Mapping[str, Any], now_vn: datetime) -> bool:
    role = str(payload.get("role", "") or "").strip().lower()
    if role not in PAST_VIOLATION_ROLES:
        return False
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    if not isinstance(start_date, date) or not isinstance(end_date, date) or end_date < start_date:
        return False

    today = now_vn.date()
    past_dates = [
        start_date + timedelta(days=index)
        for index in range((end_date - start_date).days + 1)
        if start_date + timedelta(days=index) < today
    ]
    if not past_dates:
        return False

    validate_notice = runtime.get("validate_leave_registration_notice")
    if not callable(validate_notice):
        return False
    reason = str(payload.get("reason", "") or "")
    for target in past_dates:
        try:
            ok, _message = validate_notice(reason, target, role=role, now_vn=now_vn)
        except Exception:
            return False
        if not ok:
            return False
    return True


def install_policy_v40(app, *, shared_module) -> None:
    if getattr(app.state, "leave_policy_v40_installed", False):
        return

    original_validator = shared_module.validate_leave_registration_request_live

    def validate_with_policy_v40(payload, live_df, credentials_df, runtime):
        runtime_v40 = dict(runtime or {})
        runtime_v40["validate_monthly_weekend_registration_limit"] = group3_monthly_weekend_registration_limit

        now_vn = _now(runtime_v40)
        if _past_violation_dates_are_allowed(payload, runtime_v40, now_vn):
            original_window = runtime_v40.get("employee_registration_window")
            start_date = payload.get("start_date")
            if callable(original_window) and isinstance(start_date, date):
                def relaxed_window(today):
                    _minimum, maximum = original_window(today)
                    return min(start_date, today), maximum

                runtime_v40["employee_registration_window"] = relaxed_window

        return original_validator(payload, live_df, credentials_df, runtime_v40)

    # _validate_and_prepare in vera_web_v2_api_shared resolves these globals at
    # request time, so replacing them here keeps the existing route chain intact.
    shared_module.monthly_weekend_registration_limit = group3_monthly_weekend_registration_limit
    shared_module.validate_leave_registration_request_live = validate_with_policy_v40

    app.state.leave_policy_v40_installed = True
    app.state.leave_policy_v40_release = RELEASE

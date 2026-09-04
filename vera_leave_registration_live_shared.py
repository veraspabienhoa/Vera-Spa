"""Shared live leave-registration validation for Streamlit and Web V2.

The control-flow below is intentionally framework-agnostic and mirrors the
V92.6.99 `_validate_leave_registration_request_live` contract.  UI/API layers
provide the small runtime callbacks that resolve policy/catalog-specific
helpers.  This keeps one validation sequence while preserving the legacy core
helper semantics during migration.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

import pandas as pd

from vera_leave_registration_shared import norm

VN_TZ = timezone(timedelta(hours=7))
EMPLOYEE_LIKE_ROLES = {"nhanvien", "leader", "locker", "tapvu"}


def _call(runtime: Mapping[str, Any], name: str):
    fn = runtime.get(name)
    if not callable(fn):
        raise RuntimeError(f"Shared leave validator missing runtime callback: {name}")
    return fn


def _value(runtime: Mapping[str, Any], name: str, default=None):
    return runtime.get(name, default)


def clean_display(value: Any) -> str:
    text = str(value or "").replace("🔴", "").strip()
    return "" if text.casefold() in {"nan", "none", "nat", "<na>"} else text


def normalize_reason(value: Any) -> str:
    return clean_display(value).casefold()


def employee_registration_window(today: date):
    if today.month == 12:
        next_month_first = date(today.year + 1, 1, 1)
    else:
        next_month_first = date(today.year, today.month + 1, 1)
    if next_month_first.month == 12:
        after_next = date(next_month_first.year + 1, 1, 1)
    else:
        after_next = date(next_month_first.year, next_month_first.month + 1, 1)
    return today, after_next - timedelta(days=1)


def is_annual_reason(reason: Any) -> bool:
    key = norm(clean_display(reason))
    return bool(key and "phep nam" in key)


def is_long_sick_reason(reason: Any) -> bool:
    return norm(clean_display(reason)) == norm("Nghỉ bệnh có giấy khám hoặc được quản lý duyệt")


def is_video_reason(reason: Any) -> bool:
    return norm(clean_display(reason)) == norm("Nghỉ phép quay video")


def is_bereavement_reason(reason: Any) -> bool:
    return norm(clean_display(reason)) == norm("Nghỉ đám hiếu")


def is_special_day_rule_exempt(role: str, reason: Any) -> bool:
    role = str(role or "").strip().lower()
    if role in {"admin", "letan", "quanly"} and is_bereavement_reason(reason):
        return True
    if is_video_reason(reason) or is_long_sick_reason(reason):
        return True
    return False


def rows_counting_toward_quota(df):
    if not isinstance(df, pd.DataFrame) or df.empty or "Lý do nghỉ" not in df.columns:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    reasons = df["Lý do nghỉ"].astype(str)
    exempt = reasons.apply(is_video_reason) | reasons.apply(is_long_sick_reason)
    return df[~exempt].copy()


def _parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return parsed.date() if pd.notna(parsed) else None


def _reason_group(reason: Any) -> str:
    key = norm(clean_display(reason))
    if "khong phep" in key:
        return "khong_phep"
    if "phat sinh" in key:
        return "phat_sinh"
    excluded = (
        "di tre", "ve som", "ra som", "khong don ve sinh", "loi vi pham",
        "qua tour", "xuong phong", "di tua", "ngung nhan", "ho tro ca",
    )
    if ("co phep" in key or "nghi phep" in key or "nghi dam hieu" in key) and not any(x in key for x in excluded):
        return "co_phep"
    return ""


def monthly_weekend_registration_limit(all_leave_df, employee_name, start_date, end_date, reason="", max_weekend_dates=2):
    if "khong phep" in norm(reason):
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
        mask = quota_df["Lý do nghỉ"].astype(str).apply(
            lambda x: "khong phep" in norm(x) or is_video_reason(x) or is_long_sick_reason(x)
        )
        quota_df = quota_df[~mask].copy()

    emp_key = norm(employee_name)
    by_month = {}
    for d in selected_weekends:
        by_month.setdefault((d.year, d.month), set()).add(d)

    for (year, month), selected_dates in sorted(by_month.items()):
        existing_dates = set()
        if not quota_df.empty and {"Ngày", "Tên nhân viên"}.issubset(quota_df.columns):
            tmp = quota_df.copy()
            tmp["__date"] = tmp["Ngày"].apply(_parse_date)
            tmp["__emp"] = tmp["Tên nhân viên"].astype(str).apply(norm)
            existing_dates = set(
                tmp[
                    tmp["__date"].notna()
                    & tmp["__emp"].eq(emp_key)
                    & tmp["__date"].apply(lambda x: x.year == year and x.month == month and x.weekday() >= 5)
                ]["__date"].tolist()
            )
        new_dates = set(selected_dates) - existing_dates
        projected = len(existing_dates) + len(new_dates)
        if projected > int(max_weekend_dates):
            dates_txt = ", ".join(sorted(d.strftime("%d/%m/%Y") for d in selected_dates))
            return False, (
                f"Nhân viên {employee_name} chỉ được đăng ký tối đa {max_weekend_dates} lần cuối tuần "
                f"trong tháng {month:02d}/{year} đối với các lý do chịu giới hạn. "
                f"Đã có {len(existing_dates)} lần; đăng ký này có ngày cuối tuần: {dates_txt}."
            )
    return True, ""


def daily_employee_registration_rule(df_sources, ngay, employee, new_reason, new_days):
    try:
        new_days = float(new_days or 0)
    except Exception:
        new_days = 0.0
    if not any(abs(new_days - x) < 1e-9 for x in (0.0, 0.5, 1.0)):
        return False, "Số ngày tính trong 1 ngày chỉ được phép là 0, 0.5 hoặc 1."
    target_date = _parse_date(ngay)
    if target_date is None:
        return False, "Không xác định được ngày đăng ký."
    if not isinstance(df_sources, pd.DataFrame) or df_sources.empty:
        return True, ""
    if not {"Ngày", "Tên nhân viên", "Lý do nghỉ"}.issubset(df_sources.columns):
        return True, ""

    d = df_sources.copy()
    d["_date_rule"] = d["Ngày"].apply(_parse_date)
    d["_emp_rule"] = d["Tên nhân viên"].astype(str).apply(norm)
    d = d[(d["_date_rule"] == target_date) & d["_emp_rule"].eq(norm(employee))].copy()
    if d.empty:
        return True, ""

    if new_days > 0:
        existing_days = pd.to_numeric(d.get("Số ngày tính", 0), errors="coerce").fillna(0.0)
        positive = d[existing_days > 0]
        if not positive.empty:
            desc = []
            for _, row in positive.iterrows():
                try:
                    day_val = float(pd.to_numeric(row.get("Số ngày tính", 0), errors="coerce") or 0)
                except Exception:
                    day_val = 0.0
                desc.append(f"{clean_display(row.get('Lý do nghỉ', ''))} ({day_val:g} ngày)")
            return False, (
                "Trong cùng 1 ngày, mỗi nhân viên chỉ được có 1 dòng có Số ngày tính > 0. "
                "Không cho phép 0.5 + 0.5 = 1. "
                f"Đã có: {', '.join(desc)}."
            )

    new_group = _reason_group(new_reason)
    if new_group:
        groups = d["Lý do nghỉ"].astype(str).apply(_reason_group)
        same = d[groups == new_group]
        if not same.empty:
            labels = {"co_phep": "CÓ phép", "khong_phep": "KHÔNG phép", "phat_sinh": "PHÁT SINH"}
            old_reasons = [clean_display(x) for x in same["Lý do nghỉ"].astype(str).tolist() if clean_display(x)]
            return False, (
                f"Trong cùng 1 ngày, một nhân viên không được có 2 lần {labels.get(new_group, new_group)}. "
                f"Đã có: {', '.join(old_reasons)}."
            )
    return True, ""


def leave_exists(df_sources, ngay, employee, reason):
    if not isinstance(df_sources, pd.DataFrame) or df_sources.empty:
        return False
    if not {"Ngày", "Tên nhân viên", "Lý do nghỉ"}.issubset(df_sources.columns):
        return False
    target = _parse_date(ngay)
    if target is None:
        return False
    d = df_sources.copy()
    dates = d["Ngày"].apply(_parse_date)
    names = d["Tên nhân viên"].astype(str).apply(norm)
    reasons = d["Lý do nghỉ"].astype(str).apply(normalize_reason)
    return bool(((dates == target) & names.eq(norm(employee)) & reasons.eq(normalize_reason(reason))).any())


def progressive_penalty_reason(value):
    key = norm(clean_display(value))
    mapping = {
        norm("Nghỉ không phép"): "Nghỉ không phép",
        norm("Nghỉ KHÔNG phép"): "Nghỉ không phép",
        norm("Đi trễ không phép"): "Đi trễ không phép",
        norm("Đi trễ KHÔNG phép"): "Đi trễ không phép",
        norm("Về sớm không phép"): "Về sớm không phép",
        norm("Về sớm KHÔNG phép"): "Về sớm không phép",
        norm("Ra sớm không phép"): "Về sớm không phép",
    }
    return mapping.get(key)


def progressive_ordinal_and_bonus(df_sources, ngay, reason):
    canonical = progressive_penalty_reason(reason)
    if canonical is None:
        return 1, 0
    target = _parse_date(ngay)
    if target is None or not isinstance(df_sources, pd.DataFrame) or df_sources.empty:
        ordinal = 1
    else:
        d = df_sources.copy()
        dates = d["Ngày"].apply(_parse_date)
        canonical_series = d["Lý do nghỉ"].astype(str).apply(progressive_penalty_reason)
        ordinal = int(((dates == target) & canonical_series.eq(canonical)).sum()) + 1
    return ordinal, max(0, ordinal - 2) * 100000


def daily_group_quota(all_leave_df, target_date, reason, is_zero_day_co_phep=False, weekday_limit=5, weekend_limit=3, phat_sinh_limit=2):
    group = _reason_group(reason)
    is_weekend = target_date.weekday() >= 5
    quota_df = rows_counting_toward_quota(all_leave_df)
    if not isinstance(quota_df, pd.DataFrame) or quota_df.empty:
        co_count = ps_count = 0
    else:
        d = quota_df.copy()
        if not {"Ngày", "Lý do nghỉ"}.issubset(d.columns):
            co_count = ps_count = 0
        else:
            d["__date"] = d["Ngày"].apply(_parse_date)
            d = d[d["__date"].eq(target_date)].copy()
            d["__group"] = d["Lý do nghỉ"].astype(str).apply(_reason_group)
            d["__days"] = pd.to_numeric(d.get("Số ngày tính", 0), errors="coerce").fillna(0.0)
            if "Tên nhân viên" in d.columns:
                d["__emp"] = d["Tên nhân viên"].astype(str).apply(norm)
            else:
                d["__emp"] = d.index.astype(str)
            co = d[(d["__group"] == "co_phep") & (d["__days"] > 0)]
            ps = d[d["__group"] == "phat_sinh"]
            co_count = int(co["__emp"].replace("", pd.NA).dropna().nunique())
            ps_count = int(ps["__emp"].replace("", pd.NA).dropna().nunique())

    if group == "co_phep":
        if is_zero_day_co_phep:
            return True, ""
        limit = weekend_limit if is_weekend else weekday_limit
        if co_count >= int(limit):
            return False, f"Ngày {target_date.strftime('%d/%m/%Y')} đã đủ {int(limit)} người CÓ phép."
        return True, ""
    if group == "phat_sinh":
        if is_weekend:
            return False, f"Ngày {target_date.strftime('%d/%m/%Y')} là cuối tuần (Thứ 7/Chủ nhật), không được đăng ký PHÁT SINH."
        if ps_count >= int(phat_sinh_limit):
            return False, f"Ngày {target_date.strftime('%d/%m/%Y')} đã đủ {int(phat_sinh_limit)} người PHÁT SINH."
    return True, ""


def validate_leave_registration_request_live(payload, live_df, credentials_df, runtime: Mapping[str, Any]):
    """Canonical live validation sequence shared by Streamlit and Web V2.

    Return contract is intentionally identical to V92.6.99:
    {ok, errors, warnings, accumulated_month}.
    """
    clean_reason = _call(runtime, "clean_leave_reason_display")
    is_annual = _call(runtime, "is_annual_leave_range_reason")
    is_long_sick = _call(runtime, "is_long_sick_leave_range_reason")
    normalize_leave = _call(runtime, "normalize_leave_reason")
    registration_window = _call(runtime, "employee_registration_window")
    validate_notice = _call(runtime, "validate_leave_registration_notice")
    validate_weekend = _call(runtime, "validate_monthly_weekend_registration_limit")
    is_video = _call(runtime, "is_video_leave_reason")
    quota_rows = _call(runtime, "leave_rows_counting_toward_quota")
    normalize_name = _call(runtime, "normalize_login_name")
    special_exempt = _call(runtime, "is_special_day_rule_exempt")
    exists = _call(runtime, "leave_exists_in_sources")
    validate_daily_employee = _call(runtime, "validate_daily_employee_registration_rule")
    validate_daily_quota = _call(runtime, "validate_daily_group_quota")
    progressive_reason_fn = _call(runtime, "get_progressive_penalty_reason")
    progressive_bonus = _call(runtime, "progressive_ordinal_and_bonus")

    result = {"ok": False, "errors": [], "warnings": [], "accumulated_month": 0.0}
    role = str(payload.get("role", "") or "").strip().lower()
    is_admin = role == "admin"
    employee = str(payload.get("employee", "") or "").strip()
    reason = clean_reason(payload.get("reason", ""))
    detail = str(payload.get("detail", "") or "").strip()
    is_annual_range_reason = is_annual(reason)
    is_long_sick_range_reason = is_long_sick(reason)

    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        result["errors"].append("Ngày đăng ký không hợp lệ.")
        return result
    if end_date < start_date:
        result["errors"].append("Ngày kết thúc phải lớn hơn hoặc bằng ngày bắt đầu.")
        return result
    range_days = (end_date - start_date).days + 1
    if is_annual_range_reason and range_days > 7:
        result["errors"].append("Phép năm chỉ được đăng ký tối đa 7 ngày liên tiếp cho mỗi lần.")
        return result

    if not employee or employee == "-- Chọn nhân viên --":
        result["errors"].append("Vui lòng chọn nhân viên cần nhập lịch nghỉ.")
    if not reason or reason == "-- Chọn lý do nghỉ --":
        result["errors"].append("Vui lòng chọn lý do nghỉ.")

    try:
        val_songay = float(payload.get("days", 0) or 0)
    except Exception:
        val_songay = 0.0
    val_phat = payload.get("penalty")
    requires_manual_penalty = bool(payload.get("requires_manual_penalty", False))
    is_loi_vi_pham = bool(payload.get("is_loi_vi_pham", False))
    is_nghi_ly_do_khac = bool(payload.get("is_nghi_ly_do_khac", False))
    is_zero_day_co_phep = bool(payload.get("is_zero_day_co_phep", False))
    default_phat = float(payload.get("default_penalty", 0) or 0)

    if is_loi_vi_pham:
        val_songay = 0.0
        if not detail:
            result["errors"].append("Chưa có Chi tiết vi phạm cho 'Lỗi vi phạm khác'.")
    if is_nghi_ly_do_khac and not detail:
        result["errors"].append("Bắt buộc nhập Chi tiết vi phạm / Ghi chú đối với 'Nghỉ lý do khác'.")
    if requires_manual_penalty and val_phat is None:
        result["errors"].append("Bắt buộc nhập Mức phạt vi phạm.")
    if result["errors"]:
        return result

    now_provider = runtime.get("now_vn")
    now_vn = now_provider() if callable(now_provider) else datetime.now(VN_TZ)
    today = now_vn.date()

    if not is_admin:
        reg_min, reg_max = registration_window(today)
        if start_date < reg_min or end_date < reg_min:
            result["errors"].append("Không được đăng ký lịch nghỉ cho ngày trong quá khứ.")
        if not is_long_sick_range_reason and (start_date > reg_max or end_date > reg_max):
            result["errors"].append(f"Chỉ được đăng ký lịch nghỉ đến hết {reg_max.strftime('%d/%m/%Y')}.")
        if result["errors"]:
            return result

    selected_dates = [start_date + timedelta(days=i) for i in range(range_days)]
    if not is_admin:
        for target_date in selected_dates:
            ok, msg = validate_notice(reason, target_date, role=role, now_vn=now_vn)
            if not ok:
                result["errors"].append(msg)
                return result

    employee_like_roles = set(_value(runtime, "employee_like_roles", EMPLOYEE_LIKE_ROLES) or EMPLOYEE_LIKE_ROLES)
    if role in employee_like_roles and not is_long_sick_range_reason:
        _, emp_max_date = registration_window(today)
        if end_date > emp_max_date:
            result["errors"].append(f"Nhân viên chỉ được đăng ký đến hết {emp_max_date.strftime('%d/%m/%Y')}.")
            return result

    source_df = live_df.copy() if isinstance(live_df, pd.DataFrame) else pd.DataFrame()
    norm_reason = normalize_leave(reason)

    if not is_admin and not (is_annual_range_reason or is_long_sick_range_reason):
        weekend_ok, weekend_msg = validate_weekend(source_df, employee, start_date, end_date, reason=reason, max_weekend_dates=2)
        if not weekend_ok:
            result["errors"].append(weekend_msg)
            return result

    is_video_leave = is_video(reason)
    num_days_selected = len(selected_dates)
    nv_info = pd.DataFrame()
    if isinstance(credentials_df, pd.DataFrame) and not credentials_df.empty and "Tên nhân viên" in credentials_df.columns:
        nv_info = credentials_df[
            credentials_df["Tên nhân viên"].astype(str).apply(normalize_name).eq(normalize_name(employee))
        ]

    def cred_limit(col):
        if nv_info.empty or col not in nv_info.columns:
            return 0.0
        value = pd.to_numeric(nv_info.iloc[0].get(col, 0), errors="coerce")
        return 0.0 if pd.isna(value) else float(value)

    limit_ps = cred_limit("Phát sinh tháng")
    limit_cp = cred_limit("Có phép tháng")
    limit_pn = cred_limit("Phép năm")

    if isinstance(source_df, pd.DataFrame) and not source_df.empty and "Tên nhân viên" in source_df.columns:
        user_hist = source_df[source_df["Tên nhân viên"].astype(str).apply(normalize_name).eq(normalize_name(employee))].copy()
    else:
        user_hist = pd.DataFrame(columns=["Ngày", "Lý do nghỉ", "Số ngày tính"])
    user_hist_quota = quota_rows(user_hist)

    for frame in (user_hist, user_hist_quota):
        if "Ngày" not in frame.columns:
            frame["Ngày"] = pd.Series(dtype="object")
        frame["Ngày_DT"] = pd.to_datetime(frame["Ngày"], errors="coerce", dayfirst=True)
        frame["M"] = frame["Ngày_DT"].dt.month
        frame["Y"] = frame["Ngày_DT"].dt.year
        if "Số ngày tính" in frame.columns:
            frame["Số ngày tính"] = pd.to_numeric(frame["Số ngày tính"], errors="coerce").fillna(0.0)

    curr_m, curr_y = start_date.month, start_date.year
    total_phep_required = val_songay * num_days_selected
    month_hist = user_hist_quota[(user_hist_quota["M"] == curr_m) & (user_hist_quota["Y"] == curr_y)]
    accumulated_month = (
        float(pd.to_numeric(month_hist.get("Số ngày tính", 0), errors="coerce").fillna(0).sum())
        if not month_hist.empty and "Số ngày tính" in month_hist.columns else 0.0
    )
    result["accumulated_month"] = accumulated_month

    if not is_admin and not is_video_leave:
        if "phép năm" in norm_reason:
            for annual_year in sorted({d.year for d in selected_dates}):
                annual_dates = [d for d in selected_dates if d.year == annual_year]
                annual_required = val_songay * len(annual_dates)
                year_hist = user_hist_quota[user_hist_quota["Y"] == annual_year]
                used_pn = (
                    float(pd.to_numeric(year_hist[year_hist["Lý do nghỉ"].astype(str).str.lower().str.contains("phép năm", na=False)].get("Số ngày tính", 0), errors="coerce").fillna(0).sum())
                    if not year_hist.empty and "Lý do nghỉ" in year_hist.columns else 0.0
                )
                if limit_pn > 0 and used_pn + annual_required > limit_pn:
                    result["errors"].append(
                        f"Vượt quá số ngày Phép năm. Cần {annual_required:g} ngày trong năm {annual_year}, quỹ còn {max(0.0, limit_pn - used_pn):g} ngày."
                    )
                    return result
        elif "phát sinh" in norm_reason:
            month_user = user_hist_quota[(user_hist_quota["M"] == curr_m) & (user_hist_quota["Y"] == curr_y)]
            used_ps = int(month_user["Lý do nghỉ"].astype(str).str.lower().str.contains("phát sinh", na=False).sum()) if not month_user.empty and "Lý do nghỉ" in month_user.columns else 0
            if limit_ps > 0 and used_ps >= limit_ps:
                result["errors"].append(f"Vượt giới hạn Phát sinh. Nhân viên này chỉ được đăng ký {limit_ps:g} lần phát sinh/tháng.")
                return result
        elif not is_nghi_ly_do_khac and not is_long_sick_range_reason and "không phép" not in norm_reason and val_songay > 0:
            month_user = user_hist_quota[(user_hist_quota["M"] == curr_m) & (user_hist_quota["Y"] == curr_y)]
            if not month_user.empty and "Lý do nghỉ" in month_user.columns:
                cp_mask = ~month_user["Lý do nghỉ"].astype(str).str.lower().str.contains("không phép|phát sinh|lý do khác", na=False, regex=True)
                used_cp = float(pd.to_numeric(month_user.loc[cp_mask, "Số ngày tính"], errors="coerce").fillna(0).sum())
            else:
                used_cp = 0.0
            if limit_cp > 0 and used_cp + total_phep_required > limit_cp:
                result["errors"].append(f"Vượt số ngày Có phép trong tháng. Nhân viên này chỉ được nghỉ tối đa {limit_cp:g} ngày/tháng.")
                return result

    special_day_exempt = special_exempt(role, reason)
    for target_date in selected_dates:
        if exists(source_df, target_date, employee, reason):
            result["errors"].append(f"{employee} đã có đúng lý do '{reason}' ngày {target_date.strftime('%d/%m/%Y')}.")
            return result
        if not is_admin:
            daily_ok, daily_msg = validate_daily_employee(source_df, target_date, employee, reason, val_songay)
            if not daily_ok:
                result["errors"].append(f"{employee} · {target_date.strftime('%d/%m/%Y')}: {daily_msg}")
                return result
            if not special_day_exempt and not is_nghi_ly_do_khac and "phép năm" not in norm_reason and not is_loi_vi_pham:
                quota_ok, quota_msg = validate_daily_quota(source_df, target_date, reason, is_zero_day_co_phep=is_zero_day_co_phep)
                if not quota_ok:
                    result["errors"].append(quota_msg)
                    return result

        progressive_reason = progressive_reason_fn(reason)
        if progressive_reason:
            ordinal, extra_penalty = progressive_bonus(source_df, target_date, reason)
            preview_total = default_phat + float(extra_penalty)
            result["warnings"].append(
                f"{target_date.strftime('%d/%m/%Y')}: Người Thứ {ordinal} {str(progressive_reason).lower()} · tổng phạt dự kiến {preview_total:,.0f} VNĐ."
            )

    result["ok"] = True
    return result

"""Web V2 API entrypoint using the same live validation sequence as Streamlit.

The base API keeps auth, PostgreSQL transaction, record_uid and Google Sheet
mirror code.  This wrapper replaces policy/validation helpers only, then routes
`_validate_and_prepare` through `vera_leave_registration_live_shared`.
"""
from __future__ import annotations

from datetime import datetime
import uuid

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import text

import vera_web_v2_api as _api
from vera_leave_registration_shared import (
    LeaveRuleError,
    day_allowed,
    field,
    group,
    is_annual,
    is_long_sick,
    is_video,
    norm,
    number,
    parse_first_number,
    progressive_key,
    reason_item,
    role_tokens,
    validate_registration_rule,
    weekday_label,
)
from vera_leave_registration_live_shared import (
    clean_display,
    employee_registration_window,
    is_annual_reason,
    is_long_sick_reason,
    is_special_day_rule_exempt,
    is_video_reason,
    leave_exists,
    monthly_weekend_registration_limit,
    normalize_reason,
    progressive_ordinal_and_bonus,
    progressive_penalty_reason,
    rows_counting_toward_quota,
    validate_leave_registration_request_live,
)
from vera_progressive_penalty import (
    applies as progressive_applies,
    bonus as progressive_bonus_amount,
    load_weekend_unpaid_enabled,
)


def _reason_item(conn, reason: str) -> dict:
    try:
        return reason_item(_api._policy_rows(conn), reason)
    except LeaveRuleError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def _registration_rule(item: dict, role: str, target):
    try:
        return validate_registration_rule(item, role, target)
    except LeaveRuleError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def _policy_group(conn, reason: str) -> str:
    try:
        item = _reason_item(conn, reason)
        type_key = norm(item.get("leave_type", ""))
        if "khong phep" in type_key:
            return "khong_phep"
        if "phat sinh" in type_key:
            return "phat_sinh"
        if "co phep" in type_key:
            return "co_phep"
    except Exception:
        pass
    return group(reason)


def _live_leave_df(conn, exclude_record_uid: str = "") -> pd.DataFrame:
    rows = conn.execute(text("""
        SELECT leave_date, employee_name, leave_reason, calculated_days,
               accumulated_leave, penalty, detail, leave_type
        FROM leave_records
        WHERE (:uid = '' OR record_uid <> :uid)
        ORDER BY leave_date, id
    """), {"uid": str(exclude_record_uid or "")}).mappings().all()
    if not rows:
        return pd.DataFrame(columns=["Ngày", "Tên nhân viên", "Lý do nghỉ", "Số ngày tính"])
    return pd.DataFrame([
        {
            "Ngày": row["leave_date"],
            "Tên nhân viên": row["employee_name"],
            "Lý do nghỉ": row["leave_reason"],
            "Loại nghỉ": row["leave_type"],
            "Chi tiết": row["detail"],
            "Số ngày tính": float(row["calculated_days"] or 0),
            "Số ngày phép cộng dồn": float(row["accumulated_leave"] or 0),
            "Phạt vi phạm": float(row["penalty"] or 0),
        }
        for row in rows
    ])


def _daily_quota_config():
    # PostgreSQL is canonical so an Admin save on the Nội quy page takes
    # effect on the very next registration request. The old three-key Google
    # Config remains the fallback during the Web V2 migration.
    try:
        with _api._engine_instance().connect() as conn:
            return _api.__dict__["_daily_quota_config_base"](conn)
    except Exception:
        pass
    cfg = {"weekday_limit": 5, "weekend_limit": 3, "phat_sinh_limit": 2}
    try:
        ws = _api._google_client().open_by_key(_api.LEAVE_SHEET_ID).worksheet("Config")
        values = ws.get_all_values()
        start = 1 if values and len(values[0]) >= 2 and norm(values[0][0]) == "key" else 0
        for row in values[start:]:
            if len(row) < 2:
                continue
            key = str(row[0]).strip()
            if key not in cfg:
                continue
            try:
                cfg[key] = max(0, int(float(str(row[1]).replace(",", ".").strip())))
            except Exception:
                pass
    except Exception:
        # Same safe defaults used by the immutable Streamlit core.
        pass
    cfg["days"] = [
        {
            "weekday": weekday,
            "paid_limit": cfg["weekend_limit"] if weekday >= 6 else cfg["weekday_limit"],
            "generated_limit": 0 if weekday >= 6 else cfg["phat_sinh_limit"],
        }
        for weekday in range(1, 8)
    ]
    return cfg


def _api_daily_quota_config(_conn):
    """Keep the read-only daily table on the same live quota as validation."""
    return _daily_quota_config()


_api._daily_quota_config_base = _api._daily_quota_config
_api._daily_quota_config = _api_daily_quota_config


def _daily_employee_rule(conn, df_sources, target_date, employee, reason, new_days):
    try:
        new_days = float(new_days or 0)
    except Exception:
        new_days = 0.0
    if not any(abs(new_days - x) < 1e-9 for x in (0.0, 0.5, 1.0)):
        return False, "Số ngày tính trong 1 ngày chỉ được phép là 0, 0.5 hoặc 1."
    if not isinstance(df_sources, pd.DataFrame) or df_sources.empty:
        return True, ""
    if not {"Ngày", "Tên nhân viên", "Lý do nghỉ"}.issubset(df_sources.columns):
        return True, ""
    d = df_sources.copy()
    d["__date"] = pd.to_datetime(d["Ngày"], errors="coerce", dayfirst=True).dt.date
    d["__emp"] = d["Tên nhân viên"].astype(str).apply(norm)
    d = d[(d["__date"] == target_date) & d["__emp"].eq(norm(employee))].copy()
    if d.empty:
        return True, ""
    if new_days > 0:
        days = pd.to_numeric(d.get("Số ngày tính", 0), errors="coerce").fillna(0.0)
        positive = d[days > 0]
        if not positive.empty:
            desc = [
                f"{clean_display(r.get('Lý do nghỉ',''))} ({float(r.get('Số ngày tính',0) or 0):g} ngày)"
                for _, r in positive.iterrows()
            ]
            return False, (
                "Trong cùng 1 ngày, mỗi nhân viên chỉ được có 1 dòng có Số ngày tính > 0. "
                "Không cho phép 0.5 + 0.5 = 1. "
                f"Đã có: {', '.join(desc)}."
            )
    new_group = _policy_group(conn, reason)
    if new_group:
        existing_groups = d["Lý do nghỉ"].astype(str).apply(lambda x: _policy_group(conn, x))
        same = d[existing_groups.eq(new_group)]
        if not same.empty:
            labels = {"co_phep": "CÓ phép", "khong_phep": "KHÔNG phép", "phat_sinh": "PHÁT SINH"}
            old = [clean_display(x) for x in same["Lý do nghỉ"].astype(str).tolist() if clean_display(x)]
            return False, (
                f"Trong cùng 1 ngày, một nhân viên không được có 2 lần {labels.get(new_group, new_group)}. "
                f"Đã có: {', '.join(old)}."
            )
    return True, ""


def _daily_group_quota(conn, all_leave_df, target_date, reason, is_zero_day_co_phep=False):
    cfg = _daily_quota_config()
    group_now = _policy_group(conn, reason)
    day_quota = cfg["days"][target_date.weekday()]
    d = rows_counting_toward_quota(all_leave_df)
    co_count = ps_count = 0
    if isinstance(d, pd.DataFrame) and not d.empty and {"Ngày", "Lý do nghỉ"}.issubset(d.columns):
        d = d.copy()
        d["__date"] = pd.to_datetime(d["Ngày"], errors="coerce", dayfirst=True).dt.date
        d = d[d["__date"].eq(target_date)].copy()
        d["__group"] = d["Lý do nghỉ"].astype(str).apply(lambda x: _policy_group(conn, x))
        d["__days"] = pd.to_numeric(d.get("Số ngày tính", 0), errors="coerce").fillna(0.0)
        d["__emp"] = d["Tên nhân viên"].astype(str).apply(norm) if "Tên nhân viên" in d.columns else d.index.astype(str)
        co = d[(d["__group"] == "co_phep") & (d["__days"] > 0)]
        ps = d[d["__group"] == "phat_sinh"]
        co_count = int(co["__emp"].replace("", pd.NA).dropna().nunique())
        ps_count = int(ps["__emp"].replace("", pd.NA).dropna().nunique())

    if group_now == "co_phep":
        if is_zero_day_co_phep:
            return True, ""
        limit = int(day_quota["paid_limit"])
        if co_count >= limit:
            return False, f"Ngày {target_date.strftime('%d/%m/%Y')} đã đủ {limit} người CÓ phép."
        return True, ""
    if group_now == "phat_sinh":
        limit = int(day_quota["generated_limit"])
        if limit <= 0:
            return False, f"Ngày {target_date.strftime('%d/%m/%Y')} không được đăng ký PHÁT SINH theo Nội quy."
        if ps_count >= limit:
            return False, f"Ngày {target_date.strftime('%d/%m/%Y')} đã đủ {limit} người PHÁT SINH."
    return True, ""


def _special_exempt(role, reason):
    key = norm(reason)
    if role == "leader" and "leader" in key and "chinh sach" in key:
        return True
    return is_special_day_rule_exempt(role, reason)


def _validate_and_prepare(
    conn,
    body,
    ident,
    *,
    exclude_record_uid="",
    skip_registration_timing=False,
    record_uid="",
    existing_ordinal=None,
    allow_inactive_employee=False,
):
    employee = body.employee_name.strip()
    role = str(ident.role or "").strip().lower()
    employee_like = {"nhanvien", "leader", "locker", "tapvu"}
    if role in employee_like and norm(employee) != norm(ident.employee_username):
        raise HTTPException(403, "Tài khoản hiện tại chỉ được đăng ký lịch nghỉ của chính mình.")

    emp = conn.execute(text("""
        SELECT username, monthly_generated, monthly_leave, annual_leave
        FROM employees
        WHERE lower(btrim(username))=lower(btrim(:u))
          AND (
            CAST(:allow_inactive AS boolean)
            OR (
              COALESCE(login_locked,false)=false
              AND COALESCE(payload->>'Trạng thái làm việc', payload->>'employment_status', 'Đang làm việc') = 'Đang làm việc'
            )
          )
        LIMIT 1
    """), {"u": employee, "allow_inactive": bool(allow_inactive_employee)}).mappings().first()
    if not emp:
        raise HTTPException(400, "Không tìm thấy nhân viên đang hoạt động.")
    employee = emp["username"]

    item = _reason_item(conn, body.leave_reason)
    base_penalty = float(body.manual_penalty) if item["requires_manual_penalty"] and body.manual_penalty is not None else float(item["penalty"])
    live_df = _live_leave_df(conn, exclude_record_uid=exclude_record_uid)
    weekend_unpaid_enabled = load_weekend_unpaid_enabled(conn)
    credentials_df = pd.DataFrame([{
        "Tên nhân viên": employee,
        "Phát sinh tháng": float(emp["monthly_generated"] or 0),
        "Có phép tháng": float(emp["monthly_leave"] or 0),
        "Phép năm": float(emp["annual_leave"] or 0),
    }])

    def validate_notice(reason, target_date, role=None, now_vn=None):
        if skip_registration_timing:
            return True, ""
        try:
            validate_registration_rule(_reason_item(conn, reason), str(role or ""), target_date, now=now_vn)
            return True, ""
        except LeaveRuleError as exc:
            return False, exc.message
        except HTTPException as exc:
            return False, str(exc.detail)

    def progressive_for_request(df_sources, target_date, reason):
        return progressive_ordinal_and_bonus(
            df_sources,
            target_date,
            reason,
            weekend_unpaid_enabled=weekend_unpaid_enabled,
        )

    runtime = {
        "clean_leave_reason_display": clean_display,
        "is_annual_leave_range_reason": is_annual_reason,
        "is_long_sick_leave_range_reason": is_long_sick_reason,
        "normalize_leave_reason": normalize_reason,
        "employee_registration_window": employee_registration_window,
        "validate_leave_registration_notice": validate_notice,
        "employee_like_roles": employee_like,
        "validate_monthly_weekend_registration_limit": monthly_weekend_registration_limit,
        "is_video_leave_reason": is_video_reason,
        "leave_rows_counting_toward_quota": rows_counting_toward_quota,
        "normalize_login_name": norm,
        "is_special_day_rule_exempt": _special_exempt,
        "leave_exists_in_sources": leave_exists,
        "validate_daily_employee_registration_rule": lambda df, d, e, r, days: _daily_employee_rule(conn, df, d, e, r, days),
        "validate_daily_group_quota": lambda df, d, r, is_zero_day_co_phep=False: _daily_group_quota(conn, df, d, r, is_zero_day_co_phep),
        "get_progressive_penalty_reason": progressive_penalty_reason,
        "progressive_ordinal_and_bonus": progressive_for_request,
        "now_vn": lambda: datetime.now(_api.VN_TZ),
    }
    reason_key = norm(item["name"])
    is_zero_day_co_phep = _policy_group(conn, item["name"]) == "co_phep" and abs(float(item["days"] or 0)) < 1e-9
    payload = {
        "role": role,
        "start_date": body.leave_date,
        "end_date": body.leave_date,
        "employee": employee,
        "reason": item["name"],
        "detail": body.detail.strip(),
        "days": float(item["days"] or 0),
        "penalty": body.manual_penalty if item["requires_manual_penalty"] else float(item["penalty"]),
        "requires_manual_penalty": bool(item["requires_manual_penalty"]),
        "is_loi_vi_pham": reason_key == norm("Lỗi vi phạm khác"),
        "is_nghi_ly_do_khac": reason_key == norm("Nghỉ lý do khác"),
        "is_zero_day_co_phep": is_zero_day_co_phep,
        "default_penalty": base_penalty,
    }
    validation = validate_leave_registration_request_live(payload, live_df, credentials_df, runtime)
    if not validation.get("ok"):
        message = str((validation.get("errors") or ["Đăng ký lịch nghỉ không hợp lệ."])[0])
        status = 409 if "đã có đúng lý do" in message.casefold() else 400
        raise HTTPException(status, message)

    days = float(item["days"] or 0)
    ordinal = None
    extra = 0.0
    progressive_reason = progressive_penalty_reason(item["name"])
    progressive_enabled = progressive_applies(
        body.leave_date,
        item["name"],
        weekend_unpaid_enabled=weekend_unpaid_enabled,
    )
    if progressive_reason and progressive_enabled:
        if existing_ordinal is not None:
            ordinal = int(existing_ordinal)
            extra = progressive_bonus_amount(
                ordinal,
                body.leave_date,
                item["name"],
                weekend_unpaid_enabled=weekend_unpaid_enabled,
            )
        else:
            ordinal, extra = progressive_for_request(live_df, body.leave_date, item["name"])

    accumulated = float(validation.get("accumulated_month", 0) or 0)
    if not (is_video_reason(item["name"]) or is_long_sick_reason(item["name"])):
        accumulated += days

    detail = body.detail.strip()
    if ordinal:
        prefix = f"Người Thứ {ordinal} {str(progressive_reason).lower()}"
        detail = f"{prefix} | {detail}" if detail else prefix

    now = datetime.now(_api.VN_TZ)
    record = {
        "record_uid": str(record_uid or uuid.uuid4()),
        "leave_date": body.leave_date,
        "employee_name": employee,
        "leave_reason": item["name"],
        "leave_type": item["leave_type"],
        "detail": detail,
        "calculated_days": days,
        "accumulated_leave": accumulated,
        "penalty": base_penalty + float(extra),
        "update_date": now.strftime("%d/%m/%Y"),
        "update_time": now.strftime("%H:%M:%S"),
        "updated_by": ident.employee_username,
        "weekday_label": weekday_label(body.leave_date),
    }
    return record, list(validation.get("warnings") or [])


# Shared pure policy helpers.
_api._norm = norm
_api._num = number
_api._field = field
_api._reason_item = _reason_item
_api._role_tokens = role_tokens
_api._weekday_label = weekday_label
_api._day_allowed = day_allowed
_api._parse_first_number = parse_first_number
_api._registration_rule = _registration_rule
_api._group = group
_api._is_video = is_video
_api._is_long_sick = is_long_sick
_api._is_annual = is_annual
_api._progressive_key = progressive_key

# Canonical live validation path.
_api._validate_and_prepare = _validate_and_prepare

app = _api.app

"""Date scope for manual revenue entry; stored with canonical permissions."""
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import text

POLICY_KEY = "revenue_entry_windows"


def effective_days(payload, role, username=""):
    if str(role).strip().lower() == "admin":
        return None
    policy = payload.get(POLICY_KEY, {})
    for scope, target in (("accounts", username), ("roles", role)):
        values = policy.get(scope, {})
        for key, value in values.items():
            if str(key).strip().casefold() == str(target).strip().casefold() and target:
                if value is None or (type(value) is int and 1 <= value <= 36500):
                    return value
                # Malformed explicit policy must never silently grant all dates.
                raise HTTPException(403, "Phạm vi nhập doanh thu chưa hợp lệ. Hãy liên hệ Admin.")
    return None  # Preserve existing grants until Admin configures a date scope.


def save_window(payload, scope, target, *, inherit, supplied, days, edited_features=None):
    if not supplied and not (scope == "account" and inherit):
        return
    if supplied and edited_features is not None and "revenue_entry_create" not in edited_features:
        raise HTTPException(400, "Phạm vi ngày phải đi cùng quyền Nhập doanh thu - chi phí.")
    policy = payload.setdefault(POLICY_KEY, {})
    values = policy.setdefault("accounts" if scope == "account" else "roles", {})
    for key in list(values):
        if key.strip().casefold() == target.strip().casefold():
            del values[key]
    if not (scope == "account" and inherit):
        values[target] = days


def entry_window(conn, ident, today: date):
    if str(ident.role).strip().lower() == "admin":
        days = None
    else:
        raw = conn.execute(text("""SELECT value_json FROM vera_app_setting
            WHERE category='authorization' AND setting_key='feature_permissions' LIMIT 1""")).scalar_one_or_none()
        days = effective_days(raw if isinstance(raw, dict) else {}, ident.role,
                              getattr(ident, "employee_username", ""))
    return {"days": days, "min_date": (today - timedelta(days=days - 1)).isoformat() if days else "",
            "max_date": today.isoformat() if days else "", "business_date": today.isoformat()}


def require_entry_date(conn, ident, transaction_date: date, today: date):
    window = entry_window(conn, ident, today)
    if window["days"] and not window["min_date"] <= transaction_date.isoformat() <= window["max_date"]:
        raise HTTPException(403, f"Bạn chỉ được nhập doanh thu - chi phí trong {window['days']} ngày gần nhất, gồm hôm nay (giờ Việt Nam).")
    return window

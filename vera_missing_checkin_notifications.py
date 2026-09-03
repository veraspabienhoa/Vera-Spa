"""Web Push alerts for scheduled employees missing FaceID after 15 minutes."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import hashlib
import json
import re
import unicodedata
from typing import Any

import pandas as pd
from sqlalchemy import text

import vera_auto_check as auto_check
import vera_auto_penalty_notifications as push
import vera_web_v2_department_attendance as department_attendance


RELEASE = "missing-scheduled-checkin-push-2026-09-03-v1"
CATEGORY = "missing_scheduled_checkin_alert"
THRESHOLD_MINUTES = 15
APP_URL = "https://veraspabienhoa.github.io/Vera-Spa/"
SCHEDULED_DEPARTMENTS = {"quanly", "locker", "letan"}


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").strip().lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    raw = raw.replace("đ", "d")
    return " ".join(raw.split())


def _clock(work_day: date, value: Any) -> datetime | None:
    match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(value or ""))
    if not match:
        return None
    hour, minute, second = (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))
    if hour > 23 or minute > 59 or second > 59:
        return None
    return datetime.combine(work_day, time(hour, minute, second))


def _faceid_employees(checkin_df: pd.DataFrame, employee_map: dict[str, str]) -> set[str]:
    checked: set[str] = set()
    if not isinstance(checkin_df, pd.DataFrame) or checkin_df.empty:
        return checked
    for _, row in checkin_df.iterrows():
        raw_name = ""
        for column in ("employeeInfo.Name", "EmployeeName", "employeeName", "Name", "FullName"):
            if column in row.index and str(row.get(column) or "").strip().casefold() not in {"", "nan", "none", "nat"}:
                raw_name = row.get(column)
                break
        has_event = False
        for column in (
            "MachineTimeStr", "MachineTimeCheckInStr", "CheckInTimeStr", "CheckInTime",
            "MachineTimeCheckOutStr", "CheckOutTimeStr", "CheckOutTime",
        ):
            if column in row.index and str(row.get(column) or "").strip().casefold() not in {"", "nan", "none", "nat"}:
                has_event = True
                break
        if not has_event:
            continue
        canonical = str(employee_map.get(_norm(raw_name), "") or raw_name or "").strip()
        if canonical:
            checked.add(_norm(canonical))
    return checked


def _scheduled_rows(conn, work_day: date) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text("""
        SELECT ws.employee_username,COALESCE(NULLIF(ws.employee_name,''),ws.employee_username) AS employee_name,
               lower(ws.department) AS department,ws.shift_code,
               COALESCE(NULLIF(ws.start_time,''),definition.start_time,'') AS start_time
        FROM vera_work_schedule ws
        LEFT JOIN vera_work_shift_definition definition
          ON definition.department=ws.department AND lower(definition.shift_code)=lower(ws.shift_code)
        WHERE ws.work_date=:work_day
          AND lower(ws.department) IN ('quanly','locker','letan')
          AND lower(btrim(ws.shift_code)) NOT IN ('nghỉ','nghi')
        ORDER BY ws.department,ws.employee_name,ws.employee_username
    """), {"work_day": work_day}).mappings().all()]


def _leave_adjustment(conn, work_day: date, employee: str, employee_name: str = "") -> tuple[bool, int]:
    """Return (off, allowed late minutes); unknown support fails closed."""
    rows = conn.execute(text("""
        SELECT employee_name,leave_reason,leave_type,calculated_days,source_sheet_id,updated_by
        FROM leave_records
        WHERE leave_date=:work_day
    """), {"work_day": work_day}).mappings().all()
    aliases = {_norm(employee), _norm(employee_name)} - {""}
    rows = [row for row in rows if _norm(row.get("employee_name")) in aliases]
    registered, baseline, _ = auto_check.registered_late_for_day(conn, work_day, employee)
    if not registered and _norm(employee_name) != _norm(employee):
        registered, baseline, _ = auto_check.registered_late_for_day(conn, work_day, employee_name)
    if registered:
        return False, max(0, int(baseline))
    support, allowance, _ = auto_check.late_support_for_day(conn, work_day, employee)
    if not support and _norm(employee_name) != _norm(employee):
        support, allowance, _ = auto_check.late_support_for_day(conn, work_day, employee_name)
    if support:
        return (True, 0) if allowance is None else (False, max(0, int(allowance)))
    for row in rows:
        if str(row.get("source_sheet_id") or "") == "postgres:auto_check":
            continue
        reason = _norm(row.get("leave_reason"))
        leave_type = _norm(row.get("leave_type"))
        try:
            days = float(row.get("calculated_days") or 0)
        except (TypeError, ValueError):
            days = 0
        if days >= 0.5 or "nghi" in reason or "co phep" in leave_type:
            return True, 0
    return False, 0


def _staff_subscriptions(conn) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text("""
        SELECT DISTINCT ON (s.subscription_id)
               s.subscription_id::text AS subscription_id,s.endpoint,s.p256dh,s.auth_secret
        FROM vera_v2_push_subscription s
        JOIN vera_v2_user_profile profile ON profile.auth_user_id=s.auth_user_id
        WHERE s.is_active=true AND profile.is_active=true
          AND lower(COALESCE(profile.role,'')) IN ('admin','quanly','letan')
        ORDER BY s.subscription_id,s.updated_at DESC
    """)).mappings().all()]


def _event_key(work_day: date, username: str, shift_code: str) -> str:
    raw = f"{work_day.isoformat()}|{_norm(username)}|{_norm(shift_code)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


def _already_sent(conn, key: str) -> bool:
    return bool(conn.execute(text("""
        SELECT 1 FROM vera_app_setting
        WHERE category=:category AND setting_key=:key
          AND COALESCE((value_json->>'sent')::boolean,false)=true
        LIMIT 1
    """), {"category": CATEGORY, "key": key}).scalar_one_or_none())


def _mark_sent(conn, key: str, details: dict[str, Any]) -> None:
    conn.execute(text("""
        INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
        VALUES (:category,:key,CAST(:value AS jsonb),'timesoft','system',1,NOW(),NOW())
        ON CONFLICT(category,setting_key) DO UPDATE SET
          value_json=EXCLUDED.value_json,source='timesoft',updated_by='system',
          revision=vera_app_setting.revision+1,updated_at=NOW()
    """), {"category": CATEGORY, "key": key, "value": json.dumps({"sent": True, **details}, ensure_ascii=False)})


def notify_missing_scheduled_checkins(
    engine, checkin_df: pd.DataFrame, work_day: date, employee_map: dict[str, str], now: datetime | None = None,
) -> dict[str, int]:
    """Notify at the first TimeSoft refresh after the 15-minute deadline.

    The function is deliberately independent from the Auto Check status. An
    empty TimeSoft result is treated as unavailable data, never mass absence.
    """
    result = {"scheduled": 0, "eligible": 0, "notified": 0, "sent": 0, "failed": 0, "skipped": 0}
    if not isinstance(checkin_df, pd.DataFrame) or checkin_df.empty:
        return result
    current = (now or datetime.now()).replace(tzinfo=None)
    checked = _faceid_employees(checkin_df, employee_map)
    with engine.connect() as conn:
        schedules = _scheduled_rows(conn, work_day)
    result["scheduled"] = len(schedules)
    for schedule in schedules:
        username = str(schedule.get("employee_username") or "").strip()
        employee_name = str(schedule.get("employee_name") or username).strip()
        department = str(schedule.get("department") or "").strip().lower()
        if not username or department not in SCHEDULED_DEPARTMENTS or _norm(username) in checked or _norm(employee_name) in checked:
            result["skipped"] += 1
            continue
        start = _clock(work_day, schedule.get("start_time"))
        if start is None:
            result["skipped"] += 1
            continue
        key = _event_key(work_day, username, str(schedule.get("shift_code") or ""))
        with engine.connect() as conn:
            if department in department_attendance.DEPARTMENTS and not department_attendance.control_for(conn, department)["notifications_enabled"]:
                result["skipped"] += 1
                continue
            if _already_sent(conn, key):
                result["skipped"] += 1
                continue
            off, adjustment = _leave_adjustment(conn, work_day, username, employee_name)
            if off:
                result["skipped"] += 1
                continue
            # Registered-late records return an absolute 17:00 baseline; other
            # support records return minutes added to the scheduled start.
            baseline = datetime.combine(work_day, time.min) + timedelta(minutes=adjustment) if adjustment >= 12 * 60 else start + timedelta(minutes=adjustment)
            deadline = baseline + timedelta(minutes=THRESHOLD_MINUTES)
            if current < deadline:
                result["skipped"] += 1
                continue
            subscriptions = _staff_subscriptions(conn)
            private_key = push._vault_secret(conn, "vera_v2_vapid_private_key")
            subject = push._vault_secret(conn, "vera_v2_vapid_subject") or APP_URL
        result["eligible"] += 1
        if not subscriptions or not private_key:
            result["failed"] += 1
            continue
        late_minutes = max(THRESHOLD_MINUTES, int((current - baseline).total_seconds() // 60))
        payload = {
            "kind": "missing-scheduled-checkin", "title": "VERA SPA · CHƯA CHECK MẶT",
            "body": f"{employee_name} có lịch {schedule.get('shift_code')} lúc {baseline.strftime('%H:%M')} nhưng sau {late_minutes} phút vẫn chưa có FaceID.",
            "url": APP_URL, "tag": f"vera-missing-checkin-{work_day.isoformat()}-{key}",
            "employee": username, "department": department, "deadline": deadline.isoformat(),
        }
        sent = 0
        for subscription in subscriptions:
            ok, status, error = push._send(subscription, payload, private_key, subject)
            sent += int(ok)
            result["sent"] += int(ok)
            result["failed"] += int(not ok)
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE vera_v2_push_subscription SET
                      is_active=CASE WHEN :inactive THEN false ELSE is_active END,
                      last_success_at=CASE WHEN :ok THEN NOW() ELSE last_success_at END,
                      failure_count=CASE WHEN :ok THEN 0 ELSE failure_count+1 END,
                      last_error=CASE WHEN :ok THEN NULL ELSE :error END,updated_at=NOW()
                    WHERE subscription_id=CAST(:subscription_id AS uuid)
                """), {"subscription_id": subscription["subscription_id"], "ok": ok,
                         "inactive": (not ok and status in {404, 410}), "error": error})
        if sent:
            with engine.begin() as conn:
                _mark_sent(conn, key, {
                    "work_date": work_day.isoformat(), "employee_username": username,
                    "employee_name": employee_name, "department": department,
                    "shift_code": schedule.get("shift_code"), "shift_start": baseline.strftime("%H:%M"),
                    "notified_at": current.isoformat(), "delivery_count": sent,
                })
            result["notified"] += 1
    return result

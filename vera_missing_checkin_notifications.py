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


RELEASE = "missing-scheduled-checkin-push-2026-09-08-v2"
CATEGORY = "missing_scheduled_checkin_alert"
THRESHOLD_MINUTES = 15
APP_URL = "https://app.veraspa.vn/"
REQUIRED_AUDIENCES = frozenset({"employee", "letan", "quanly", "admin"})
NAME_COLUMNS = ("employeeInfo.Name", "EmployeeName", "employeeName", "Name", "FullName")
EVENT_COLUMNS = (
    "MachineTimeStr", "MachineTimeCheckInStr", "CheckInTimeStr", "CheckInTime",
    "MachineTimeCheckOutStr", "CheckOutTimeStr", "CheckOutTime",
)
SHIFT_COLUMNS = ("WorkTimeName", "ShiftName", "Shift", "shift_code")
SHIFT_START_COLUMNS = ("StartWorkTime", "WorkTimeStart", "ShiftStartTime", "start_time")


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


def _alert_ready(*, has_leave: bool, has_faceid: bool, current: datetime, shift_start: datetime) -> bool:
    """All three IF conditions must be true before an alert is eligible."""
    return (
        not has_leave
        and not has_faceid
        and current > shift_start + timedelta(minutes=THRESHOLD_MINUTES)
    )


def _row_value(row: pd.Series, columns: tuple[str, ...]) -> Any:
    for column in columns:
        if column in row.index:
            value = row.get(column)
            if str(value or "").strip().casefold() not in {"", "nan", "none", "nat"}:
                return value
    return ""


def _faceid_employees(checkin_df: pd.DataFrame, employee_map: dict[str, str]) -> set[str]:
    checked: set[str] = set()
    if not isinstance(checkin_df, pd.DataFrame) or checkin_df.empty:
        return checked
    for _, row in checkin_df.iterrows():
        raw_name = _row_value(row, NAME_COLUMNS)
        if not _row_value(row, EVENT_COLUMNS):
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
          AND NULLIF(btrim(ws.shift_code),'') IS NOT NULL
          AND lower(btrim(ws.shift_code)) NOT IN ('nghỉ','nghi')
        ORDER BY ws.department,ws.employee_name,ws.employee_username
    """), {"work_day": work_day}).mappings().all()]


def _timesoft_scheduled_rows(
    checkin_df: pd.DataFrame, employee_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Read scheduled employees from TimeSoft summary rows, including KTV/Leader."""
    schedules: dict[str, dict[str, Any]] = {}
    if not isinstance(checkin_df, pd.DataFrame) or checkin_df.empty:
        return []
    for _, row in checkin_df.iterrows():
        raw_name = str(_row_value(row, NAME_COLUMNS) or "").strip()
        start_time = str(_row_value(row, SHIFT_START_COLUMNS) or "").strip()
        if not raw_name or not start_time:
            continue
        username = str(employee_map.get(_norm(raw_name), "") or raw_name).strip()
        key = _norm(username)
        if not key:
            continue
        schedules.setdefault(key, {
            "employee_username": username,
            "employee_name": raw_name,
            "department": "timesoft",
            "shift_code": str(_row_value(row, SHIFT_COLUMNS) or "Ca làm việc").strip(),
            "start_time": start_time,
        })
    return list(schedules.values())


def _merge_schedules(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge by employee; a manually assigned PostgreSQL schedule wins."""
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for row in group:
            key = _norm(row.get("employee_username") or row.get("employee_name"))
            if key:
                merged[key] = dict(row)
    return list(merged.values())


def _has_leave_schedule(conn, work_day: date, employee: str, employee_name: str = "") -> bool:
    """Any non-Auto-Check leave registration suppresses the absence alert."""
    rows = conn.execute(text("""
        SELECT employee_name,source_sheet_id
        FROM leave_records
        WHERE leave_date=:work_day
          AND COALESCE(source_sheet_id,'') <> 'postgres:auto_check'
    """), {"work_day": work_day}).mappings().all()
    aliases = {_norm(employee), _norm(employee_name)} - {""}
    return any(_norm(row.get("employee_name")) in aliases for row in rows)


def _audience_subscriptions(conn, employee: str, employee_name: str = "") -> list[dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT DISTINCT ON (s.subscription_id)
               s.subscription_id::text AS subscription_id,s.endpoint,s.p256dh,s.auth_secret,
               s.employee_username,lower(COALESCE(profile.role,'')) AS profile_role
        FROM vera_v2_push_subscription s
        LEFT JOIN vera_v2_user_profile profile ON profile.auth_user_id=s.auth_user_id
        WHERE s.is_active=true AND (
          lower(btrim(s.employee_username)) IN (lower(btrim(:employee)),lower(btrim(:employee_name)))
          OR (profile.is_active=true AND lower(COALESCE(profile.role,'')) IN ('admin','letan','quanly'))
        )
        ORDER BY s.subscription_id,s.updated_at DESC
    """), {"employee": employee, "employee_name": employee_name}).mappings().all()
    output = []
    aliases = {_norm(employee), _norm(employee_name)} - {""}
    for raw in rows:
        item = dict(raw)
        audiences = set()
        if _norm(item.get("employee_username")) in aliases:
            audiences.add("employee")
        if str(item.get("profile_role") or "").lower() in {"admin", "letan", "quanly"}:
            audiences.add(str(item["profile_role"]).lower())
        if audiences:
            item["audiences"] = sorted(audiences)
            output.append(item)
    return output


def _vault_secret(conn, name: str) -> str:
    value = conn.execute(text("""
        SELECT decrypted_secret FROM vault.decrypted_secrets
        WHERE name=:name LIMIT 1
    """), {"name": name}).scalar_one_or_none()
    return str(value or "").strip()


def _send(subscription: dict[str, Any], payload: dict[str, Any], private_key: str, subject: str):
    """Dedicated push transport; absence alerts do not import Auto Check code."""
    from pywebpush import WebPushException, webpush
    try:
        response = webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth_secret"]},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
            timeout=15,
        )
        return True, getattr(response, "status_code", None), ""
    except WebPushException as exc:
        return False, getattr(getattr(exc, "response", None), "status_code", None), str(exc)[:1000]
    except Exception as exc:
        return False, None, str(exc)[:1000]


def _event_key(work_day: date, username: str, shift_code: str) -> str:
    raw = f"{work_day.isoformat()}|{_norm(username)}|{_norm(shift_code)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


def _delivery_state(conn, key: str) -> dict[str, Any]:
    value = conn.execute(text("""
        SELECT value_json FROM vera_app_setting
        WHERE category=:category AND setting_key=:key LIMIT 1
    """), {"category": CATEGORY, "key": key}).scalar_one_or_none()
    state = dict(value) if isinstance(value, dict) else {}
    if state.get("sent") is True and not state.get("sent_audiences"):
        state["sent_audiences"] = sorted(REQUIRED_AUDIENCES)
    return state


def _mark_delivery_state(conn, key: str, details: dict[str, Any], sent_audiences: set[str]) -> None:
    completed = REQUIRED_AUDIENCES.issubset(sent_audiences)
    value = {
        "sent": completed,
        "sent_audiences": sorted(sent_audiences),
        "required_audiences": sorted(REQUIRED_AUDIENCES),
        **details,
    }
    conn.execute(text("""
        INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
        VALUES (:category,:key,CAST(:value AS jsonb),'timesoft','system',1,NOW(),NOW())
        ON CONFLICT(category,setting_key) DO UPDATE SET
          value_json=EXCLUDED.value_json,source='timesoft',updated_by='system',
          revision=vera_app_setting.revision+1,updated_at=NOW()
    """), {"category": CATEGORY, "key": key, "value": json.dumps(value, ensure_ascii=False)})


def notify_missing_scheduled_checkins(
    engine, checkin_df: pd.DataFrame, work_day: date, employee_map: dict[str, str], now: datetime | None = None,
) -> dict[str, int]:
    """Notify at the first TimeSoft refresh after the 15-minute deadline.

    The decision uses only work schedules, leave registrations and raw FaceID.
    It never reads Auto Check state/events. An empty TimeSoft result is treated
    as unavailable data, never mass absence.
    """
    result = {"scheduled": 0, "eligible": 0, "notified": 0, "sent": 0, "failed": 0, "skipped": 0}
    if not isinstance(checkin_df, pd.DataFrame) or checkin_df.empty:
        return result
    current = (now or datetime.now()).replace(tzinfo=None)
    checked = _faceid_employees(checkin_df, employee_map)
    timesoft_schedules = _timesoft_scheduled_rows(checkin_df, employee_map)
    with engine.connect() as conn:
        database_schedules = _scheduled_rows(conn, work_day)
    schedules = _merge_schedules(timesoft_schedules, database_schedules)
    result["scheduled"] = len(schedules)
    for schedule in schedules:
        username = str(schedule.get("employee_username") or "").strip()
        employee_name = str(schedule.get("employee_name") or username).strip()
        department = str(schedule.get("department") or "").strip().lower()
        if not username:
            result["skipped"] += 1
            continue
        start = _clock(work_day, schedule.get("start_time"))
        if start is None:
            result["skipped"] += 1
            continue
        key = _event_key(work_day, username, str(schedule.get("shift_code") or ""))
        with engine.connect() as conn:
            state = _delivery_state(conn, key)
            sent_audiences = set(state.get("sent_audiences") or [])
            if REQUIRED_AUDIENCES.issubset(sent_audiences):
                result["skipped"] += 1
                continue
            has_leave = _has_leave_schedule(conn, work_day, username, employee_name)
            deadline = start + timedelta(minutes=THRESHOLD_MINUTES)
            has_faceid = _norm(username) in checked or _norm(employee_name) in checked
            if not _alert_ready(
                has_leave=has_leave,
                has_faceid=has_faceid,
                current=current,
                shift_start=start,
            ):
                result["skipped"] += 1
                continue
            subscriptions = _audience_subscriptions(conn, username, employee_name)
            private_key = _vault_secret(conn, "vera_v2_vapid_private_key")
            subject = _vault_secret(conn, "vera_v2_vapid_subject") or APP_URL
        result["eligible"] += 1
        pending_audiences = REQUIRED_AUDIENCES - sent_audiences
        if not private_key:
            result["failed"] += len(pending_audiences)
            continue
        late_minutes = max(THRESHOLD_MINUTES + 1, int((current - start).total_seconds() // 60))
        payload = {
            "kind": "missing-scheduled-checkin", "title": "VERA SPA · VẮNG MẶT / ĐI MUỘN",
            "body": f"{employee_name} có lịch {schedule.get('shift_code')} lúc {start.strftime('%H:%M')} nhưng sau {late_minutes} phút vẫn chưa có FaceID và không có lịch xin nghỉ.",
            "url": APP_URL, "tag": f"vera-missing-checkin-{work_day.isoformat()}-{key}",
            "employee": username, "department": department, "deadline": deadline.isoformat(),
        }
        sent = 0
        for subscription in subscriptions:
            target_audiences = set(subscription.get("audiences") or []) & pending_audiences
            if not target_audiences:
                continue
            ok, status, error = _send(subscription, payload, private_key, subject)
            sent += int(ok)
            result["sent"] += int(ok)
            result["failed"] += int(not ok)
            if ok:
                sent_audiences.update(target_audiences)
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
        covered_audiences = set().union(*(set(item.get("audiences") or []) for item in subscriptions)) if subscriptions else set()
        result["failed"] += len(pending_audiences - covered_audiences)
        if sent:
            with engine.begin() as conn:
                _mark_delivery_state(conn, key, {
                    "work_date": work_day.isoformat(), "employee_username": username,
                    "employee_name": employee_name, "department": department,
                    "shift_code": schedule.get("shift_code"), "shift_start": start.strftime("%H:%M"),
                    "notified_at": current.isoformat(),
                    "delivery_count": int(state.get("delivery_count") or 0) + sent,
                }, sent_audiences)
        if REQUIRED_AUDIENCES.issubset(sent_audiences):
            result["notified"] += 1
    return result

"""Dynamic mid-shift break deadlines, TourVera fallback and persistent alerts.

Before any live reminder/overdue decision, Web V2 asks the production TimeSoft
refresh layer to update today's FaceID dataset in PostgreSQL. If TimeSoft cannot
be refreshed and the PostgreSQL snapshot is stale, active alerts fail closed.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import hashlib
import json
import re
import time as time_module
import unicodedata
from typing import Any, Callable

from fastapi import Depends
from sqlalchemy import text

import vera_web_v2_people as people
import vera_web_v2_snapshot as snapshot
import vera_web_v2_timesoft_live_refresh as timesoft_live


RELEASE = "attendance-break-alerts-2026-09-01-v3-live-timesoft"
REMINDER_SECONDS = 15 * 60
DEFAULT_BREAK_MINUTES = 90
TIMESOFT_MAX_STALE_SECONDS = 90
MANAGEMENT_ROLES = {"admin", "quanly", "letan"}
EMPLOYEE_ROLES = {"nhanvien", "leader"}
APP_URL = "https://veraspabienhoa.github.io/Vera-Spa/"


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").strip().lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    raw = raw.replace("đ", "d")
    raw = re.sub(r"\s*\*+\s*$", "", raw)
    return " ".join(raw.split())


def _parse_clock(value: Any, work_day: date) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, time):
        return datetime.combine(work_day, value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if 0 <= number < 1:
            seconds = int(round(number * 86400)) % 86400
            return datetime.combine(work_day, time(seconds // 3600, (seconds % 3600) // 60, seconds % 60))
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in (
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%H:%M:%S", "%H:%M",
    ):
        try:
            parsed = datetime.strptime(raw, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=work_day.year, month=work_day.month, day=work_day.day)
            return parsed
        except ValueError:
            continue
    try:
        number = float(raw.replace(",", "."))
    except ValueError:
        return None
    if 0 <= number < 1:
        seconds = int(round(number * 86400)) % 86400
        return datetime.combine(work_day, time(seconds // 3600, (seconds % 3600) // 60, seconds % 60))
    return None


def _timesoft_freshness(conn) -> dict[str, Any]:
    row = conn.execute(text("""
        SELECT updated_at,
               GREATEST(0, EXTRACT(EPOCH FROM (NOW() - updated_at))) AS age_seconds
        FROM vera_dataset_cache
        WHERE dataset_key='timesoft_employee_checkin_today'
        LIMIT 1
    """)).mappings().first()
    if not row:
        return {"fresh": False, "age_seconds": None, "updated_at": ""}
    try:
        age = max(0, int(float(row.get("age_seconds") or 0)))
    except Exception:
        age = TIMESOFT_MAX_STALE_SECONDS + 1
    updated_at = row.get("updated_at")
    return {
        "fresh": age <= TIMESOFT_MAX_STALE_SECONDS,
        "age_seconds": age,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at or ""),
    }


def _tour_snapshot() -> tuple[list[str], list[dict[str, Any]]]:
    with people._tour_lock:
        expired = time_module.monotonic() - float(people._tour_cache.get("loaded_at") or 0) > people.TOUR_CACHE_SECONDS
        if not people._tour_cache.get("records") or expired:
            try:
                columns, records, source_updated_at = people._download_tour()
            except Exception:
                columns = list(people._tour_cache.get("columns") or [])
                records = list(people._tour_cache.get("records") or [])
                return columns, records
            people._tour_cache.update({
                "loaded_at": time_module.monotonic(), "columns": columns,
                "records": records, "source_updated_at": source_updated_at,
            })
        return list(people._tour_cache.get("columns") or []), list(people._tour_cache.get("records") or [])


def _employee_aliases(conn) -> dict[str, str]:
    rows = conn.execute(text("""
        SELECT username, COALESCE(full_name,'') AS full_name
        FROM employees
        WHERE lower(COALESCE(role,'')) IN ('nhanvien','leader')
          AND COALESCE(payload->>'__deleted','false') <> 'true'
    """)).mappings().all()
    aliases: dict[str, str] = {}
    for row in rows:
        username = str(row.get("username") or "").strip()
        if not username:
            continue
        for value in (username, row.get("full_name")):
            key = _norm(value)
            if key:
                aliases[key] = username
    return aliases


def _tour_break_map(conn, work_day: date) -> dict[str, dict[str, Any]]:
    columns, records = _tour_snapshot()
    if len(columns) < 21:
        return {}
    name_column = people._find_column(columns, "Tên nhân viên")
    if not name_column:
        return {}
    break_column, break_out_column, break_in_column = columns[17], columns[18], columns[20]
    aliases = _employee_aliases(conn)
    output: dict[str, dict[str, Any]] = {}
    for row in records:
        if _norm(row.get(break_column)) != "break":
            continue
        username = aliases.get(_norm(row.get(name_column)))
        if not username:
            continue
        break_out = _parse_clock(row.get(break_out_column), work_day)
        break_in = _parse_clock(row.get(break_in_column), work_day)
        if break_out is None or break_out.time() < time(15, 0):
            continue
        if break_in is not None and break_in < break_out:
            break_in += timedelta(days=1)
        output[_norm(username)] = {"break_out": break_out, "break_in": break_in, "break_flag": str(row.get(break_column) or "")}
    return output


def _deadline_payload(*, work_day: date, break_out: datetime, break_in: datetime | None, planned_minutes: int, source: str) -> dict[str, Any]:
    planned = max(1, int(planned_minutes or DEFAULT_BREAK_MINUTES))
    deadline = break_out + timedelta(minutes=planned)
    actual = int(round((break_in - break_out).total_seconds() / 60)) if break_in else 0
    late = max(0, int((break_in - deadline).total_seconds() // 60)) if break_in else 0
    remaining = int((deadline - datetime.now()).total_seconds()) if not break_in else 0
    if break_in:
        status = f"Vào lại trễ {late} phút · phải vào lại lúc {deadline.strftime('%H:%M:%S')}" if late > 0 else f"Đã vào lại đúng giờ · hạn {deadline.strftime('%H:%M:%S')}"
        detail = f"Nghỉ giữa ca {break_out.strftime('%d/%m/%Y %H:%M:%S')} → {break_in.strftime('%d/%m/%Y %H:%M:%S')}"
    else:
        status = f"Đang nghỉ giữa ca · phải vào lại lúc {deadline.strftime('%H:%M:%S')}"
        detail = f"Bắt đầu nghỉ giữa ca {break_out.strftime('%d/%m/%Y %H:%M:%S')}"
    return {
        "break_started": True, "break_out": break_out.strftime("%H:%M:%S"),
        "break_in": break_in.strftime("%H:%M:%S") if break_in else "",
        "break_planned_minutes": planned, "break_actual_minutes": actual,
        "break_over_minutes": max(0, actual - planned), "break_return_late_minutes": late,
        "break_return_deadline": deadline.strftime("%H:%M:%S"),
        "break_return_deadline_iso": deadline.isoformat(), "break_remaining_seconds": remaining,
        "break_detail": detail, "break_status": status, "break_source": source,
    }


def _apply_tour_fallback(conn, records: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    today = datetime.now().date()
    if not (start <= today <= end):
        return records
    tour_map = _tour_break_map(conn, today)
    if not tour_map:
        return records
    output = []
    for raw in records:
        item = dict(raw)
        try:
            work_day = datetime.strptime(str(item.get("date") or ""), "%d/%m/%Y").date()
        except ValueError:
            output.append(item)
            continue
        if work_day != today or str(item.get("break_out") or "").strip():
            output.append(item)
            continue
        tour = tour_map.get(_norm(item.get("employee_name")))
        if not tour:
            output.append(item)
            continue
        planned = int(item.get("break_planned_minutes") or DEFAULT_BREAK_MINUTES)
        item.update(_deadline_payload(
            work_day=work_day, break_out=tour["break_out"], break_in=tour.get("break_in"),
            planned_minutes=planned, source="TourVera · R=Break, S=Giờ ra, U=Giờ vào",
        ))
        item["break_method"] = "Fallback TourVera sau khi TimeSoft chưa có giờ nghỉ"
        output.append(item)
    return output


def _event_key(item: dict[str, Any]) -> str:
    raw = "|".join((str(item.get("date") or ""), _norm(item.get("employee_name")), str(item.get("break_out") or "")))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _fact(item: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    try:
        work_day = datetime.strptime(str(item.get("date") or ""), "%d/%m/%Y").date()
    except ValueError:
        return None
    break_out = _parse_clock(item.get("break_out"), work_day)
    if break_out is None:
        return None
    break_in = _parse_clock(item.get("break_in"), work_day)
    planned = max(1, int(item.get("break_planned_minutes") or DEFAULT_BREAK_MINUTES))
    deadline = _parse_clock(item.get("break_return_deadline"), work_day) or (break_out + timedelta(minutes=planned))
    remaining = int((deadline - now).total_seconds()) if break_in is None else 0
    late = max(0, int((now - deadline).total_seconds())) if break_in is None else max(0, int((break_in - deadline).total_seconds()))
    return {
        "key": _event_key(item), "date": work_day,
        "employee": str(item.get("employee_name") or "").strip(),
        "break_out": break_out, "break_in": break_in, "deadline": deadline,
        "planned_minutes": planned, "remaining_seconds": remaining, "late_seconds": late,
        "source": str(item.get("break_source") or item.get("break_method") or "TimeSoft FaceID"),
    }


def _ensure_state(conn, key: str) -> dict[str, Any]:
    conn.execute(text("""
        INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
        VALUES ('attendance_break_alert',:key,'{}'::jsonb,'web_v2','system',1,NOW(),NOW())
        ON CONFLICT(category,setting_key) DO NOTHING
    """), {"key": key})
    value = conn.execute(text("""
        SELECT value_json FROM vera_app_setting
        WHERE category='attendance_break_alert' AND setting_key=:key FOR UPDATE
    """), {"key": key}).scalar_one_or_none()
    return dict(value) if isinstance(value, dict) else {}


def _save_state(conn, key: str, state: dict[str, Any]) -> None:
    conn.execute(text("""
        UPDATE vera_app_setting
        SET value_json=CAST(:value AS jsonb), source='web_v2', updated_by='system', revision=revision+1, updated_at=NOW()
        WHERE category='attendance_break_alert' AND setting_key=:key
    """), {"key": key, "value": json.dumps(state, ensure_ascii=False)})


def _employee_subscriptions(conn, username: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text("""
        SELECT subscription_id::text AS subscription_id, endpoint, p256dh, auth_secret
        FROM vera_v2_push_subscription
        WHERE is_active=true AND lower(btrim(employee_username))=lower(btrim(:username))
        ORDER BY updated_at DESC
    """), {"username": username}).mappings().all()]


def _management_subscriptions(conn) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text("""
        SELECT s.subscription_id::text AS subscription_id, s.endpoint, s.p256dh, s.auth_secret
        FROM vera_v2_push_subscription s
        JOIN vera_v2_user_profile p ON p.auth_user_id=s.auth_user_id
        WHERE s.is_active=true AND p.is_active=true
          AND lower(COALESCE(p.role,'')) IN ('admin','quanly','letan')
        ORDER BY s.updated_at DESC
    """)).mappings().all()]


def _update_delivery(engine_instance, result: dict[str, Any]) -> None:
    with engine_instance().begin() as conn:
        conn.execute(text("""
            UPDATE vera_v2_push_subscription SET
              is_active=CASE WHEN :inactive THEN false ELSE is_active END,
              last_success_at=CASE WHEN :ok THEN NOW() ELSE last_success_at END,
              failure_count=CASE WHEN :ok THEN 0 ELSE failure_count+1 END,
              last_error=CASE WHEN :ok THEN NULL ELSE :error END, updated_at=NOW()
            WHERE subscription_id=CAST(:subscription_id AS uuid)
        """), result)


def _send_payloads(api_module, engine_instance, deliveries: list[dict[str, Any]]) -> dict[str, int]:
    if not deliveries:
        return {"sent": 0, "failed": 0}
    with engine_instance().connect() as conn:
        private_key = api_module._vault_secret(conn, "vera_v2_vapid_private_key")
        subject = api_module._vault_secret(conn, "vera_v2_vapid_subject") or APP_URL
    if not private_key:
        return {"sent": 0, "failed": len(deliveries)}
    sent = failed = 0
    for delivery in deliveries:
        ok, status, error_text = api_module._send_web_push(delivery, private_key, subject)
        sent += int(ok)
        failed += int(not ok)
        _update_delivery(engine_instance, {
            "subscription_id": delivery["subscription_id"], "ok": ok,
            "inactive": (not ok and status in {404, 410}), "error": error_text,
        })
    return {"sent": sent, "failed": failed}


def _payload(fact: dict[str, Any], kind: str) -> dict[str, Any]:
    employee, start = fact["employee"], fact["break_out"].strftime("%H:%M:%S")
    deadline = fact["deadline"].strftime("%H:%M:%S")
    tag = f"vera-break-{fact['date'].isoformat()}-{fact['key']}"
    if kind == "reminder":
        remaining_minutes = max(1, (max(0, fact["remaining_seconds"]) + 59) // 60)
        return {"kind": "attendance-break-reminder", "title": "VERA SPA · Sắp hết giờ nghỉ giữa ca", "body": f"{employee}: còn {remaining_minutes} phút. Nghỉ từ {start}, phải FaceID vào lại lúc {deadline}.", "url": APP_URL, "tag": tag, "employee": employee, "deadline": fact["deadline"].isoformat()}
    if kind == "clear":
        return {"kind": "attendance-break-cleared", "tag": tag, "employee": employee, "url": APP_URL}
    late_minutes = max(1, (max(0, fact["late_seconds"]) + 59) // 60)
    return {"kind": "attendance-break-overdue", "title": "VERA SPA · NHÂN VIÊN VÀO LẠI TRỄ", "body": f"{employee}: nghỉ từ {start}, phải vào lại {deadline}, hiện đã trễ {late_minutes} phút. Nguồn: {fact['source']}.", "url": APP_URL, "tag": tag, "employee": employee, "deadline": fact["deadline"].isoformat()}


def _viewer_alerts(facts: list[dict[str, Any]], ident, now: datetime, source_fresh: bool) -> list[dict[str, Any]]:
    if not source_fresh:
        return []
    role = str(getattr(ident, "role", "") or "").strip().lower()
    username = str(getattr(ident, "employee_username", "") or "").strip()
    alerts = []
    for fact in facts:
        if fact["break_in"] is not None:
            continue
        remaining, audience, level = fact["remaining_seconds"], "", ""
        if role in MANAGEMENT_ROLES and remaining <= 0:
            audience, level = "staff", "overdue"
        elif role in EMPLOYEE_ROLES and _norm(fact["employee"]) == _norm(username) and remaining <= REMINDER_SECONDS:
            audience, level = "employee", ("overdue" if remaining <= 0 else "reminder")
        if audience:
            alerts.append({
                "key": fact["key"], "tag": f"vera-break-{fact['date'].isoformat()}-{fact['key']}",
                "audience": audience, "level": level, "employee": fact["employee"],
                "date": fact["date"].strftime("%d/%m/%Y"), "break_out": fact["break_out"].strftime("%H:%M:%S"),
                "deadline": fact["deadline"].strftime("%H:%M:%S"), "deadline_iso": fact["deadline"].isoformat(),
                "planned_minutes": fact["planned_minutes"], "remaining_seconds": remaining,
                "late_seconds": fact["late_seconds"], "source": fact["source"],
            })
    return sorted(alerts, key=lambda row: (row["deadline_iso"], _norm(row["employee"])))


def install_attendance_break_alerts(app, *, engine_instance: Callable[[], Any], api_module, current_identity, identity_type, vn_tz) -> None:
    if getattr(app.state, "attendance_break_alerts_installed", False):
        return
    original_records = snapshot._records

    def records_with_tour_fallback(conn, start: date, end: date):
        return _apply_tour_fallback(conn, original_records(conn, start, end), start, end)

    snapshot._records = records_with_tour_fallback

    @app.post("/v2/attendance/break-alerts/check")
    def check_break_alerts(ident: identity_type = Depends(current_identity)):
        now_aware = datetime.now(vn_tz)
        now, today = now_aware.replace(tzinfo=None), now_aware.date()
        # Refresh TimeSoft production before opening the DB transaction used to
        # calculate alerts. The live helper writes the same PostgreSQL dataset
        # consumed by snapshot._records.
        live_refresh = timesoft_live.refresh_today(force=False)
        deliveries: list[dict[str, Any]] = []
        with engine_instance().begin() as conn:
            freshness = _timesoft_freshness(conn)
            records = snapshot._records(conn, today, today)
            facts = [fact for item in records if (fact := _fact(item, now)) is not None]
            management_cache: list[dict[str, Any]] | None = None
            for fact in facts:
                state = _ensure_state(conn, fact["key"])
                remaining = fact["remaining_seconds"]
                if freshness["fresh"] and fact["break_in"] is None and 0 < remaining <= REMINDER_SECONDS and not state.get("reminder_sent_at"):
                    subscriptions = _employee_subscriptions(conn, fact["employee"])
                    if subscriptions:
                        deliveries.extend({**row, "payload": _payload(fact, "reminder")} for row in subscriptions)
                        state["reminder_sent_at"] = now_aware.isoformat()
                if freshness["fresh"] and fact["break_in"] is None and remaining <= 0 and not state.get("overdue_sent_at"):
                    if management_cache is None:
                        management_cache = _management_subscriptions(conn)
                    if management_cache:
                        deliveries.extend({**row, "payload": _payload(fact, "overdue")} for row in management_cache)
                        state["overdue_sent_at"] = now_aware.isoformat()
                if fact["break_in"] is not None and state.get("overdue_sent_at") and not state.get("cleared_at"):
                    if management_cache is None:
                        management_cache = _management_subscriptions(conn)
                    if management_cache:
                        deliveries.extend({**row, "payload": _payload(fact, "clear")} for row in management_cache)
                    state["cleared_at"] = now_aware.isoformat()
                state.update({
                    "employee": fact["employee"], "work_date": fact["date"].isoformat(),
                    "break_out": fact["break_out"].isoformat(), "deadline": fact["deadline"].isoformat(),
                    "break_in": fact["break_in"].isoformat() if fact["break_in"] else "", "source": fact["source"],
                    "timesoft_fresh": bool(freshness["fresh"]), "timesoft_age_seconds": freshness["age_seconds"],
                    "timesoft_live_refresh_ok": bool(live_refresh.get("ok")), "last_checked_at": now_aware.isoformat(),
                })
                _save_state(conn, fact["key"], state)
            viewer_alerts = _viewer_alerts(facts, ident, now, bool(freshness["fresh"]))

        delivery_result = _send_payloads(api_module, engine_instance, deliveries)
        return {
            "ok": True, "release": RELEASE, "alerts": viewer_alerts, "alert_count": len(viewer_alerts),
            "checked_at": now_aware.isoformat(), "reminder_before_minutes": 15,
            "source_priority": ["TimeSoft production live", "PostgreSQL", "TourVera R/S/U"],
            "timesoft_live_refresh": live_refresh, "timesoft_freshness": freshness,
            "alerts_suppressed_for_stale_timesoft": not bool(freshness["fresh"]), "push": delivery_result,
        }

    @app.get("/v2/attendance/break-alerts/health")
    def break_alerts_health():
        return {
            "ok": True, "release": RELEASE, "deadline_rule": "break_out + configured break minutes",
            "default_break_minutes": DEFAULT_BREAK_MINUTES, "reminder_before_minutes": 15,
            "timesoft_max_stale_seconds": TIMESOFT_MAX_STALE_SECONDS,
            "stale_policy": "suppress active reminder/overdue alerts until FaceID cache is fresh",
            "live_timesoft": timesoft_live.health(), "management_roles": sorted(MANAGEMENT_ROLES),
            "source_priority": ["TimeSoft production live", "PostgreSQL", "TourVera R=Break S=Giờ ra U=Giờ vào"],
        }

    app.state.attendance_break_alerts_installed = True
    app.state.attendance_break_alerts_release = RELEASE

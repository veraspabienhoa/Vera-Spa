"""Web Push alerts for scheduled employees missing FaceID after 15 minutes."""
from __future__ import annotations
from vera_notification_delivery import route_event as route_notification

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import re
import unicodedata
from typing import Any

import pandas as pd
from sqlalchemy import text
import vera_web_v2_notification_settings as notification_settings


RELEASE = "missing-scheduled-checkin-push-2026-09-08-v2"
CATEGORY = "missing_scheduled_checkin_alert"
THRESHOLD_MINUTES = 15
APP_URL = "https://app.veraspa.vn/"
REQUIRED_AUDIENCES = frozenset({"employee", "letan", "quanly", "admin"})
NAME_COLUMNS = ("employeeInfo.Name", "EmployeeName", "employeeName", "Name", "FullName")
EVENT_COLUMNS = (
    "MachineTimeStr", "MachineTimeCheckInStr", "CheckInTimeStr", "CheckInTime",
)


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


def _scheduled_rows(conn, work_day: date, employee_username: str = '') -> list[dict[str, Any]]:
    rows = [dict(row) for row in conn.execute(text("""
        SELECT ws.employee_username,COALESCE(NULLIF(ws.employee_name,''),ws.employee_username) AS employee_name,
               lower(ws.department) AS department,lower(btrim(e.role)) AS employee_role,ws.shift_code,
               COALESCE(NULLIF(ws.start_time,''),definition.start_time,'') AS start_time,
               COALESCE(NULLIF(ws.end_time,''),definition.end_time,'') AS end_time,
               COALESCE(ws.overtime_shift,'') AS overtime_shift,
               COALESCE(NULLIF(ws.overtime_start_time,''),ot.start_time,'') AS overtime_start_time,
               COALESCE(NULLIF(ws.overtime_end_time,''),ot.end_time,'') AS overtime_end_time
        FROM vera_work_schedule ws
        JOIN employees e ON lower(btrim(e.username))=lower(btrim(ws.employee_username))
        LEFT JOIN vera_work_shift_definition definition
          ON definition.department=ws.department AND lower(definition.shift_code)=lower(ws.shift_code)
        LEFT JOIN vera_work_shift_definition ot
          ON ot.department=ws.department AND ot.shift_code=
            CASE ws.overtime_shift WHEN 'TC Ca 1' THEN 'Ca 1' WHEN 'TC Ca 2' THEN 'Ca 2' END
        WHERE ws.work_date=:work_day
          AND (:employee_username='' OR lower(btrim(e.username))=:employee_username)
          AND COALESCE(e.payload->>'__deleted','false') <> 'true'
          AND COALESCE(NULLIF(e.payload->>'Trạng thái làm việc',''),
                       NULLIF(e.payload->>'employment_status',''),'Đang làm việc')='Đang làm việc'
        ORDER BY ws.department,ws.employee_name,ws.employee_username
    """), {"work_day": work_day, "employee_username": employee_username}).mappings().all()]
    from vera_schedule_attendance_window import attendance_window
    for row in rows:
        row["start_time"], row["end_time"] = attendance_window(row)
    return rows


def _manual_shift_overrides(conn, work_day):
    import vera_live_tour_resource_store as resources
    if resources.enabled():
        state, _, _ = resources.read(conn, collections={'employees'})
        workers = state.get('employees', [])
    else:
        workers = conn.execute(text("""SELECT value_json->'employees' FROM vera_app_setting
            WHERE category='live_tour' AND setting_key='state'""")).scalar_one_or_none() or []
    return {_norm(row.get('username') or row.get('name')): row.get('manual_shift', row.get('shift', ''))
            for row in workers if row.get('manual_shift_date') == work_day.isoformat()}


def _staff_scheduled_rows(conn, work_day, employee_username=''):
    """Include staff who have no TimeSoft row because they have not checked in."""
    from vera_shift_assignment import scheduled_shift
    from vera_web_v2_live_tour_roster import shift_label, display_shift_label, eligible
    rows = conn.execute(text("""
        SELECT username, full_name, role, payload, work_shift, rotation_cycle, shift_start_date,
          (SELECT value_json FROM vera_app_setting WHERE category='shift' AND setting_key='shift_definitions') AS shift_definitions
        FROM employees WHERE lower(btrim(role)) IN ('leader','nhanvien')
          AND (:employee_username='' OR lower(btrim(username))=:employee_username)
    """), {'employee_username': employee_username}).mappings().all()
    overrides = _manual_shift_overrides(conn, work_day)
    result = []
    for row in rows:
        if not eligible(row):
            continue
        definitions = row.get('shift_definitions') or []
        shift = overrides.get(_norm(row['username']), scheduled_shift(row, work_day))
        if not shift:
            continue
        active = [item for item in definitions if isinstance(item, dict)
                  and _norm(item.get('Bộ phận') or 'Nhân viên + Leader') == 'nhan vien + leader'
                  and _norm(item.get('Trạng thái')) != 'da xoa'
                  and shift_label(item.get('Tên ca'), definitions) == shift]
        exact = [item for item in active if _norm(row.get('work_shift')) in {_norm(item.get('Tên ca')), _norm(display_shift_label(item))}]
        starts = {str(item.get('Giờ bắt đầu') or '') for item in (exact or active)} - {''}
        if len(starts) != 1:
            continue  # Do not invent a start time for an ambiguous schedule.
        result.append({'employee_username': row['username'], 'employee_name': row.get('full_name') or row['username'],
                       'department': row['role'], 'employee_role': str(row['role']).strip().lower(), 'shift_code': shift, 'start_time': starts.pop()})
    return result


def current_missing_checkins(conn, ident, now, *, include_expiry=False):
    """Read current absence from fresh attendance data, without worker/push state.

    FaceGate uses its verified archive directly; legacy TimeSoft uses today's
    cache. Both reuse the caller connection without contacting a device.
    """
    viewer_role = str(getattr(ident, 'role', '')).strip().lower()
    view_team = viewer_role in {'admin', 'letan', 'quanly'}
    viewer_username = str(getattr(ident, 'employee_username', '') or '').strip().lower()
    if not view_team and (viewer_role not in {'leader', 'nhanvien', 'locker', 'tapvu', 'support'} or not viewer_username):
        return []
    zone = timezone(timedelta(hours=7))
    current = now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone)
    day = current.date()
    from vera_attendance_source import cache_key, source_for
    facegate = source_for(day) == 'facegate'
    eligible_users = None
    if facegate:
        from vera_facegate_runtime import missing_checkin_snapshot
        dataset = missing_checkin_snapshot(conn, day, now=current)
        if dataset is None:
            return []
        eligible_users = dataset['eligible_users']
        if not eligible_users:
            return []
    else:
        datasets = conn.execute(text("""
        SELECT payload,updated_at FROM vera_dataset_cache
        WHERE dataset_key IN (:today_key,:dated_key) AND source_version=:day
          AND updated_at BETWEEN :cutoff AND :current AND expires_at>:current
        ORDER BY updated_at DESC LIMIT 1
        """), {'today_key': cache_key(day, today_alias=True),
                'dated_key': cache_key(day),
                'day': day.isoformat(), 'cutoff': current-timedelta(minutes=10),
                'current': current}).mappings().all()
        if not datasets or not isinstance(datasets[0].get('payload'), list) or not datasets[0]['payload']:
            return []
        dataset = datasets[0]
    from vera_web_v2_attendance_v42 import _explicit_work_day, _generic_raw_punch, _parse_datetime, _work_day_for_row
    checked = set()
    for raw in dataset['payload']:
        if not isinstance(raw, dict):
            continue
        work_day = _explicit_work_day(raw)
        values = [value for name,value in raw.items()
                  if name.startswith(('MachineTimeCheckIn', 'LocalTimeCheckIn')) and name.endswith('Str')]
        values += [raw.get(name) for name in ('CheckInTimeStr', 'CheckInTime') if raw.get(name)]
        punches = [parsed for value in values if (parsed := _parse_datetime(value, work_day)) is not None]
        if not punches and not any(name.startswith(('MachineTime', 'LocalTime')) and 'CheckOut' in name for name in raw):
            punches = _generic_raw_punch(raw, work_day)
        # Match Live Tour's business-day boundary: yesterday's midnight exits,
        # future scans and checkout-only summaries cannot count as today's entry.
        if (work_day or _work_day_for_row(raw, punches)) != day:
            continue
        if any(p.date() == day and 3 <= p.hour < 23 and p <= current.replace(tzinfo=None) for p in punches):
            checked.update(_norm(raw.get(name)) for name in NAME_COLUMNS if raw.get(name))
    owner = '' if view_team else viewer_username
    schedules = _merge_schedules(_staff_scheduled_rows(conn, day, owner), _scheduled_rows(conn, day, owner))
    leave_rows = conn.execute(text("""SELECT employee_name,leave_reason FROM leave_records
        WHERE leave_date=:day AND COALESCE(source_sheet_id,'') <> 'postgres:auto_check'"""),
        {'day': day}).mappings().all()
    late = {_norm(row.get('employee_name')) for row in leave_rows if 'di tre' in _norm(row.get('leave_reason'))}
    leave = {_norm(row.get('employee_name')) for row in leave_rows if 'di tre' not in _norm(row.get('leave_reason'))}
    updated = dataset['updated_at']
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    expires = min(dataset.get('expires_at', updated.astimezone(zone)+timedelta(minutes=10)),
                  datetime.combine(day+timedelta(days=1), time.min, tzinfo=zone))
    result = []
    for row in schedules:
        employee_role = str(row.get('employee_role') or '').strip().lower()
        if employee_role in {'giamdoc', 'quanly'}:
            continue
        if viewer_role == 'letan' and employee_role not in {'leader', 'nhanvien', 'letan'}:
            continue
        username = str(row.get('employee_username') or '').strip()
        # Ownership uses the authenticated account name, never display-name or
        # accent-stripped matching which could expose another person's alert.
        if not view_team and username.lower() != viewer_username:
            continue
        if eligible_users is not None and username not in eligible_users:
            continue
        name = str(row.get('employee_name') or username)
        aliases = {_norm(username), _norm(name)} - {''}
        start = _clock(day, row.get('start_time'))
        if not username or not start or _norm(row.get('shift_code')) in {'', 'nghi'}:
            continue
        registered_late = bool(aliases & late)
        if registered_late:
            cutoff_hour = {'ca 1': 15, 'ca1': 15, 'ca 2': 17, 'ca2': 17}.get(_norm(row.get('shift_code')))
            if cutoff_hour is None or aliases & leave or aliases & checked or current.hour < cutoff_hour:
                continue
            start = datetime.combine(day, time(cutoff_hour))
        elif not _alert_ready(has_leave=bool(aliases & leave), has_faceid=bool(aliases & checked),
                              current=current.replace(tzinfo=None), shift_start=start):
            continue
        # A pre-cutoff archive cannot prove absence at the cutoff. Wait for a
        # completed sync past 15:00/17:00 (or the ordinary 15-minute threshold).
        decision_at = start if registered_late else start + timedelta(minutes=THRESHOLD_MINUTES)
        if facegate and updated.astimezone(zone) < decision_at.replace(tzinfo=zone):
            continue
        key = _event_key(day, username, str(row.get('shift_code') or ''))
        alert = {'key': key, 'tag': f'vera-missing-checkin-{day.isoformat()}-{key}',
                 'kind': 'missing-scheduled-checkin', 'employee': username,
                 'body': f"{username} · {row.get('shift_code')} lúc {start:%H:%M} · " + ("đã đăng ký đi trễ nhưng chưa có check-in." if registered_late else "chưa có check-in và chưa đăng ký nghỉ."),
                 'date': day.strftime('%d-%m-%Y')}
        if include_expiry:
            alert['expires_at'] = expires.isoformat()
        result.append(alert)
    return result


def viewer_missing_checkins(conn, ident, now, *, include_expiry=False):
    rows = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category=:category AND setting_key=:key"),
                        {'category': CATEGORY, 'key': f'current_alerts:{now.date().isoformat()}'}).mappings().all()
    data = (rows[0].get('value_json') or {}) if rows else {}
    if not isinstance(data, dict):
        return []
    try:
        checked = datetime.fromisoformat(data.get('checked_at', ''))
        if checked.tzinfo is not None:
            checked = checked.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
        age = (now.replace(tzinfo=None) - checked).total_seconds()
    except (TypeError, ValueError):
        return []
    if not 0 <= age <= 600 or data.get('work_date') != now.date().isoformat():
        return []
    role = str(getattr(ident, 'role', '')).lower()
    username = _norm(getattr(ident, 'employee_username', ''))
    alerts = [row for row in data.get('alerts', []) if isinstance(row, dict)
              and (role in {'admin', 'letan', 'quanly'} or username == _norm(row.get('employee')))]
    if include_expiry:
        expires = min(checked + timedelta(seconds=600), datetime.combine(now.date() + timedelta(days=1), time.min))
        return [{**row, 'expires_at': expires.replace(tzinfo=timezone(timedelta(hours=7))).isoformat()} for row in alerts]
    return alerts


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
    try:
        with engine.begin() as conn:
            if not notification_settings.is_enabled(conn, "missing_checkin"):
                result["skipped"] = 1
                return result
    except Exception:
        pass
    current = now or datetime.now(timezone(timedelta(hours=7)))
    if current.tzinfo is not None:
        current = current.astimezone(timezone(timedelta(hours=7)))
    current = current.replace(tzinfo=None)
    if current.date() != work_day:
        return result
    if not isinstance(checkin_df, pd.DataFrame) or checkin_df.empty:
        with engine.begin() as conn:
            _mark_delivery_state(conn, f'current_alerts:{work_day.isoformat()}',
                {'work_date': work_day.isoformat(), 'checked_at': current.isoformat(), 'alerts': []}, set())
        return result
    checked = _faceid_employees(checkin_df, employee_map)
    with engine.connect() as conn:
        database_schedules = _scheduled_rows(conn, work_day)
        staff_schedules = _staff_scheduled_rows(conn, work_day)
        from vera_attendance_source import source_for
        eligible_users = None
        if source_for(work_day) == 'facegate':
            from vera_facegate_runtime import alert_eligible_users
            eligible_users = alert_eligible_users(conn, work_day)
    schedules = _merge_schedules(staff_schedules, database_schedules)
    if eligible_users is not None:
        schedules = [s for s in schedules if s.get('employee_username') in eligible_users]
    visible_alerts = []
    result["scheduled"] = len(schedules)
    for schedule in schedules:
        username = str(schedule.get("employee_username") or "").strip()
        employee_name = str(schedule.get("employee_name") or username).strip()
        department = str(schedule.get("department") or "").strip().lower()
        if not username or _norm(schedule.get('shift_code')) in {'', 'nghi'}:
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
        result["eligible"] += 1
        pending_audiences = REQUIRED_AUDIENCES - sent_audiences
        late_minutes = max(THRESHOLD_MINUTES + 1, int((current - start).total_seconds() // 60))
        payload = {
            "kind": "missing-scheduled-checkin", "title": "VERA SPA · VẮNG MẶT / ĐI MUỘN",
            "body": f"{employee_name} có lịch {schedule.get('shift_code')} lúc {start.strftime('%H:%M')} nhưng sau {late_minutes} phút vẫn chưa có FaceID và không có lịch xin nghỉ.",
            "url": APP_URL, "tag": f"vera-missing-checkin-{work_day.isoformat()}-{key}",
            "employee": username, "department": department, "deadline": deadline.isoformat(),
        }
        # Current absence is independent of push routing and transport success.
        visible_alerts.append({**payload, 'key': key, 'audience': 'staff', 'level': 'overdue',
            'deadline_iso': deadline.isoformat(), 'date': work_day.strftime('%d-%m-%Y')})
        try:
            routed = route_notification(engine, 'missing_checkin', payload)
        except Exception:
            result['failed'] += 1
            continue
        if routed:
            result['notified'] += 1
            continue
        if not pending_audiences:
            result['skipped'] += 1
            continue
        try:
            with engine.connect() as conn:
                subscriptions = _audience_subscriptions(conn, username, employee_name)
                private_key = _vault_secret(conn, "vera_v2_vapid_private_key")
                subject = _vault_secret(conn, "vera_v2_vapid_subject") or APP_URL
        except Exception:
            result['failed'] += len(pending_audiences)
            continue
        if not private_key:
            result['failed'] += len(pending_audiences)
            continue
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
    with engine.begin() as conn:
        _mark_delivery_state(conn, f'current_alerts:{work_day.isoformat()}', {'work_date': work_day.isoformat(),
            'checked_at': current.isoformat(), 'alerts': visible_alerts}, set())
    return result

"""PostgreSQL-only Auto Check core shared by the background job and Web V2."""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

VN_TZ = timezone(timedelta(hours=7))
RELEASE = "auto-check-pg-v3-employee-notification"
DEFAULT_CONFIG = {
    "status": "RUNNING",
    "threshold_minutes": 5,
    "schedule_hours": [15, 20, 21],
    "midshift_hour": 21,
    "manual_run_requested": False,
}

REGISTERED_LATE_REASONS = {
    "di tre phat sinh",
    "di tre co phep",
    "di tre khong phep",
}
REGISTERED_LATE_BASELINE_MINUTES = 17 * 60


def _norm(value) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return " ".join(value.replace("đ", "d").replace("Đ", "D").casefold().split())


def _json(value, default):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except Exception:
        return default


def ensure_schema(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_auto_check_run (
            id bigserial PRIMARY KEY,
            trigger_type text NOT NULL DEFAULT 'scheduled',
            status text NOT NULL,
            started_at timestamptz NOT NULL DEFAULT NOW(),
            completed_at timestamptz,
            details jsonb NOT NULL DEFAULT '{}'::jsonb,
            error text
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_auto_check_event (
            id bigserial PRIMARY KEY,
            event_key text NOT NULL UNIQUE,
            work_date date NOT NULL,
            employee_name text NOT NULL,
            reason text NOT NULL,
            source text NOT NULL,
            minutes numeric NOT NULL DEFAULT 0,
            status text NOT NULL,
            detail text,
            leave_record_uid text,
            created_at timestamptz NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_auto_check_event_date ON vera_auto_check_event(work_date DESC, created_at DESC)"))
    conn.execute(text("""
        ALTER TABLE vera_auto_check_event
          ADD COLUMN IF NOT EXISTS employee_notify_claimed_at timestamptz,
          ADD COLUMN IF NOT EXISTS employee_notify_attempted_at timestamptz,
          ADD COLUMN IF NOT EXISTS employee_notified_at timestamptz DEFAULT NOW(),
          ADD COLUMN IF NOT EXISTS employee_notify_error text
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_auto_check_event_pending_notify
        ON vera_auto_check_event(created_at)
        WHERE status='added' AND employee_notified_at IS NULL
    """))


def load_config(conn) -> dict:
    ensure_schema(conn)
    row = conn.execute(text("""
        SELECT value_json FROM vera_app_setting
        WHERE category='auto_check' AND setting_key='config'
        LIMIT 1
    """)).scalar()
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(_json(row, {}))
    cfg["status"] = "PAUSED" if str(cfg.get("status", "")).upper() == "PAUSED" else "RUNNING"
    cfg["threshold_minutes"] = max(1, min(180, int(cfg.get("threshold_minutes", 5) or 5)))
    return cfg


def save_config(conn, updates: dict, actor: str) -> dict:
    cfg = load_config(conn)
    for key in ("status", "threshold_minutes", "manual_run_requested"):
        if key in updates:
            cfg[key] = updates[key]
    cfg["status"] = "PAUSED" if str(cfg.get("status", "")).upper() == "PAUSED" else "RUNNING"
    cfg["threshold_minutes"] = max(1, min(180, int(cfg.get("threshold_minutes", 5) or 5)))
    conn.execute(text("""
        INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
        VALUES ('auto_check','config',CAST(:value AS jsonb),'web_v2',:actor,1,NOW(),NOW())
        ON CONFLICT(category,setting_key) DO UPDATE SET
          value_json=EXCLUDED.value_json, source=EXCLUDED.source, updated_by=EXCLUDED.updated_by,
          revision=vera_app_setting.revision+1, updated_at=NOW()
    """), {"value": json.dumps(cfg, ensure_ascii=False), "actor": actor})
    return cfg


def load_catalog(conn) -> dict[str, dict]:
    values = conn.execute(text("""
        SELECT value_json FROM vera_app_setting
        WHERE (category='official_policy' AND setting_key='leave_rules')
           OR (category='leave_rules' AND setting_key='loai_nghi_snapshot_v2')
        ORDER BY CASE WHEN category='official_policy' THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
    """)).scalar()
    payload = _json(values, {})
    rows = payload.get("rows", payload.get("reasons", payload if isinstance(payload, list) else [])) if isinstance(payload, dict) else payload
    headers = payload.get("columns") or payload.get("headers") or [] if isinstance(payload, dict) else []
    if rows and not isinstance(rows[0], dict) and headers:
        rows = [dict(zip(headers, list(row) + [""] * max(0, len(headers) - len(row)))) for row in rows]
    out = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = next((str(row.get(k) or "").strip() for k in ("name", "reason", "Lý do nghỉ", "ly_do_nghi") if row.get(k)), "")
        if not name:
            continue
        def number(keys):
            raw = next((row.get(k) for k in keys if row.get(k) not in (None, "")), 0)
            if isinstance(raw, str):
                raw = re.sub(r"[^0-9,.-]", "", raw)
                if "," in raw and "." in raw:
                    raw = raw.replace(".", "").replace(",", ".")
                elif "," in raw:
                    raw = raw.replace(",", ".")
                elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", raw):
                    raw = raw.replace(".", "")
            try: return float(raw)
            except Exception: return 0.0
        out[_norm(name)] = {
            "name": name,
            "type": next((str(row.get(k) or "").strip() for k in ("type", "leave_type", "Loại nghỉ", "loai_nghi") if row.get(k)), "Vi phạm"),
            "days": number(("days", "calculated_days", "Số ngày tính", "Số ngày tính phép", "so_ngay_tinh")),
            "penalty": number(("penalty", "Phạt vi phạm", "phat_vi_pham")),
        }
    return out


def catalog_item(catalog: dict, name: str):
    return catalog.get(_norm(name))


def outside_reason(catalog: dict, minutes: float):
    candidates = ([
        "Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút",
        "Ra ngoài vào muộn dưới 30 phút",
    ] if minutes <= 30 else [
        "Ra ngoài vào muộn nhỏ hơn hoặc bằng 60 phút",
        "Ra ngoài vào muộn dưới 60 phút",
    ] if minutes <= 60 else [
        "Ra ngoài vào muộn nhỏ hơn hoặc bằng 120 phút",
        "Ra ngoài vào muộn dưới 120 phút",
    ] if minutes <= 120 else [
        "Ra ngoài vào muộn trên 120 phút",
        "Ra ngoài vào muộn từ 120 phút trở lên",
    ])
    return next((catalog_item(catalog, name) for name in candidates if catalog_item(catalog, name)), None)


def late_support_for_day(conn, work_date: date, employee: str) -> tuple[list[str], int | None, str]:
    """Return same-day support reasons and their late allowance.

    Unknown support wording is fail-closed: Auto Check skips the penalty instead
    of guessing. Known ``đi trễ N tiếng/giờ`` wording is converted to minutes.
    """
    rows = conn.execute(text("""
        SELECT employee_name, leave_reason
        FROM leave_records
        WHERE leave_date=:day
    """), {"day": work_date}).mappings().all()
    reasons = [str(row["leave_reason"] or "").strip() for row in rows
               if _norm(row["employee_name"]) == _norm(employee)
               and "ho tro" in _norm(row["leave_reason"])]
    if not reasons:
        return [], 0, ""
    matched = []
    unknown = []
    for reason in reasons:
        key = _norm(reason)
        match = re.search(r"di tre\s+(\d+(?:[.,]\d+)?)\s*(?:tieng|gio)", key)
        if match:
            matched.append((int(round(float(match.group(1).replace(",", ".")) * 60)), reason))
        else:
            unknown.append(reason)
    if unknown:
        return reasons, None, unknown[0]
    allowance, reason = max(matched, key=lambda item: item[0])
    return reasons, allowance, reason


def registered_late_for_day(conn, work_date: date, employee: str) -> tuple[list[str], int, str]:
    """Return a same-day registered late reason and its 17:00 baseline.

    These three registrations have historically moved the employee's standard
    check-in to 17:00 for that day. The frequent PostgreSQL penalty path must
    preserve the same rule instead of charging against the employee's normal
    shift start.
    """
    rows = conn.execute(text("""
        SELECT employee_name, leave_reason, source_sheet_id, updated_by
        FROM leave_records
        WHERE leave_date=:day
          AND COALESCE(source_sheet_id, '') <> 'postgres:auto_check'
    """), {"day": work_date}).mappings().all()
    reasons = [
        str(row["leave_reason"] or "").strip()
        for row in rows
        if _norm(row["employee_name"]) == _norm(employee)
        and _norm(row["leave_reason"]) in REGISTERED_LATE_REASONS
        and str(row.get("source_sheet_id", "") or "") != "postgres:auto_check"
        and not _norm(row.get("updated_by", "")).startswith("auto update")
    ]
    return (
        reasons,
        REGISTERED_LATE_BASELINE_MINUTES,
        reasons[0] if reasons else "",
    )


def revoke_auto_late_penalty(conn, *, work_date: date, employee: str, basis: str) -> int:
    """Remove only the direct PostgreSQL late penalty covered by a later rule."""
    deleted = conn.execute(text("""
        DELETE FROM leave_records
        WHERE source_sheet_id='postgres:auto_check'
          AND leave_date=:day
          AND lower(employee_name)=lower(:employee)
          AND lower(leave_reason)=lower(:reason)
        RETURNING record_uid
    """), {"day": work_date, "employee": employee, "reason": "Đi trễ không phép"}).scalars().all()
    if deleted:
        conn.execute(text("""
            UPDATE vera_auto_check_event
            SET status='revoked', leave_record_uid=NULL,
                detail=CONCAT(COALESCE(detail,''),' · Thu hồi vì có ',:basis)
            WHERE work_date=:day AND lower(employee_name)=lower(:employee)
              AND lower(reason)=lower(:reason) AND status='added'
        """), {"day": work_date, "employee": employee, "reason": "Đi trễ không phép", "basis": basis})
    return len(deleted)


def revoke_wrong_late_penalty(conn, *, work_date: date, employee: str, support_reason: str) -> int:
    """Remove only a PostgreSQL Auto Check late penalty covered by support."""
    return revoke_auto_late_penalty(
        conn,
        work_date=work_date,
        employee=employee,
        basis=support_reason,
    )


def start_run(conn, trigger_type="scheduled") -> int:
    ensure_schema(conn)
    return int(conn.execute(text("""
        INSERT INTO vera_auto_check_run(trigger_type,status) VALUES (:trigger,'running') RETURNING id
    """), {"trigger": trigger_type}).scalar_one())


def finish_run(conn, run_id: int, status: str, details=None, error="") -> None:
    conn.execute(text("""
        UPDATE vera_auto_check_run SET status=:status,completed_at=NOW(),details=CAST(:details AS jsonb),error=:error WHERE id=:id
    """), {"id": run_id, "status": status, "details": json.dumps(details or {}, ensure_ascii=False), "error": error or None})


def event_rows(conn, *, start: date | None = None, end: date | None = None, limit: int | None = 100) -> list[dict]:
    """Return non-revoked Auto Check events, optionally bounded by work date."""
    ensure_schema(conn)
    conditions = ["status <> 'revoked'"]
    params: dict[str, object] = {}
    if start is not None:
        conditions.append("work_date >= :start")
        params["start"] = start
    if end is not None:
        conditions.append("work_date <= :end")
        params["end"] = end

    query = """
        SELECT work_date,employee_name,reason,source,minutes,status,detail,created_at
        FROM vera_auto_check_event
        WHERE {conditions}
        ORDER BY work_date DESC, id DESC
    """.format(conditions=" AND ".join(conditions))
    if limit is not None:
        query += " LIMIT :limit"
        params["limit"] = max(1, min(50_000, int(limit)))

    rows = [dict(row) for row in conn.execute(text(query), params).mappings()]
    for row in rows:
        for key, value in list(row.items()):
            if isinstance(value, (date, datetime)):
                row[key] = value.isoformat()
            elif hasattr(value, "as_tuple"):
                row[key] = float(value)
    return rows


def save_violation(conn, *, work_date: date, employee: str, reason_item: dict, detail: str, source: str, minutes=0) -> tuple[bool, str]:
    ensure_schema(conn)
    reason = str(reason_item.get("name") or "").strip()
    event_key = f"{work_date.isoformat()}|{_norm(employee)}|{_norm(reason)}"
    inserted = conn.execute(text("""
        INSERT INTO vera_auto_check_event(event_key,work_date,employee_name,reason,source,minutes,status,detail,employee_notified_at)
        VALUES (:key,:day,:employee,:reason,:source,:minutes,'processing',:detail,NULL)
        ON CONFLICT(event_key) DO UPDATE SET
          status='processing', source=EXCLUDED.source, minutes=EXCLUDED.minutes,
          detail=EXCLUDED.detail, created_at=NOW(), employee_notify_claimed_at=NULL,
          employee_notify_attempted_at=NULL, employee_notified_at=NULL,
          employee_notify_error=NULL
        WHERE vera_auto_check_event.status='revoked'
        RETURNING id
    """), {"key": event_key, "day": work_date, "employee": employee, "reason": reason, "source": source, "minutes": float(minutes or 0), "detail": detail}).scalar()
    if not inserted:
        return True, "SKIP_DUPLICATE"
    days = float(reason_item.get("days") or 0)
    accumulated = float(conn.execute(text("""
        SELECT COALESCE(SUM(calculated_days),0) FROM leave_records
        WHERE employee_name=:employee AND date_trunc('month',leave_date)=date_trunc('month',CAST(:day AS date))
    """), {"employee": employee, "day": work_date}).scalar() or 0) + days
    ordinal = int(conn.execute(text("""
        SELECT COUNT(*) FROM leave_records WHERE leave_date=:day AND lower(leave_reason)=lower(:reason)
    """), {"day": work_date, "reason": reason}).scalar() or 0) + 1
    progressive = _norm(reason) in {"nghi khong phep", "di tre khong phep", "ve som khong phep"}
    penalty = float(reason_item.get("penalty") or 0) + (max(0, ordinal - 2) * 100000 if progressive else 0)
    if progressive:
        detail = f"Người Thứ {ordinal} {reason.lower()} | {detail}"
    uid = str(uuid.uuid4())
    now = datetime.now(VN_TZ)
    source_row = -int(inserted)
    payload = {"Ngày": work_date.strftime("%d/%m/%Y"), "Tên nhân viên": employee, "Lý do nghỉ": reason,
               "Loại nghỉ": reason_item.get("type") or "Vi phạm", "Chi tiết": detail, "Số ngày tính": days,
               "Số ngày phép cộng dồn": accumulated, "Phạt vi phạm": penalty, "record_uid": uid,
               "__source_sheet_id": "postgres:auto_check", "__source_row": source_row}
    conn.execute(text("""
        INSERT INTO leave_records(source_sheet_id,source_row,leave_date,employee_name,leave_reason,leave_type,detail,
          calculated_days,accumulated_leave,penalty,update_date,update_time,updated_by,weekday_label,payload,record_uid,created_at,updated_at)
        VALUES ('postgres:auto_check',:srow,:day,:employee,:reason,:type,:detail,:days,:acc,:penalty,:udate,:utime,:actor,:weekday,CAST(:payload AS jsonb),:uid,NOW(),NOW())
    """), {"srow": source_row, "day": work_date, "employee": employee, "reason": reason,
        "type": reason_item.get("type") or "Vi phạm", "detail": detail, "days": days, "acc": accumulated,
        "penalty": penalty, "udate": now.strftime("%d/%m/%Y"), "utime": now.strftime("%H:%M:%S"),
        "actor": source, "weekday": f"Thứ {work_date.isoweekday()+1}" if work_date.isoweekday() < 7 else "Chủ nhật",
        "payload": json.dumps(payload, ensure_ascii=False), "uid": uid})
    conn.execute(text("UPDATE vera_auto_check_event SET status='added',leave_record_uid=:uid,detail=:detail WHERE id=:id"), {"uid": uid, "detail": detail, "id": inserted})
    return True, "ADDED"


def dashboard(conn, limit=100, *, start: date | None = None, end: date | None = None) -> dict:
    cfg = load_config(conn)
    runs = [dict(row) for row in conn.execute(text("SELECT id,trigger_type,status,started_at,completed_at,details,error FROM vera_auto_check_run ORDER BY id DESC LIMIT 20")).mappings()]
    events = event_rows(conn, start=start, end=end, limit=max(1, min(500, int(limit))))
    for row in runs:
        for key, value in list(row.items()):
            if isinstance(value, (date, datetime)):
                row[key] = value.isoformat()
            elif hasattr(value, "as_tuple"):
                row[key] = float(value)
    return {
        "release": RELEASE,
        "config": cfg,
        "runs": runs,
        "events": events,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
    }

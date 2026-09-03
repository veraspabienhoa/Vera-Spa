"""Attendance controls and work-schedule rules for Locker and Lễ tân."""
from __future__ import annotations

from datetime import date
import json
import unicodedata
from typing import Any, Callable

from fastapi import Depends, HTTPException
from sqlalchemy import text

from vera_department_attendance_rules import schedule_late_minutes


RELEASE = "department-attendance-2026-09-03-v1"
DEPARTMENTS = ("locker", "letan")
LABELS = {"locker": "Locker", "letan": "Lễ tân"}
DEFAULT_CONTROL = {"attendance_enabled": True, "notifications_enabled": True}
CATEGORY = "department_attendance_control"


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").strip().lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return " ".join(raw.replace("đ", "d").split())


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or ""))
        return dict(parsed) if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def controls(conn) -> dict[str, dict[str, bool]]:
    rows = conn.execute(text("""
        SELECT setting_key,value_json FROM vera_app_setting
        WHERE category=:category AND setting_key IN ('locker','letan')
    """), {"category": CATEGORY}).mappings().all()
    stored = {str(row.get("setting_key") or ""): _json(row.get("value_json")) for row in rows}
    result: dict[str, dict[str, bool]] = {}
    for department in DEPARTMENTS:
        value = {**DEFAULT_CONTROL, **stored.get(department, {})}
        result[department] = {
            "attendance_enabled": bool(value.get("attendance_enabled", True)),
            "notifications_enabled": bool(value.get("notifications_enabled", True)),
        }
    return result


def control_for(conn, department: str) -> dict[str, bool]:
    return controls(conn).get(str(department or "").lower(), {**DEFAULT_CONTROL})


def save_control(conn, department: str, updates: dict[str, Any], actor: str) -> dict[str, bool]:
    department = str(department or "").strip().lower()
    if department not in DEPARTMENTS:
        raise ValueError("Bộ phận chỉ hỗ trợ Locker hoặc Lễ tân.")
    value = control_for(conn, department)
    for key in DEFAULT_CONTROL:
        if key in updates:
            value[key] = bool(updates[key])
    conn.execute(text("""
        INSERT INTO vera_app_setting(
          category,setting_key,value_json,source,updated_by,revision,created_at,updated_at
        ) VALUES (
          :category,:department,CAST(:value AS jsonb),'web_v2',:actor,1,NOW(),NOW()
        )
        ON CONFLICT(category,setting_key) DO UPDATE SET
          value_json=EXCLUDED.value_json,source='web_v2',updated_by=EXCLUDED.updated_by,
          revision=vera_app_setting.revision+1,updated_at=NOW()
    """), {
        "category": CATEGORY, "department": department,
        "value": json.dumps(value, ensure_ascii=False), "actor": actor or "admin",
    })
    return value


def employee_role(conn, employee: str) -> str:
    row = conn.execute(text("""
        SELECT lower(COALESCE(role,'')) AS role
        FROM employees
        WHERE COALESCE(payload->>'__deleted','false') <> 'true'
          AND (lower(btrim(username))=lower(btrim(:employee))
               OR lower(btrim(COALESCE(full_name,'')))=lower(btrim(:employee)))
        ORDER BY CASE WHEN lower(btrim(username))=lower(btrim(:employee)) THEN 0 ELSE 1 END
        LIMIT 1
    """), {"employee": employee}).mappings().first()
    return str((row or {}).get("role") or "").strip().lower()


def scheduled_shift(conn, work_day: date, employee: str, department: str) -> dict[str, Any] | None:
    row = conn.execute(text("""
        SELECT ws.shift_code,
               COALESCE(NULLIF(ws.start_time,''),d.start_time,'') AS start_time,
               COALESCE(NULLIF(ws.end_time,''),d.end_time,'') AS end_time,
               ws.overtime_shift,ws.overtime_start_time,ws.overtime_end_time
        FROM vera_work_schedule ws
        LEFT JOIN vera_work_shift_definition d
          ON d.department=ws.department AND lower(d.shift_code)=lower(ws.shift_code)
        WHERE ws.work_date=:work_day AND lower(ws.department)=:department
          AND (lower(btrim(ws.employee_username))=lower(btrim(:employee))
               OR lower(btrim(ws.employee_name))=lower(btrim(:employee)))
        LIMIT 1
    """), {"work_day": work_day, "employee": employee, "department": department}).mappings().first()
    if not row:
        return None
    result = dict(row)
    if _norm(result.get("shift_code")) == "nghi":
        result["is_off"] = True
    return result


def apply_schedule_to_record(conn, item: dict[str, Any], work_day: date, employee: str, role: str) -> dict[str, Any] | None:
    role = str(role or "").lower()
    if role not in DEPARTMENTS:
        return item
    if not control_for(conn, role)["attendance_enabled"]:
        return None
    schedule = scheduled_shift(conn, work_day, employee, role)
    if not schedule or schedule.get("is_off"):
        return None
    result = dict(item)
    result.update({
        "shift": str(schedule.get("shift_code") or ""),
        "shift_start": str(schedule.get("start_time") or ""),
        "shift_end": str(schedule.get("end_time") or ""),
        "break_department": LABELS[role],
        "break_enabled": False,
        "break_planned_minutes": 0,
        "break_actual_minutes": 0,
        "break_over_minutes": 0,
        "break_count": 0,
        "break_out": "",
        "break_in": "",
        "break_detail": "",
        "break_source": "",
        "break_method": "Không áp dụng cho bộ phận",
        "break_status": f"{LABELS[role]} không áp dụng chính sách nghỉ giữa ca",
        "break_restricted_reason": "",
        "break_return_late_minutes": 0,
        "break_return_deadline": "",
        "break_return_deadline_iso": "",
        "attendance_schedule_source": "Lịch làm việc",
    })
    calculated = schedule_late_minutes(result.get("check_in"), result.get("shift_start"))
    result["late_minutes"] = int(round(calculated)) if calculated is not None else 0
    result["arrival_status"] = "Đi trễ" if result["late_minutes"] > 0 else "Đúng giờ"
    return result


def install_department_attendance_routes(
    app, *, engine_instance: Callable[[], Any], current_identity, identity_type,
) -> None:
    if getattr(app.state, "department_attendance_installed", False):
        return

    @app.get("/v2/attendance/department-controls")
    def get_department_controls(ident: identity_type = Depends(current_identity)):
        del ident
        with engine_instance().connect() as conn:
            value = controls(conn)
        return {"ok": True, "release": RELEASE, "departments": value}

    @app.put("/v2/attendance/department-controls/{department}")
    def update_department_control(
        department: str, payload: dict[str, Any], ident: identity_type = Depends(current_identity),
    ):
        if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được tắt/mở chấm công và thông báo theo bộ phận.")
        department = department.strip().lower()
        if department not in DEPARTMENTS:
            raise HTTPException(400, "Bộ phận chỉ hỗ trợ Locker hoặc Lễ tân.")
        actor = str(getattr(ident, "employee_username", "") or "admin").strip()
        with engine_instance().begin() as conn:
            value = save_control(conn, department, payload, actor)
        return {"ok": True, "release": RELEASE, "department": department, **value}

    @app.get("/v2/attendance/department-controls/health")
    def department_attendance_health():
        return {
            "ok": True, "release": RELEASE, "departments": list(DEPARTMENTS),
            "schedule_source": "vera_work_schedule", "midshift_break": False,
            "notification_audience": ["employee", "quanly", "admin"],
        }

    app.state.department_attendance_installed = True
    app.state.department_attendance_release = RELEASE

"""Daily work-schedule module for VERA Web V2.

Schedules are assigned by individual calendar date, never generated from a recurring
cycle. Locker and Lễ tân have fixed shift definitions supplied by operations:
- Locker Ca 1: 09:30-17:30
- Locker Ca 2: 17:30-01:30 (+1 day)
- Lễ tân Ca 1: 09:00-17:00
- Lễ tân Ca 2: 16:30-00:30 (+1 day)

Quản lý is scheduled with a start time and end time for each individual date.
Overtime remains separate for Locker/Lễ tân so the UI can reproduce the reference
layout with a main shift and overtime value in each day cell.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Callable, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text


SHIFT_DEFINITIONS = {
    "locker": {
        "Ca 1": {"start": "09:30", "end": "17:30", "end_next_day": False},
        "Ca 2": {"start": "17:30", "end": "01:30", "end_next_day": True},
    },
    "letan": {
        "Ca 1": {"start": "09:00", "end": "17:00", "end_next_day": False},
        "Ca 2": {"start": "16:30", "end": "00:30", "end_next_day": True},
    },
    "quanly": {
        "mode": "daily_time_range",
    },
}

WORK_SCHEDULE_FEATURES = {
    "quanly": "work_schedule_quanly",
    "letan": "work_schedule_letan",
    "locker": "work_schedule_locker",
}

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ScheduleRow(BaseModel):
    work_date: date
    employee_username: str = Field(min_length=1, max_length=200)
    employee_name: str = Field(default="", max_length=300)
    department: Literal["quanly", "locker", "letan"]
    shift_code: Literal["Ca 1", "Ca 2", "Nghỉ", "Giờ làm"]
    overtime_shift: Literal["", "TC Ca 1", "TC Ca 2"] = ""
    start_time: str = Field(default="", max_length=5)
    end_time: str = Field(default="", max_length=5)
    note: str = Field(default="", max_length=500)


class ScheduleSave(BaseModel):
    rows: list[ScheduleRow] = Field(default_factory=list, max_length=1000)


def _ensure_schema(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_work_schedule (
            work_date DATE NOT NULL,
            employee_username TEXT NOT NULL,
            employee_name TEXT NOT NULL DEFAULT '',
            department TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            overtime_shift TEXT NOT NULL DEFAULT '',
            start_time TEXT NOT NULL DEFAULT '',
            end_time TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(work_date, employee_username)
        )
    """))
    # Safe migration for the first version of the table already in production.
    conn.execute(text("ALTER TABLE vera_work_schedule ADD COLUMN IF NOT EXISTS start_time TEXT NOT NULL DEFAULT ''"))
    conn.execute(text("ALTER TABLE vera_work_schedule ADD COLUMN IF NOT EXISTS end_time TEXT NOT NULL DEFAULT ''"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vera_work_schedule_department_date ON vera_work_schedule(department, work_date)"))


def _role(ident: Any) -> str:
    return str(getattr(ident, "role", "") or "").strip().lower()


def _actor(ident: Any) -> str:
    return str(getattr(ident, "employee_username", "") or getattr(ident, "email", "") or "web_v2")


def _feature_for_department(department: str) -> str:
    try:
        return WORK_SCHEDULE_FEATURES[department]
    except KeyError as exc:
        raise HTTPException(400, "Bộ phận chỉ hỗ trợ Quản lý, Lễ tân hoặc Locker.") from exc


def _allowed_department(conn, ident, department: str, feature_allowed) -> bool:
    return bool(feature_allowed(conn, ident, _feature_for_department(department)))


def _validate_row(row: ScheduleRow) -> tuple[str, str]:
    """Validate and normalize schedule-specific fields."""
    start_time = str(row.start_time or "").strip()
    end_time = str(row.end_time or "").strip()

    if row.department == "quanly":
        if row.shift_code not in {"Giờ làm", "Nghỉ"}:
            raise HTTPException(400, "Lịch Quản lý chỉ dùng Giờ làm hoặc Nghỉ.")
        if row.overtime_shift:
            raise HTTPException(400, "Lịch Quản lý không dùng TC Ca 1 / TC Ca 2.")
        if row.shift_code == "Nghỉ":
            return "", ""
        if not (_TIME_RE.fullmatch(start_time) and _TIME_RE.fullmatch(end_time)):
            raise HTTPException(
                400,
                f"Quản lý {row.employee_name or row.employee_username} ngày {row.work_date:%d/%m/%Y} cần đủ giờ bắt đầu và giờ kết thúc dạng HH:MM.",
            )
        return start_time, end_time

    if row.shift_code not in {"Ca 1", "Ca 2", "Nghỉ"}:
        raise HTTPException(400, "Ca làm việc không hợp lệ.")
    if row.shift_code != "Nghỉ" and row.shift_code not in SHIFT_DEFINITIONS[row.department]:
        raise HTTPException(400, "Ca làm việc không hợp lệ.")
    if row.shift_code == "Nghỉ" and row.overtime_shift:
        raise HTTPException(400, "Ngày nghỉ không thể đồng thời có tăng ca.")
    return "", ""


def install_work_schedule_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    feature_allowed,
) -> None:
    if getattr(app.state, "work_schedule_installed", False):
        return

    @app.get("/v2/work-schedule")
    def get_work_schedule(
        start: date = Query(...),
        end: date = Query(...),
        department: str = Query(""),
        ident=Depends(current_identity),
    ):
        if end < start:
            raise HTTPException(400, "Ngày kết thúc phải từ ngày bắt đầu trở đi.")
        if (end - start).days > 62:
            raise HTTPException(400, "Chỉ xem tối đa 63 ngày mỗi lần.")
        dep = department.strip().lower()
        if dep and dep not in SHIFT_DEFINITIONS:
            raise HTTPException(400, "Bộ phận chỉ hỗ trợ Quản lý, Locker hoặc Lễ tân.")

        with engine_instance().begin() as conn:
            _ensure_schema(conn)
            allowed_departments = [
                item for item in ("quanly", "letan", "locker")
                if _allowed_department(conn, ident, item, feature_allowed)
            ]
            if dep and dep not in allowed_departments:
                raise HTTPException(403, "Bạn không có quyền xem lịch làm việc của bộ phận này.")
            if not dep and not allowed_departments:
                raise HTTPException(403, "Bạn không có quyền xem Lịch làm việc.")

            sql = """
                SELECT work_date, employee_username, employee_name, department,
                       shift_code, overtime_shift, start_time, end_time, note,
                       updated_by, updated_at
                FROM vera_work_schedule
                WHERE work_date BETWEEN :start AND :end
            """
            params: dict[str, Any] = {"start": start, "end": end}
            if dep:
                sql += " AND department=:department"
                params["department"] = dep
            else:
                sql += " AND department = ANY(:departments)"
                params["departments"] = allowed_departments
            sql += " ORDER BY department, employee_name, employee_username, work_date"
            rows = conn.execute(text(sql), params).mappings().all()

        return {
            "ok": True,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "shift_definitions": SHIFT_DEFINITIONS,
            "rows": [dict(row) for row in rows],
            "can_edit": _role(ident) in {"admin", "quanly"},
            "allowed_departments": allowed_departments,
            "assignment_mode": "daily",
            "display_mode": "current_and_next_week_14_days",
        }

    @app.put("/v2/work-schedule")
    def save_work_schedule(body: ScheduleSave, ident=Depends(current_identity)):
        if _role(ident) not in {"admin", "quanly"}:
            raise HTTPException(403, "Chỉ Admin hoặc Quản lý được sắp xếp lịch làm việc.")
        actor = _actor(ident)

        unique_keys: set[tuple[date, str]] = set()
        normalized_rows: list[tuple[ScheduleRow, str, str]] = []
        with engine_instance().begin() as conn:
            _ensure_schema(conn)
            for row in body.rows:
                key = (row.work_date, row.employee_username.strip())
                if key in unique_keys:
                    raise HTTPException(400, f"Trùng lịch {row.employee_username} ngày {row.work_date:%d/%m/%Y}.")
                unique_keys.add(key)
                if not _allowed_department(conn, ident, row.department, feature_allowed):
                    raise HTTPException(403, f"Bạn không có quyền sửa lịch {row.department}.")
                start_time, end_time = _validate_row(row)
                normalized_rows.append((row, start_time, end_time))

            for row, start_time, end_time in normalized_rows:
                conn.execute(text("""
                    INSERT INTO vera_work_schedule(
                        work_date, employee_username, employee_name, department,
                        shift_code, overtime_shift, start_time, end_time, note,
                        updated_by, created_at, updated_at
                    ) VALUES (
                        :work_date, :employee_username, :employee_name, :department,
                        :shift_code, :overtime_shift, :start_time, :end_time, :note,
                        :updated_by, NOW(), NOW()
                    )
                    ON CONFLICT(work_date, employee_username) DO UPDATE SET
                        employee_name=EXCLUDED.employee_name,
                        department=EXCLUDED.department,
                        shift_code=EXCLUDED.shift_code,
                        overtime_shift=EXCLUDED.overtime_shift,
                        start_time=EXCLUDED.start_time,
                        end_time=EXCLUDED.end_time,
                        note=EXCLUDED.note,
                        updated_by=EXCLUDED.updated_by,
                        updated_at=NOW()
                """), {
                    "work_date": row.work_date,
                    "employee_username": row.employee_username.strip(),
                    "employee_name": row.employee_name.strip(),
                    "department": row.department,
                    "shift_code": row.shift_code,
                    "overtime_shift": row.overtime_shift if row.department != "quanly" else "",
                    "start_time": start_time,
                    "end_time": end_time,
                    "note": row.note.strip(),
                    "updated_by": actor,
                })

        return {"ok": True, "saved": len(normalized_rows), "message": "Đã lưu lịch làm việc theo từng ngày."}

    @app.delete("/v2/work-schedule")
    def delete_work_schedule(
        work_date: date = Query(...),
        employee_username: str = Query(..., min_length=1),
        ident=Depends(current_identity),
    ):
        if _role(ident) not in {"admin", "quanly"}:
            raise HTTPException(403, "Chỉ Admin hoặc Quản lý được xóa lịch làm việc.")
        with engine_instance().begin() as conn:
            _ensure_schema(conn)
            existing = conn.execute(text("""
                SELECT department FROM vera_work_schedule
                WHERE work_date=:work_date AND employee_username=:employee_username
            """), {"work_date": work_date, "employee_username": employee_username.strip()}).mappings().first()
            if existing and not _allowed_department(conn, ident, str(existing.get("department") or ""), feature_allowed):
                raise HTTPException(403, "Bạn không có quyền xóa lịch làm việc của bộ phận này.")
            result = conn.execute(text("""
                DELETE FROM vera_work_schedule
                WHERE work_date=:work_date AND employee_username=:employee_username
            """), {"work_date": work_date, "employee_username": employee_username.strip()})
        return {"ok": True, "deleted": int(result.rowcount or 0)}

    app.state.work_schedule_installed = True

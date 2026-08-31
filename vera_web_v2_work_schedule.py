"""Daily work-schedule module for VERA Web V2.

Schedules are assigned by individual calendar date, never generated from a recurring
cycle. Locker and Lễ tân have fixed shift definitions supplied by operations:
- Locker Ca 1: 09:30-17:30
- Locker Ca 2: 17:30-01:30 (+1 day)
- Lễ tân Ca 1: 09:00-17:00
- Lễ tân Ca 2: 16:30-00:30 (+1 day)

Overtime is stored separately so the UI can reproduce the reference layout with a
main shift grid and an overtime grid underneath.
"""
from __future__ import annotations

from datetime import date
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
}


class ScheduleRow(BaseModel):
    work_date: date
    employee_username: str = Field(min_length=1, max_length=200)
    employee_name: str = Field(default="", max_length=300)
    department: Literal["locker", "letan"]
    shift_code: Literal["Ca 1", "Ca 2", "Nghỉ"]
    overtime_shift: Literal["", "TC Ca 1", "TC Ca 2"] = ""
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
            note TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(work_date, employee_username)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vera_work_schedule_department_date ON vera_work_schedule(department, work_date)"))


def _role(ident: Any) -> str:
    return str(getattr(ident, "role", "") or "").strip().lower()


def _actor(ident: Any) -> str:
    return str(getattr(ident, "employee_username", "") or getattr(ident, "email", "") or "web_v2")


def install_work_schedule_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
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
            raise HTTPException(400, "Bộ phận chỉ hỗ trợ Locker hoặc Lễ tân.")

        with engine_instance().begin() as conn:
            _ensure_schema(conn)
            sql = """
                SELECT work_date, employee_username, employee_name, department,
                       shift_code, overtime_shift, note, updated_by, updated_at
                FROM vera_work_schedule
                WHERE work_date BETWEEN :start AND :end
            """
            params: dict[str, Any] = {"start": start, "end": end}
            if dep:
                sql += " AND department=:department"
                params["department"] = dep
            sql += " ORDER BY department, employee_name, employee_username, work_date"
            rows = conn.execute(text(sql), params).mappings().all()

        return {
            "ok": True,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "shift_definitions": SHIFT_DEFINITIONS,
            "rows": [dict(row) for row in rows],
            "can_edit": _role(ident) in {"admin", "quanly"},
            "assignment_mode": "daily",
        }

    @app.put("/v2/work-schedule")
    def save_work_schedule(body: ScheduleSave, ident=Depends(current_identity)):
        if _role(ident) not in {"admin", "quanly"}:
            raise HTTPException(403, "Chỉ Admin hoặc Quản lý được sắp xếp lịch làm việc.")
        actor = _actor(ident)

        unique_keys: set[tuple[date, str]] = set()
        for row in body.rows:
            key = (row.work_date, row.employee_username.strip())
            if key in unique_keys:
                raise HTTPException(400, f"Trùng lịch {row.employee_username} ngày {row.work_date:%d/%m/%Y}.")
            unique_keys.add(key)
            if row.shift_code != "Nghỉ" and row.shift_code not in SHIFT_DEFINITIONS[row.department]:
                raise HTTPException(400, "Ca làm việc không hợp lệ.")

        with engine_instance().begin() as conn:
            _ensure_schema(conn)
            for row in body.rows:
                conn.execute(text("""
                    INSERT INTO vera_work_schedule(
                        work_date, employee_username, employee_name, department,
                        shift_code, overtime_shift, note, updated_by, created_at, updated_at
                    ) VALUES (
                        :work_date, :employee_username, :employee_name, :department,
                        :shift_code, :overtime_shift, :note, :updated_by, NOW(), NOW()
                    )
                    ON CONFLICT(work_date, employee_username) DO UPDATE SET
                        employee_name=EXCLUDED.employee_name,
                        department=EXCLUDED.department,
                        shift_code=EXCLUDED.shift_code,
                        overtime_shift=EXCLUDED.overtime_shift,
                        note=EXCLUDED.note,
                        updated_by=EXCLUDED.updated_by,
                        updated_at=NOW()
                """), {
                    "work_date": row.work_date,
                    "employee_username": row.employee_username.strip(),
                    "employee_name": row.employee_name.strip(),
                    "department": row.department,
                    "shift_code": row.shift_code,
                    "overtime_shift": row.overtime_shift,
                    "note": row.note.strip(),
                    "updated_by": actor,
                })

        return {"ok": True, "saved": len(body.rows), "message": "Đã lưu lịch làm việc theo từng ngày."}

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
            result = conn.execute(text("""
                DELETE FROM vera_work_schedule
                WHERE work_date=:work_date AND employee_username=:employee_username
            """), {"work_date": work_date, "employee_username": employee_username.strip()})
        return {"ok": True, "deleted": int(result.rowcount or 0)}

    app.state.work_schedule_installed = True

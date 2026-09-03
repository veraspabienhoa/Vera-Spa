"""Daily work-schedule module for VERA Web V2.

Schedules are assigned by individual calendar date, never generated from a recurring
cycle. The UI may load a whole selected month (up to 63 days per request).

Quản lý is scheduled with a start/end time for each date. Locker and Lễ tân use
configurable shift definitions stored in PostgreSQL. All three departments share
the same overtime choices: TC Ca 1, TC Ca 2, or an explicit time range.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Callable, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text


DEFAULT_SHIFT_DEFINITIONS = {
    "locker": {
        "Ca 1": {"start": "09:30", "end": "17:30"},
        "Ca 2": {"start": "17:30", "end": "01:30"},
    },
    "letan": {
        "Ca 1": {"start": "09:00", "end": "17:00"},
        "Ca 2": {"start": "16:30", "end": "00:30"},
    },
}

WORK_SCHEDULE_FEATURES = {
    "quanly": "work_schedule_quanly",
    "letan": "work_schedule_letan",
    "locker": "work_schedule_locker",
}

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
OVERTIME_SHIFT_CHOICES = {"", "TC Ca 1", "TC Ca 2", "Từ giờ tới giờ"}


class ScheduleRow(BaseModel):
    work_date: date
    employee_username: str = Field(min_length=1, max_length=200)
    employee_name: str = Field(default="", max_length=300)
    department: Literal["quanly", "locker", "letan"]
    shift_code: str = Field(min_length=1, max_length=100)
    overtime_shift: str = Field(default="", max_length=100)
    start_time: str = Field(default="", max_length=5)
    end_time: str = Field(default="", max_length=5)
    overtime_start_time: str = Field(default="", max_length=5)
    overtime_end_time: str = Field(default="", max_length=5)
    note: str = Field(default="", max_length=500)


class ScheduleSave(BaseModel):
    rows: list[ScheduleRow] = Field(default_factory=list, max_length=1000)


class ShiftDefinitionRow(BaseModel):
    shift_code: str = Field(min_length=1, max_length=100)
    start_time: str = Field(min_length=5, max_length=5)
    end_time: str = Field(min_length=5, max_length=5)


class ShiftDefinitionSave(BaseModel):
    department: Literal["locker", "letan"]
    shifts: list[ShiftDefinitionRow] = Field(min_length=1, max_length=20)


def _time_is_next_day(start_time: str, end_time: str) -> bool:
    return end_time <= start_time


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
            overtime_start_time TEXT NOT NULL DEFAULT '',
            overtime_end_time TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(work_date, employee_username)
        )
    """))
    conn.execute(text("ALTER TABLE vera_work_schedule ADD COLUMN IF NOT EXISTS start_time TEXT NOT NULL DEFAULT ''"))
    conn.execute(text("ALTER TABLE vera_work_schedule ADD COLUMN IF NOT EXISTS end_time TEXT NOT NULL DEFAULT ''"))
    conn.execute(text("ALTER TABLE vera_work_schedule ADD COLUMN IF NOT EXISTS overtime_start_time TEXT NOT NULL DEFAULT ''"))
    conn.execute(text("ALTER TABLE vera_work_schedule ADD COLUMN IF NOT EXISTS overtime_end_time TEXT NOT NULL DEFAULT ''"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vera_work_schedule_department_date ON vera_work_schedule(department, work_date)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_work_shift_definition (
            department TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(department, shift_code)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vera_work_shift_definition_department ON vera_work_shift_definition(department, sort_order, shift_code)"))

    for department, defaults in DEFAULT_SHIFT_DEFINITIONS.items():
        existing = conn.execute(text("""
            SELECT COUNT(*) FROM vera_work_shift_definition WHERE department=:department
        """), {"department": department}).scalar_one()
        if int(existing or 0) > 0:
            continue
        for sort_order, (shift_code, spec) in enumerate(defaults.items(), start=1):
            conn.execute(text("""
                INSERT INTO vera_work_shift_definition(
                    department, shift_code, start_time, end_time, sort_order, updated_by
                ) VALUES (
                    :department, :shift_code, :start_time, :end_time, :sort_order, 'system-default'
                )
                ON CONFLICT(department, shift_code) DO NOTHING
            """), {
                "department": department,
                "shift_code": shift_code,
                "start_time": spec["start"],
                "end_time": spec["end"],
                "sort_order": sort_order,
            })


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


def _employee_catalog(conn, department: str) -> list[dict[str, Any]]:
    """Schedule viewers do not need the broad staff_list permission."""
    rows = conn.execute(text("""
        SELECT username,
               COALESCE(NULLIF(full_name,''), username) AS full_name,
               lower(COALESCE(role,'')) AS role,
               COALESCE(payload->>'Trạng thái làm việc','') AS employment_status
        FROM employees
        WHERE lower(COALESCE(role,''))=:department
          AND COALESCE(payload->>'__deleted','false') <> 'true'
        ORDER BY lower(COALESCE(NULLIF(full_name,''), username)), lower(username)
    """), {"department": department}).mappings().all()
    return [dict(row) for row in rows]


def _load_shift_definitions(conn) -> dict[str, Any]:
    output: dict[str, Any] = {
        "quanly": {"mode": "daily_time_range"},
        "locker": {},
        "letan": {},
    }
    rows = conn.execute(text("""
        SELECT department, shift_code, start_time, end_time, sort_order
        FROM vera_work_shift_definition
        WHERE department IN ('locker','letan')
        ORDER BY department, sort_order, lower(shift_code)
    """)).mappings().all()
    for row in rows:
        department = str(row.get("department") or "")
        shift_code = str(row.get("shift_code") or "")
        start_time = str(row.get("start_time") or "")[:5]
        end_time = str(row.get("end_time") or "")[:5]
        if not department or not shift_code:
            continue
        output.setdefault(department, {})[shift_code] = {
            "start": start_time,
            "end": end_time,
            "end_next_day": _time_is_next_day(start_time, end_time),
        }
    return output


def _validate_shift_definition(row: ShiftDefinitionRow) -> tuple[str, str, str]:
    shift_code = str(row.shift_code or "").strip()
    start_time = str(row.start_time or "").strip()
    end_time = str(row.end_time or "").strip()
    if not shift_code or shift_code.casefold() in {"nghỉ", "nghi", "giờ làm", "gio lam"}:
        raise HTTPException(400, "Tên ca không hợp lệ.")
    if not (_TIME_RE.fullmatch(start_time) and _TIME_RE.fullmatch(end_time)):
        raise HTTPException(400, f"Ca {shift_code}: giờ bắt đầu/kết thúc phải theo HH:MM.")
    if start_time == end_time:
        raise HTTPException(400, f"Ca {shift_code}: giờ bắt đầu và kết thúc không được trùng nhau.")
    return shift_code, start_time, end_time


def _validate_row(row: ScheduleRow, shift_definitions: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Validate and normalize schedule-specific fields."""
    shift_code = str(row.shift_code or "").strip()
    overtime_shift = str(row.overtime_shift or "").strip()
    start_time = str(row.start_time or "").strip()
    end_time = str(row.end_time or "").strip()
    overtime_start_time = str(row.overtime_start_time or "").strip()
    overtime_end_time = str(row.overtime_end_time or "").strip()

    if row.department == "quanly":
        if shift_code not in {"Giờ làm", "Nghỉ"}:
            raise HTTPException(400, "Lịch Quản lý chỉ dùng Giờ làm hoặc Nghỉ.")
        if shift_code == "Nghỉ":
            if overtime_shift or overtime_start_time or overtime_end_time:
                raise HTTPException(400, "Ngày nghỉ không thể đồng thời có tăng ca.")
            return "", "", "", "", ""
        if not (_TIME_RE.fullmatch(start_time) and _TIME_RE.fullmatch(end_time)):
            raise HTTPException(
                400,
                f"Quản lý {row.employee_name or row.employee_username} ngày {row.work_date:%d/%m/%Y} cần đủ giờ bắt đầu và giờ kết thúc dạng HH:MM.",
            )
    elif shift_code == "Nghỉ":
        if overtime_shift or overtime_start_time or overtime_end_time:
            raise HTTPException(400, "Ngày nghỉ không thể đồng thời có tăng ca.")
        return "", "", "", "", ""
    elif shift_code not in (shift_definitions.get(row.department) or {}):
        raise HTTPException(400, f"Ca '{shift_code}' không còn trong cấu hình {row.department}.")

    if overtime_shift not in OVERTIME_SHIFT_CHOICES:
        raise HTTPException(400, "Tăng ca chỉ dùng TC Ca 1, TC Ca 2 hoặc Từ giờ tới giờ.")
    has_overtime_times = bool(overtime_start_time or overtime_end_time)
    custom_overtime = overtime_shift == "Từ giờ tới giờ" or (not overtime_shift and has_overtime_times)
    if overtime_shift in {"TC Ca 1", "TC Ca 2"}:
        if overtime_start_time or overtime_end_time:
            raise HTTPException(400, "TC Ca 1/TC Ca 2 không nhập thêm khoảng giờ tùy chỉnh.")
        return start_time if row.department == "quanly" else "", end_time if row.department == "quanly" else "", overtime_shift, "", ""
    if custom_overtime and not (_TIME_RE.fullmatch(overtime_start_time) and _TIME_RE.fullmatch(overtime_end_time)):
        raise HTTPException(
            400,
            f"{row.employee_name or row.employee_username} ngày {row.work_date:%d/%m/%Y}: tăng ca cần đủ giờ bắt đầu và kết thúc dạng HH:MM.",
        )
    if custom_overtime and overtime_start_time == overtime_end_time:
        raise HTTPException(400, "Giờ bắt đầu và kết thúc tăng ca không được trùng nhau.")
    return (
        start_time if row.department == "quanly" else "",
        end_time if row.department == "quanly" else "",
        "Từ giờ tới giờ" if custom_overtime else "",
        overtime_start_time if custom_overtime else "",
        overtime_end_time if custom_overtime else "",
    )


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
        if dep and dep not in WORK_SCHEDULE_FEATURES:
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
                       shift_code, overtime_shift, start_time, end_time,
                       overtime_start_time, overtime_end_time, note,
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
            employees = _employee_catalog(conn, dep) if dep else []
            shift_definitions = _load_shift_definitions(conn)

        return {
            "ok": True,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "shift_definitions": shift_definitions,
            "rows": [dict(row) for row in rows],
            "employees": employees,
            "can_edit": _role(ident) in {"admin", "quanly"},
            "allowed_departments": allowed_departments,
            "assignment_mode": "daily",
            "display_mode": "selected_month_all_days",
            "overtime_mode": {"locker": "shared", "letan": "shared", "quanly": "shared"},
            "overtime_choices": ["TC Ca 1", "TC Ca 2", "Từ giờ tới giờ"],
        }

    @app.put("/v2/work-schedule/shifts")
    def save_shift_definitions(body: ShiftDefinitionSave, ident=Depends(current_identity)):
        if _role(ident) not in {"admin", "quanly"}:
            raise HTTPException(403, "Chỉ Admin hoặc Quản lý được tạo/sửa ca làm việc.")
        actor = _actor(ident)
        normalized: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for item in body.shifts:
            shift_code, start_time, end_time = _validate_shift_definition(item)
            key = shift_code.casefold()
            if key in seen:
                raise HTTPException(400, f"Tên ca bị trùng: {shift_code}.")
            seen.add(key)
            normalized.append((shift_code, start_time, end_time))

        with engine_instance().begin() as conn:
            _ensure_schema(conn)
            if not _allowed_department(conn, ident, body.department, feature_allowed):
                raise HTTPException(403, "Bạn không có quyền cấu hình ca của bộ phận này.")
            conn.execute(text("DELETE FROM vera_work_shift_definition WHERE department=:department"), {"department": body.department})
            for sort_order, (shift_code, start_time, end_time) in enumerate(normalized, start=1):
                conn.execute(text("""
                    INSERT INTO vera_work_shift_definition(
                        department, shift_code, start_time, end_time, sort_order,
                        updated_by, created_at, updated_at
                    ) VALUES (
                        :department, :shift_code, :start_time, :end_time, :sort_order,
                        :updated_by, NOW(), NOW()
                    )
                """), {
                    "department": body.department,
                    "shift_code": shift_code,
                    "start_time": start_time,
                    "end_time": end_time,
                    "sort_order": sort_order,
                    "updated_by": actor,
                })

        return {"ok": True, "saved": len(normalized), "message": "Đã cập nhật cấu hình ca làm việc."}

    @app.put("/v2/work-schedule")
    def save_work_schedule(body: ScheduleSave, ident=Depends(current_identity)):
        if _role(ident) not in {"admin", "quanly"}:
            raise HTTPException(403, "Chỉ Admin hoặc Quản lý được sắp xếp lịch làm việc.")
        actor = _actor(ident)

        unique_keys: set[tuple[date, str]] = set()
        normalized_rows: list[tuple[ScheduleRow, str, str, str, str, str]] = []
        with engine_instance().begin() as conn:
            _ensure_schema(conn)
            shift_definitions = _load_shift_definitions(conn)
            for row in body.rows:
                key = (row.work_date, row.employee_username.strip())
                if key in unique_keys:
                    raise HTTPException(400, f"Trùng lịch {row.employee_username} ngày {row.work_date:%d/%m/%Y}.")
                unique_keys.add(key)
                if not _allowed_department(conn, ident, row.department, feature_allowed):
                    raise HTTPException(403, f"Bạn không có quyền sửa lịch {row.department}.")
                start_time, end_time, overtime_shift, overtime_start_time, overtime_end_time = _validate_row(row, shift_definitions)
                normalized_rows.append((row, start_time, end_time, overtime_shift, overtime_start_time, overtime_end_time))

            for row, start_time, end_time, overtime_shift, overtime_start_time, overtime_end_time in normalized_rows:
                conn.execute(text("""
                    INSERT INTO vera_work_schedule(
                        work_date, employee_username, employee_name, department,
                        shift_code, overtime_shift, start_time, end_time,
                        overtime_start_time, overtime_end_time, note,
                        updated_by, created_at, updated_at
                    ) VALUES (
                        :work_date, :employee_username, :employee_name, :department,
                        :shift_code, :overtime_shift, :start_time, :end_time,
                        :overtime_start_time, :overtime_end_time, :note,
                        :updated_by, NOW(), NOW()
                    )
                    ON CONFLICT(work_date, employee_username) DO UPDATE SET
                        employee_name=EXCLUDED.employee_name,
                        department=EXCLUDED.department,
                        shift_code=EXCLUDED.shift_code,
                        overtime_shift=EXCLUDED.overtime_shift,
                        start_time=EXCLUDED.start_time,
                        end_time=EXCLUDED.end_time,
                        overtime_start_time=EXCLUDED.overtime_start_time,
                        overtime_end_time=EXCLUDED.overtime_end_time,
                        note=EXCLUDED.note,
                        updated_by=EXCLUDED.updated_by,
                        updated_at=NOW()
                """), {
                    "work_date": row.work_date,
                    "employee_username": row.employee_username.strip(),
                    "employee_name": row.employee_name.strip(),
                    "department": row.department,
                    "shift_code": str(row.shift_code or "").strip(),
                    "overtime_shift": overtime_shift,
                    "start_time": start_time,
                    "end_time": end_time,
                    "overtime_start_time": overtime_start_time,
                    "overtime_end_time": overtime_end_time,
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

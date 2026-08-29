"""Admin settings for legacy-compatible mid-shift breaks.

The attendance view already reads two canonical PostgreSQL settings:
- shift/shift_definitions for per-shift overrides;
- shift/shift_break_config for department fallbacks.

This module exposes a safe Admin-only editor for those exact settings so Web V2
can configure the planned break duration and FaceID clustering without touching
the old Streamlit application.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text


DEPARTMENTS = ["Nhân viên + Leader", "Lễ tân", "Quản lý", "Locker", "Tạp vụ"]


class ShiftBreakRow(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    duration_minutes: int = Field(default=90, ge=0, le=360)
    faceid_cluster_minutes: int = Field(default=10, ge=1, le=60)


class DepartmentBreakRow(BaseModel):
    department: str = Field(min_length=1, max_length=200)
    enabled: bool = False
    duration_minutes: int = Field(default=60, ge=0, le=360)


class ShiftBreakUpdate(BaseModel):
    shifts: list[ShiftBreakRow] = Field(default_factory=list, max_length=100)
    departments: list[DepartmentBreakRow] = Field(default_factory=list, max_length=30)


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _setting(conn, key: str, default: Any) -> Any:
    value = conn.execute(text("""
        SELECT value_json
        FROM vera_app_setting
        WHERE category='shift' AND setting_key=:key
        LIMIT 1
    """), {"key": key}).scalar_one_or_none()
    return default if value is None else value


def _put_setting(conn, key: str, value: Any, actor: str) -> None:
    conn.execute(text("""
        INSERT INTO vera_app_setting(
            category,setting_key,value_json,source,updated_by,revision,created_at,updated_at
        ) VALUES (
            'shift',:key,CAST(:value AS jsonb),'web_v2',:actor,1,NOW(),NOW()
        )
        ON CONFLICT(category,setting_key) DO UPDATE SET
            value_json=EXCLUDED.value_json,
            source='web_v2',
            updated_by=EXCLUDED.updated_by,
            revision=vera_app_setting.revision+1,
            updated_at=NOW()
    """), {"key": key, "value": json.dumps(value, ensure_ascii=False), "actor": actor})


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "có", "co", "bật", "bat"}
    return bool(value)


def _number(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _active_shift_payload(definitions: list[dict[str, Any]], break_config: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, item in enumerate(definitions):
        if str(item.get("Trạng thái") or "Đang dùng").strip().casefold() == "đã xóa".casefold():
            continue
        department = str(item.get("Bộ phận") or "Nhân viên + Leader").strip() or "Nhân viên + Leader"
        fallback = break_config.get(department) if isinstance(break_config.get(department), dict) else {}
        shift_id = str(item.get("ID") or item.get("Tên ca") or f"shift-{index}").strip()
        result.append({
            "id": shift_id,
            "name": str(item.get("Tên ca") or "").strip(),
            "department": department,
            "start": str(item.get("Giờ bắt đầu") or "").strip(),
            "end": str(item.get("Giờ kết thúc") or "").strip(),
            "enabled": _bool(item.get("Áp dụng nghỉ giữa ca", fallback.get("enabled", False))),
            "duration_minutes": max(0, _number(
                item.get("Duration nghỉ giữa ca (phút)", fallback.get("duration_minutes", 0)),
                _number(fallback.get("duration_minutes", 0), 0),
            )),
            "faceid_cluster_minutes": max(1, _number(item.get("Khoảng gom FaceID (phút)", 10), 10)),
        })
    return sorted(result, key=lambda row: (row["department"], row["name"], row["start"]))


def _department_payload(break_config: dict[str, Any]) -> list[dict[str, Any]]:
    names = list(DEPARTMENTS)
    for name in break_config:
        if name not in names:
            names.append(name)
    result = []
    for name in names:
        item = break_config.get(name) if isinstance(break_config.get(name), dict) else {}
        result.append({
            "department": name,
            "enabled": _bool(item.get("enabled", False)),
            "duration_minutes": max(0, _number(item.get("duration_minutes", 60), 60)),
        })
    return result


def install_shift_break_admin_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    identity_type,
) -> None:
    if getattr(app.state, "shift_break_admin_installed", False):
        return

    def ensure_admin(ident) -> None:
        if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được cài đặt nghỉ giữa ca.")

    @app.get("/v2/staff/shift-break-settings")
    def get_shift_break_settings(ident: identity_type = Depends(current_identity)):
        ensure_admin(ident)
        with engine_instance().connect() as conn:
            definitions = _as_list(_setting(conn, "shift_definitions", []))
            break_config = _as_dict(_setting(conn, "shift_break_config", {}))
        return {
            "ok": True,
            "shifts": _active_shift_payload(definitions, break_config),
            "departments": _department_payload(break_config),
            "source": "vera_app_setting.shift",
        }

    @app.put("/v2/staff/shift-break-settings")
    def put_shift_break_settings(body: ShiftBreakUpdate, ident: identity_type = Depends(current_identity)):
        ensure_admin(ident)
        actor = str(getattr(ident, "employee_username", "") or getattr(ident, "email", "") or "admin")
        shift_updates = {row.id: row for row in body.shifts}
        department_updates = {row.department.strip(): row for row in body.departments if row.department.strip()}

        with engine_instance().begin() as conn:
            definitions = _as_list(_setting(conn, "shift_definitions", []))
            break_config = _as_dict(_setting(conn, "shift_break_config", {}))

            known_ids = set()
            for index, item in enumerate(definitions):
                shift_id = str(item.get("ID") or item.get("Tên ca") or f"shift-{index}").strip()
                known_ids.add(shift_id)
                update = shift_updates.get(shift_id)
                if update is None:
                    continue
                item["Áp dụng nghỉ giữa ca"] = bool(update.enabled)
                item["Duration nghỉ giữa ca (phút)"] = int(update.duration_minutes)
                item["Khoảng gom FaceID (phút)"] = int(update.faceid_cluster_minutes)

            unknown = sorted(set(shift_updates) - known_ids)
            if unknown:
                raise HTTPException(409, f"Ca làm việc đã thay đổi. Vui lòng Làm mới trước khi lưu: {', '.join(unknown[:5])}")

            for department, update in department_updates.items():
                current = break_config.get(department) if isinstance(break_config.get(department), dict) else {}
                current = dict(current)
                current["enabled"] = bool(update.enabled)
                current["duration_minutes"] = int(update.duration_minutes)
                break_config[department] = current

            _put_setting(conn, "shift_definitions", definitions, actor)
            _put_setting(conn, "shift_break_config", break_config, actor)

        return {
            "ok": True,
            "message": "Đã lưu cài đặt nghỉ giữa ca. Chấm công sẽ dùng cấu hình mới ngay lần tải tiếp theo.",
            "saved_shifts": len(shift_updates),
            "saved_departments": len(department_updates),
        }

    app.state.shift_break_admin_installed = True

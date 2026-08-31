"""System display-name support for VERA Web V2.

The login/account key (employees.username) remains unchanged. Admin can edit a
separate system display name used by work-schedule screens, so renaming a person
never breaks authentication, leave history, payroll links, or attendance keys.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

import vera_web_v2_work_schedule as work_schedule


RELEASE = "system-employee-name-2026-08-31-v1"
_ORIGINAL_EMPLOYEE_CATALOG = work_schedule._employee_catalog


class SystemNameUpdate(BaseModel):
    system_name: str = Field(min_length=1, max_length=200)


def _clean_name(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _system_names(conn, usernames: list[str]) -> dict[str, str]:
    clean = sorted({str(item or "").strip() for item in usernames if str(item or "").strip()})
    if not clean:
        return {}
    rows = conn.execute(text("""
        SELECT username,
               COALESCE(NULLIF(BTRIM(payload->>'Tên hệ thống'), ''), username) AS system_name
        FROM employees
        WHERE username = ANY(:usernames)
    """), {"usernames": clean}).mappings().all()
    return {str(row["username"]): _clean_name(row["system_name"]) for row in rows}


def install_system_name_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    identity_type,
) -> None:
    if getattr(app.state, "system_name_installed", False):
        return

    def employee_catalog_with_system_name(conn, department: str):
        rows = _ORIGINAL_EMPLOYEE_CATALOG(conn, department)
        names = _system_names(conn, [row.get("username", "") for row in rows])
        for row in rows:
            username = str(row.get("username") or "")
            row["system_name"] = names.get(username) or username
        return rows

    # Existing work-schedule route resolves this global at request time, so this
    # safely enriches its employee directory without replacing the route itself.
    work_schedule._employee_catalog = employee_catalog_with_system_name

    @app.patch("/v2/staff/{username}/system-name")
    def update_system_name(
        username: str,
        payload: SystemNameUpdate,
        ident: identity_type = Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role != "admin":
            raise HTTPException(403, "Chỉ Admin được đổi tên hệ thống của nhân viên.")

        target = str(username or "").strip()
        system_name = _clean_name(payload.system_name)
        if not target:
            raise HTTPException(400, "Tài khoản nhân viên không hợp lệ.")
        if not system_name:
            raise HTTPException(400, "Tên hệ thống không được để trống.")

        actor = str(getattr(ident, "employee_username", "") or getattr(ident, "email", "") or "admin").strip()
        with engine_instance().begin() as conn:
            row = conn.execute(text("""
                SELECT username, payload
                FROM employees
                WHERE username=:username
                  AND COALESCE(payload->>'__deleted','false') <> 'true'
                FOR UPDATE
            """), {"username": target}).mappings().first()
            if not row:
                raise HTTPException(404, "Không tìm thấy nhân viên.")

            conn.execute(text("""
                UPDATE employees
                SET payload = jsonb_set(
                    COALESCE(payload, '{}'::jsonb),
                    '{Tên hệ thống}',
                    to_jsonb(CAST(:system_name AS text)),
                    true
                )
                WHERE username=:username
            """), {"username": target, "system_name": system_name})

        return {
            "ok": True,
            "release": RELEASE,
            "username": target,
            "system_name": system_name,
            "updated_by": actor,
            "login_username_unchanged": True,
        }

    @app.get("/v2/staff/system-name/health")
    def system_name_health():
        return {
            "ok": True,
            "release": RELEASE,
            "admin_edit": True,
            "login_username_unchanged": True,
            "work_schedule_uses_system_name": True,
        }

    app.state.system_name_installed = True
    app.state.system_name_release = RELEASE

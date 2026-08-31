"""System/login-name support for VERA Web V2.

Tên hệ thống is the canonical employee username.  Admin can rename any employee
(including Giám đốc/Admin), and the rename is propagated transactionally to the
VERA tables that use the employee username as an identity key.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

import vera_web_v2_work_schedule as work_schedule


RELEASE = "system-login-name-2026-08-31-v2"
_ORIGINAL_EMPLOYEE_CATALOG = work_schedule._employee_catalog


class SystemNameUpdate(BaseModel):
    system_name: str = Field(min_length=1, max_length=120)


def _clean_name(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _name_key(value: Any) -> str:
    raw = unicodedata.normalize("NFD", _clean_name(value).lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    raw = raw.replace("đ", "d")
    return re.sub(r"\s+", " ", raw).strip()


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


def _rename_reference(conn, table: str, column: str, old: str, new: str) -> int:
    # table/column are hard-coded below, never supplied by the request.
    result = conn.execute(
        text(f'UPDATE "{table}" SET "{column}"=:new WHERE "{column}"=:old'),
        {"old": old, "new": new},
    )
    return int(result.rowcount or 0)


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

    work_schedule._employee_catalog = employee_catalog_with_system_name

    @app.patch("/v2/staff/{username}/system-name")
    def update_system_name(
        username: str,
        payload: SystemNameUpdate,
        ident: identity_type = Depends(current_identity),
    ):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role != "admin":
            raise HTTPException(403, "Chỉ Admin được đổi Tên hệ thống/Tên đăng nhập của nhân viên.")

        target = _clean_name(username)
        system_name = _clean_name(payload.system_name)
        if not target:
            raise HTTPException(400, "Tài khoản nhân viên không hợp lệ.")
        if not system_name:
            raise HTTPException(400, "Tên hệ thống không được để trống.")
        if len(system_name) > 120:
            raise HTTPException(400, "Tên hệ thống tối đa 120 ký tự.")
        if any(ch in system_name for ch in ("/", "\\", "\n", "\r", "\t")):
            raise HTTPException(400, "Tên hệ thống không được chứa /, \\, xuống dòng hoặc tab.")

        actor = _clean_name(
            getattr(ident, "employee_username", "")
            or getattr(ident, "email", "")
            or "admin"
        )
        renamed_counts: dict[str, int] = {}

        with engine_instance().begin() as conn:
            # Lock the active employee directory so two simultaneous renames cannot
            # create usernames that are equivalent after login normalization.
            directory = conn.execute(text("""
                SELECT username, payload
                FROM employees
                WHERE COALESCE(payload->>'__deleted','false') <> 'true'
                ORDER BY username
                FOR UPDATE
            """)).mappings().all()
            row = next((item for item in directory if str(item["username"]) == target), None)
            if not row:
                raise HTTPException(404, "Không tìm thấy nhân viên.")

            wanted_key = _name_key(system_name)
            duplicate = next(
                (
                    str(item["username"])
                    for item in directory
                    if str(item["username"]) != target
                    and _name_key(item["username"]) == wanted_key
                ),
                "",
            )
            if duplicate:
                raise HTTPException(409, f"Tên hệ thống đã trùng với tài khoản {duplicate}.")

            if system_name != target:
                # employees.username is the canonical login key. vera_v2_user_profile
                # has an ON UPDATE CASCADE FK, so its employee_username follows this
                # update automatically and the existing Supabase auth_user_id remains.
                conn.execute(text("""
                    UPDATE employees
                    SET username=:new_username,
                        payload=jsonb_set(
                            jsonb_set(
                                COALESCE(payload, '{}'::jsonb),
                                '{Tên hệ thống}',
                                to_jsonb(CAST(:new_username AS text)),
                                true
                            ),
                            '{Tên nhân viên}',
                            to_jsonb(CAST(:new_username AS text)),
                            true
                        )
                    WHERE username=:old_username
                """), {"old_username": target, "new_username": system_name})

                # Identity-key references that do not have an FK to employees.
                for table, column in (
                    ("vera_employee_identity_document", "employee_username"),
                    ("vera_v2_active_device", "employee_username"),
                    ("vera_v2_active_device_session", "employee_username"),
                    ("vera_v2_leave_watch", "employee_username"),
                    ("vera_v2_push_subscription", "employee_username"),
                    ("vera_work_schedule", "employee_username"),
                ):
                    count = _rename_reference(conn, table, column, target, system_name)
                    if count:
                        renamed_counts[f"{table}.{column}"] = count

                # Tables that store the employee account name as employee_name.
                for table in (
                    "leave_records",
                    "vera_auto_check_event",
                    "vera_v2_leave_change_detail",
                    "vera_work_schedule",
                ):
                    count = _rename_reference(conn, table, "employee_name", target, system_name)
                    if count:
                        renamed_counts[f"{table}.employee_name"] = count
            else:
                conn.execute(text("""
                    UPDATE employees
                    SET payload=jsonb_set(
                        jsonb_set(
                            COALESCE(payload, '{}'::jsonb),
                            '{Tên hệ thống}',
                            to_jsonb(CAST(:system_name AS text)),
                            true
                        ),
                        '{Tên nhân viên}',
                        to_jsonb(CAST(:system_name AS text)),
                        true
                    )
                    WHERE username=:username
                """), {"username": target, "system_name": system_name})

        return {
            "ok": True,
            "release": RELEASE,
            "old_username": target,
            "username": system_name,
            "system_name": system_name,
            "updated_by": actor,
            "login_username_changed": system_name != target,
            "references_updated": renamed_counts,
            "message": (
                f"Đã đổi Tên hệ thống và Tên đăng nhập từ “{target}” thành “{system_name}”."
                if system_name != target
                else f"Tên hệ thống hiện là “{system_name}”."
            ),
        }

    @app.get("/v2/staff/system-name/health")
    def system_name_health():
        return {
            "ok": True,
            "release": RELEASE,
            "admin_edit_all_roles": True,
            "login_username_changes_with_system_name": True,
            "work_schedule_uses_system_name": True,
        }

    app.state.system_name_installed = True
    app.state.system_name_release = RELEASE

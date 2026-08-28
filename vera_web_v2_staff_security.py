"""Secure staff password reset and compressed identity-document storage for Web V2.

Passwords are never returned to the browser. Admin may replace a legacy VERA
password and force the employee to change it at the next Web V2 login.

Citizen-ID images are stored in PostgreSQL only after the browser compresses
them to a small raster image. Access is restricted to the employee themself or
an Admin. SVG and other active formats are intentionally rejected.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_web_v2_security import password_policy_error
from vera_web_v2_staff import CREDENTIAL_SHEET_ID


STAFF_SECURITY_RELEASE = "3.8-staff-security-identity"
MAX_IDENTITY_BYTES = 700 * 1024
IDENTITY_SIDES = {"front": "Mặt trước", "back": "Mặt sau"}
ALLOWED_IMAGE_TYPES = {"image/webp", "image/jpeg", "image/png"}


class StaffPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


def _ensure_identity_table(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_employee_identity_document (
            employee_username text NOT NULL,
            side text NOT NULL CHECK (side IN ('front','back')),
            content_type text NOT NULL,
            content bytea NOT NULL,
            size_bytes integer NOT NULL,
            sha256 text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT NOW(),
            updated_by text NOT NULL DEFAULT '',
            PRIMARY KEY (employee_username, side)
        )
    """))


def _valid_image(data: bytes, content_type: str) -> bool:
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type == "image/jpeg":
        return len(data) >= 3 and data[:3] == b"\xff\xd8\xff"
    if content_type == "image/png":
        return len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n"
    return False


def install_staff_security_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity: Callable[..., Any],
    require_feature: Callable[[Any, Any, str], None],
    norm: Callable[[Any], str],
    identity_type: type,
    google_client: Callable[[], Any],
) -> None:
    if getattr(app.state, "staff_security_routes_installed", False):
        return

    def employee_row(conn, username: str, *, for_update: bool = False) -> dict[str, Any]:
        suffix = " FOR UPDATE" if for_update else ""
        row = conn.execute(text("""
            SELECT username, full_name, role, password_value, payload, source_row,
                   remember_token_hash, remember_token_expiry
            FROM employees
            WHERE lower(btrim(username))=lower(btrim(:username))
            LIMIT 1
        """ + suffix), {"username": str(username or "").strip()}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân viên.")
        return dict(row)

    def require_identity_access(conn, ident, username: str) -> dict[str, Any]:
        row = employee_row(conn, username)
        is_admin = str(getattr(ident, "role", "") or "").lower() == "admin"
        is_self = norm(row["username"]) == norm(getattr(ident, "employee_username", ""))
        if not (is_admin or is_self):
            raise HTTPException(403, "Chỉ nhân viên đó hoặc Admin được xem Căn cước công dân.")
        return row

    @app.get("/v2/staff-security/health")
    def staff_security_health():
        return {"ok": True, "release": STAFF_SECURITY_RELEASE}

    @app.post("/v2/staff/{username}/reset-password")
    def reset_staff_password(
        username: str,
        body: StaffPasswordReset,
        ident: identity_type = Depends(current_identity),
    ):
        if str(getattr(ident, "role", "") or "").lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được reset mật khẩu nhân viên.")

        engine = engine_instance()
        conn = engine.connect()
        tx = conn.begin()
        sheet_ref = None
        sheet_row = 0
        old_sheet_password = ""
        sheet_changed = False
        try:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:employees'))"))
            require_feature(conn, ident, "employee_edit_save")
            row = employee_row(conn, username, for_update=True)
            if str(row.get("role") or "").lower() == "admin":
                raise HTTPException(400, "Không reset mật khẩu tài khoản Admin qua hồ sơ nhân viên.")

            error = password_policy_error(
                body.new_password,
                username=str(row.get("username") or ""),
                full_name=str(row.get("full_name") or ""),
            )
            if error:
                raise HTTPException(400, error)

            payload = dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}
            payload["must_change_password"] = True
            conn.execute(text("""
                UPDATE employees
                SET password_value=:password,
                    remember_token_hash='', remember_token_expiry='',
                    payload=CAST(:payload AS jsonb), updated_at=NOW()
                WHERE username=:username
            """), {
                "password": body.new_password,
                "payload": json.dumps(payload, ensure_ascii=False),
                "username": row["username"],
            })

            # Mirror the reset to the legacy credential worksheet. The browser
            # never receives this value; only the sheet and PostgreSQL are updated.
            sheet_ref = google_client().open_by_key(CREDENTIAL_SHEET_ID).get_worksheet(0)
            values = sheet_ref.get_all_values()
            for index, values_row in enumerate(values[1:], start=2):
                candidate = values_row[1] if len(values_row) > 1 else ""
                if norm(candidate) == norm(row["username"]):
                    sheet_row = index
                    old_sheet_password = values_row[2] if len(values_row) > 2 else ""
                    break
            if sheet_row < 2:
                raise RuntimeError(f"Không tìm thấy {row['username']} trong Sheet1 để đồng bộ mật khẩu.")
            sheet_ref.update(
                range_name=f"C{sheet_row}",
                values=[[body.new_password]],
                value_input_option="USER_ENTERED",
            )
            sheet_changed = True
            tx.commit()
            return {
                "ok": True,
                "message": (
                    f"Đã reset mật khẩu cho {row['username']}. Nhân viên phải đổi mật khẩu "
                    "sau lần đăng nhập kế tiếp."
                ),
            }
        except HTTPException:
            if tx.is_active:
                tx.rollback()
            if sheet_changed and sheet_ref is not None and sheet_row >= 2:
                try:
                    sheet_ref.update(
                        range_name=f"C{sheet_row}", values=[[old_sheet_password]],
                        value_input_option="USER_ENTERED",
                    )
                except Exception:
                    pass
            raise
        except Exception as exc:
            if tx.is_active:
                tx.rollback()
            if sheet_changed and sheet_ref is not None and sheet_row >= 2:
                try:
                    sheet_ref.update(
                        range_name=f"C{sheet_row}", values=[[old_sheet_password]],
                        value_input_option="USER_ENTERED",
                    )
                except Exception:
                    pass
            raise HTTPException(500, f"Không reset được mật khẩu an toàn: {type(exc).__name__}: {exc}") from exc
        finally:
            conn.close()

    @app.get("/v2/staff/{username}/identity")
    def identity_metadata(username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username)
            _ensure_identity_table(conn)
            records = conn.execute(text("""
                SELECT side, content_type, size_bytes, sha256, updated_at, updated_by
                FROM vera_employee_identity_document
                WHERE employee_username=:username
                ORDER BY side
            """), {"username": row["username"]}).mappings().all()
            by_side = {str(item["side"]): dict(item) for item in records}
            return {
                "ok": True,
                "employee_username": row["username"],
                "front": by_side.get("front"),
                "back": by_side.get("back"),
                "max_bytes": MAX_IDENTITY_BYTES,
            }

    @app.get("/v2/staff/{username}/identity/{side}")
    def identity_image(username: str, side: str, ident: identity_type = Depends(current_identity)):
        if side not in IDENTITY_SIDES:
            raise HTTPException(404, "Mặt Căn cước công dân không hợp lệ.")
        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username)
            _ensure_identity_table(conn)
            document = conn.execute(text("""
                SELECT content_type, content
                FROM vera_employee_identity_document
                WHERE employee_username=:username AND side=:side
            """), {"username": row["username"], "side": side}).mappings().first()
            if not document:
                raise HTTPException(404, f"Chưa có ảnh {IDENTITY_SIDES[side].lower()} CCCD.")
            content = bytes(document["content"])
            return Response(
                content=content,
                media_type=str(document["content_type"]),
                headers={
                    "Cache-Control": "private, no-store, max-age=0",
                    "Pragma": "no-cache",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    @app.put("/v2/staff/{username}/identity/{side}")
    async def upload_identity_image(
        username: str,
        side: str,
        request: Request,
        ident: identity_type = Depends(current_identity),
    ):
        if side not in IDENTITY_SIDES:
            raise HTTPException(404, "Mặt Căn cước công dân không hợp lệ.")
        content_type = str(request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, "Chỉ chấp nhận ảnh WebP, JPEG hoặc PNG.")
        content = await request.body()
        if not content:
            raise HTTPException(400, "Ảnh CCCD đang trống.")
        if len(content) > MAX_IDENTITY_BYTES:
            raise HTTPException(413, "Ảnh sau nén vẫn quá lớn. Vui lòng chọn ảnh rõ hơn hoặc thử lại.")
        if not _valid_image(content, content_type):
            raise HTTPException(400, "Nội dung file ảnh không hợp lệ.")

        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username)
            _ensure_identity_table(conn)
            digest = hashlib.sha256(content).hexdigest()
            conn.execute(text("""
                INSERT INTO vera_employee_identity_document(
                    employee_username, side, content_type, content, size_bytes,
                    sha256, updated_at, updated_by
                ) VALUES (
                    :username, :side, :content_type, :content, :size_bytes,
                    :sha256, NOW(), :updated_by
                )
                ON CONFLICT (employee_username, side) DO UPDATE SET
                    content_type=EXCLUDED.content_type,
                    content=EXCLUDED.content,
                    size_bytes=EXCLUDED.size_bytes,
                    sha256=EXCLUDED.sha256,
                    updated_at=NOW(),
                    updated_by=EXCLUDED.updated_by
            """), {
                "username": row["username"],
                "side": side,
                "content_type": content_type,
                "content": content,
                "size_bytes": len(content),
                "sha256": digest,
                "updated_by": str(getattr(ident, "employee_username", "") or ""),
            })
            return {
                "ok": True,
                "side": side,
                "size_bytes": len(content),
                "sha256": digest,
                "message": f"Đã lưu {IDENTITY_SIDES[side]} CCCD ({round(len(content) / 1024)} KB).",
            }

    @app.delete("/v2/staff/{username}/identity/{side}")
    def delete_identity_image(username: str, side: str, ident: identity_type = Depends(current_identity)):
        if side not in IDENTITY_SIDES:
            raise HTTPException(404, "Mặt Căn cước công dân không hợp lệ.")
        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username)
            _ensure_identity_table(conn)
            result = conn.execute(text("""
                DELETE FROM vera_employee_identity_document
                WHERE employee_username=:username AND side=:side
            """), {"username": row["username"], "side": side})
            return {
                "ok": True,
                "deleted": int(result.rowcount or 0),
                "message": f"Đã xóa ảnh {IDENTITY_SIDES[side].lower()} CCCD.",
            }

    app.state.staff_security_routes_installed = True
    app.state.staff_security_release = STAFF_SECURITY_RELEASE

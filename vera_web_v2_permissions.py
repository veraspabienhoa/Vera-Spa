"""Granular role/account permissions for VERA SPA Web V2."""
from __future__ import annotations

from datetime import datetime
import json
import os
from typing import Any, Callable

import gspread
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text


CREDENTIAL_SHEET_ID = os.getenv(
    "VERA_CREDENTIAL_SHEET_ID", "1DGXy3kPyMPwtz-3CnG8i6BiQbXFDApasoXVFzSmUe24"
)
WORKSHEET = "PhanQuyenChucNang"
HEADERS = ["Phạm vi", "Đối tượng", "Chức năng", "Cho phép", "Ngày cập nhật", "Giờ cập nhật", "Người cập nhật"]
ROLES = ["quanly", "letan", "leader", "nhanvien", "locker", "tapvu"]

FEATURE_GROUPS: dict[str, dict[str, str]] = {
    "Bảng tua": {
        "tour": "Xem Bảng tua", "tour_refresh": "Làm mới Bảng tua",
        "tour_leave_sync": "Cập nhật lịch nghỉ vào TourVera",
    },
    "Lịch nghỉ": {
        "leave": "Xem Đăng ký nghỉ", "leave_manage": "Xem Quản lý lịch nghỉ",
        "leave_create": "Đăng ký / ghi lịch nghỉ",
        "leave_export": "Export Excel", "leave_email": "Gửi email báo cáo",
        "leave_detail_edit": "Sửa trực tiếp danh sách", "leave_detail_delete": "Xóa dòng trong danh sách",
        "leave_manage_edit": "Quản lý lịch nghỉ · Sửa", "leave_manage_delete": "Quản lý lịch nghỉ · Xóa",
        "leave_today_khong_phep_edit_delete": "Sửa/Xóa không phép ngày hiện tại",
        "employee_penalty_view": "Xem tiền phạt vi phạm",
    },
    "Phép năm / Làm đẹp / Nghỉ việc": {
        "long_leave": "Xem khu vực đơn", "long_leave_form": "Gửi Phép năm / Nghỉ làm đẹp",
        "resignation_form": "Gửi Đơn xin nghỉ việc", "long_leave_stats": "Xem danh sách đã duyệt",
        "long_leave_document": "Quản lý tài liệu", "long_leave_pause": "Tạm dừng / mở nhận đơn",
        "long_leave_manual_add": "Thêm đơn thủ công",
        "long_leave_approve": "Duyệt đơn", "long_leave_reject": "Không duyệt đơn",
        "long_leave_end": "Kết thúc nghỉ", "long_leave_delete": "Xóa bản ghi",
        "long_leave_export": "Export đơn",
    },
    "Nhân viên": {
        "staff_list": "Xem danh sách nhân viên", "staff_export": "Export danh sách",
        "staff_import": "Import danh sách", "employee_add": "Mở form thêm nhân viên",
        "employee_add_save": "Lưu nhân viên mới", "employee_edit": "Mở chỉnh sửa nhân viên",
        "employee_edit_save": "Lưu chỉnh sửa hồ sơ", "employment_status": "Xem trạng thái làm việc",
        "employment_status_edit": "Thay đổi trạng thái làm việc", "employee_delete": "Mở chức năng xóa",
        "employee_delete_confirm": "Xác nhận xóa tài khoản", "account_lock": "Xem khóa đăng nhập",
        "employees_visibility_manage": "Tạm ẩn / hiện nhân viên",
        "account_lock_edit": "Khóa / mở đăng nhập", "registration_lock": "Xem khóa đăng ký",
        "registration_lock_edit": "Khóa / mở quyền đăng ký", "shift": "Xem chia ca",
        "shift_definition_edit": "Tạo / sửa / xóa ca", "shift_break_config_edit": "Cấu hình nghỉ giữa ca",
        "shift_assignment_edit": "Sửa phân ca", "shift_plan_edit": "Lưu kế hoạch hẹn ngày",
        "shift_assignment_clear": "Xóa phân ca", "shift_import": "Import phân ca", "shift_export_pdf": "Export ca",
    },
    "Hợp đồng": {
        "contract_1_view": "Xem Hợp đồng lao động",
        "contract_1_export_self": "Xuất hợp đồng của chính mình",
        "contract_1_export_bulk": "Xuất hợp đồng theo nhân viên / bộ phận / toàn bộ",
        "contract_1_template_edit": "Chỉnh sửa nội dung mẫu hợp đồng",
        "contract_1_settings_edit": "Chỉnh người đại diện, thời hạn, ngày ký và mức lương hợp đồng",
    },
    "Nội quy": {
        "official_rules_view": "Xem Nội quy", "official_rules_edit": "Sửa Nội quy",
        "official_rules_export": "Export Nội quy", "official_rules_import": "Import Nội quy",
    },
    "Bảng lương": {
        "payroll": "Xem Bảng lương", "payroll_history": "Xem lịch sử bảng lương",
        "payroll_calculate": "Tính / tính lại", "payroll_config_edit": "Sửa cấu hình",
        "payroll_penalty_obligation": "Quản lý nghĩa vụ vi phạm", "payroll_save": "Lưu kỳ lương",
        "payroll_export": "Export Excel", "payroll_email": "Gửi email",
        "payroll_history_edit": "Cập nhật / ghi đè lịch sử", "payroll_history_delete": "Xóa bản lưu",
    },
    "Chấm công / hệ thống": {
        "snapshot_today": "Xem Chấm công", "snapshot_export": "Export Chấm công",
        "auto_penalty": "Xem Auto Check", "auto_penalty_control": "Tạm dừng / mở Auto Check",
        "auto_penalty_run": "Chạy Auto Check thủ công", "sync": "Xem Đồng bộ dữ liệu",
        "sync_timesoft_fetch": "Lấy dữ liệu TimeSoft", "sync_timesoft_api": "Cấu hình API TimeSoft",
        "sync_leave_export": "Tải Excel lịch nghỉ", "sync_postgres": "Đồng bộ Google Sheets sang PostgreSQL",
        "column_config": "Xem giao diện tùy chỉnh", "column_config_edit": "Lưu cấu hình giao diện",
        "profile": "Xem hồ sơ cá nhân", "profile_edit": "Tự cập nhật hồ sơ / mật khẩu",
        "birthday": "Xem sinh nhật", "birthday_check": "Chạy kiểm tra sinh nhật",
        "guide_manage": "Quản lý tài liệu hướng dẫn",
        "audit_admin_view": "Xem nhật ký thay đổi hệ thống", "permission_admin": "Quản trị phân quyền",
        "storage_admin_view": "Xem quản lý bộ nhớ", "storage_export": "Export dữ liệu lưu trữ",
        "storage_delete": "Xóa dữ liệu lưu trữ theo thời gian",
    },
}
FEATURES = {key: label for group in FEATURE_GROUPS.values() for key, label in group.items()}

FRONTDESK = {
    "tour", "tour_refresh", "tour_leave_sync", "leave", "leave_manage", "leave_create", "leave_export", "leave_email", "leave_detail_edit", "leave_detail_delete",
    "leave_manage_edit", "leave_manage_delete", "leave_today_khong_phep_edit_delete",
    "long_leave", "long_leave_stats", "staff_list", "staff_export", "staff_import", "employee_add",
    "employee_add_save", "employee_edit", "employee_edit_save", "employment_status", "employment_status_edit",
    "employee_delete", "employee_delete_confirm", "shift", "shift_assignment_edit", "shift_import", "shift_export_pdf",
    "account_lock", "account_lock_edit", "registration_lock", "registration_lock_edit",
    "profile", "profile_edit", "birthday", "birthday_check",
    "contract_1_view", "contract_1_export_self",
}
EMPLOYEE = {
    "tour", "tour_refresh", "leave", "leave_manage", "leave_create", "leave_export", "leave_detail_edit", "leave_detail_delete",
    "leave_manage_edit", "leave_manage_delete", "long_leave", "long_leave_form", "resignation_form",
    "long_leave_document", "profile", "profile_edit", "birthday", "birthday_check",
    "contract_1_view", "contract_1_export_self",
}
DEFAULT_ROLE_FEATURES = {
    "admin": set(FEATURES), "quanly": set(FRONTDESK), "letan": set(FRONTDESK),
    "leader": set(EMPLOYEE), "nhanvien": set(EMPLOYEE),
    "locker": {"tour", "tour_refresh", "profile", "profile_edit", "birthday", "birthday_check", "resignation_form", "contract_1_view", "contract_1_export_self"},
    "tapvu": {"profile", "profile_edit", "birthday", "birthday_check", "resignation_form", "contract_1_view", "contract_1_export_self"},
}


class PermissionUpdate(BaseModel):
    allowed_features: list[str] = Field(default_factory=list, max_length=200)
    inherit: bool = False
    expected_revision: int | None = Field(default=None, ge=0)


def _payload(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {"roles": [], "accounts": []}


def _scope_rows(payload: dict[str, Any], scope: str, target: str) -> dict[str, bool]:
    rows = payload.get("accounts" if scope == "account" else "roles", []) or []
    target_key = target.casefold().strip()
    return {
        str(item.get("feature") or ""): bool(item.get("allowed"))
        for item in rows if isinstance(item, dict) and str(item.get("target") or "").casefold().strip() == target_key
    }


def install_permission_routes(
    app, *, engine_instance: Callable[[], Any], current_identity,
    google_client: Callable[[], Any], identity_type, vn_tz,
    permissions_changed: Callable[[], None] | None = None,
):
    def require_admin(ident):
        if str(ident.role or "").lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được quản trị phân quyền.")

    @app.get("/v2/permissions")
    def permissions_overview(ident: identity_type = Depends(current_identity)):
        require_admin(ident)
        with engine_instance().connect() as conn:
            row = conn.execute(text("""
                SELECT value_json, revision FROM vera_app_setting
                WHERE category='authorization' AND setting_key='feature_permissions' LIMIT 1
            """)).mappings().first()
            payload = _payload(row.get("value_json") if row else None)
            accounts = conn.execute(text("""
                SELECT username, COALESCE(full_name,'') full_name, lower(COALESCE(role,'')) role
                FROM employees
                WHERE COALESCE(payload->>'__deleted','false') <> 'true'
                ORDER BY lower(username)
            """)).mappings().all()
        return {
            "groups": FEATURE_GROUPS, "roles": ROLES, "accounts": [dict(item) for item in accounts],
            "role_overrides": {role: _scope_rows(payload, "role", role) for role in ROLES},
            "account_overrides": {item["username"]: _scope_rows(payload, "account", item["username"]) for item in accounts},
            "defaults": {role: sorted(DEFAULT_ROLE_FEATURES.get(role, set())) for role in ROLES},
            "revision": int(row.get("revision") or 0) if row else 0,
        }

    @app.put("/v2/permissions/{scope}/{target}")
    def save_permissions(scope: str, target: str, body: PermissionUpdate, ident: identity_type = Depends(current_identity)):
        require_admin(ident)
        if scope not in {"role", "account"}:
            raise HTTPException(400, "Phạm vi phân quyền không hợp lệ.")
        target = target.strip()
        if not target:
            raise HTTPException(400, "Thiếu vai trò hoặc tài khoản cần phân quyền.")
        if scope == "role" and target.lower() not in ROLES:
            raise HTTPException(400, "Vai trò không hợp lệ hoặc vai trò Admin không được sửa.")
        unknown = sorted(set(body.allowed_features) - set(FEATURES))
        if unknown:
            raise HTTPException(400, f"Có quyền không hợp lệ: {', '.join(unknown)}")

        conn = engine_instance().connect()
        tx = conn.begin()
        try:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:v2:feature_permissions'))"))
            row = conn.execute(text("""
                SELECT value_json, revision FROM vera_app_setting
                WHERE category='authorization' AND setting_key='feature_permissions'
                FOR UPDATE
            """)).mappings().first()
            revision = int(row.get("revision") or 0) if row else 0
            if body.expected_revision is not None and body.expected_revision != revision:
                raise HTTPException(409, "Phân quyền đã thay đổi ở thiết bị khác. Hãy Làm mới rồi lưu lại.")
            payload = _payload(row.get("value_json") if row else None)
            key = "accounts" if scope == "account" else "roles"
            keep = [
                item for item in payload.get(key, []) or []
                if str(item.get("target") or "").casefold().strip() != target.casefold()
                or str(item.get("feature") or "") not in FEATURES
            ]
            now = datetime.now(vn_tz)
            if not (scope == "account" and body.inherit):
                allowed = set(body.allowed_features)
                keep.extend({"target": target, "feature": feature, "allowed": feature in allowed} for feature in FEATURES)
            payload[key] = keep
            payload.setdefault("roles" if key == "accounts" else "accounts", [])

            mirror = [HEADERS]
            for mirror_scope, items in (("Vai trò", payload.get("roles", [])), ("Tài khoản", payload.get("accounts", []))):
                for item in items or []:
                    mirror.append([
                        mirror_scope, item.get("target", ""), item.get("feature", ""),
                        "TRUE" if item.get("allowed") else "FALSE", now.strftime("%d/%m/%Y"),
                        now.strftime("%H:%M:%S"), ident.employee_username,
                    ])
            conn.execute(text("""
                INSERT INTO vera_app_setting(category, setting_key, value_json, source, updated_by, revision, created_at, updated_at)
                VALUES ('authorization','feature_permissions',CAST(:payload AS jsonb),'web_v2',:updated_by,1,NOW(),NOW())
                ON CONFLICT (category, setting_key) DO UPDATE
                SET value_json=EXCLUDED.value_json, source='web_v2', updated_by=EXCLUDED.updated_by,
                    revision=vera_app_setting.revision+1, updated_at=NOW()
            """), {"payload": json.dumps(payload, ensure_ascii=False), "updated_by": ident.employee_username})
            tx.commit()
            if permissions_changed is not None:
                permissions_changed()

            # PostgreSQL is the canonical permission store. The legacy Google
            # worksheet is only a compatibility mirror and must never make a
            # valid permission change fail (for example, when VPS credentials
            # are temporarily missing or malformed).
            mirror_warning = ""
            try:
                sheet = google_client().open_by_key(CREDENTIAL_SHEET_ID)
                try:
                    ws = sheet.worksheet(WORKSHEET)
                except gspread.WorksheetNotFound:
                    ws = sheet.add_worksheet(title=WORKSHEET, rows=1000, cols=len(HEADERS))
                ws.clear()
                ws.update(range_name=f"A1:G{len(mirror)}", values=mirror, value_input_option="USER_ENTERED")
            except Exception as mirror_exc:
                mirror_warning = (
                    "Đã lưu PostgreSQL; chưa đồng bộ được bản sao Google Sheets "
                    f"({type(mirror_exc).__name__})."
                )
            return {
                "ok": True,
                "message": "Đã lưu phân quyền THÀNH CÔNG",
                "revision": revision + 1,
                "mirror_pending": bool(mirror_warning),
                "warnings": [mirror_warning] if mirror_warning else [],
            }
        except HTTPException:
            if tx.is_active: tx.rollback()
            raise
        except Exception as exc:
            if tx.is_active: tx.rollback()
            raise HTTPException(500, f"Không lưu được phân quyền an toàn: {type(exc).__name__}: {exc}") from exc
        finally:
            conn.close()

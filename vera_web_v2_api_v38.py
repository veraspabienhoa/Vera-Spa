"""Web V2 shared API entrypoint + Payroll 3.8 installers."""
from __future__ import annotations

from vera_web_v2_runtime_env import load_managed_runtime_environment

# This must run before importing the shared API because several modules read
# database/Auth settings while their module globals are initialized.
load_managed_runtime_environment()

from fastapi import HTTPException
from sqlalchemy import text

import vera_web_v2_api_shared as _shared
import vera_web_v2_admin_audit_archive as _audit_archive
import vera_web_v2_contracts as _contracts
import vera_web_v2_profile as _profile
import vera_web_v2_staff as _staff
import vera_web_v2_staff_security as _staff_security
import vera_web_v2_staff_status_sort as _staff_sort
import vera_web_v2_snapshot as _snapshot
from vera_web_v2_accumulation_permission import install_accumulation_permission
from vera_web_v2_admin_audit_archive import install_admin_audit_archive_routes
from vera_web_v2_admin_change_push import install_admin_change_push
from vera_web_v2_auth_gateway import install_auth_gateway
from vera_web_v2_attendance_v42 import install_attendance_v42
from vera_web_v2_attendance_break_window import install_attendance_break_window
from vera_web_v2_attendance_break_alerts import install_attendance_break_alerts
from vera_web_v2_attendance_break_dispatch import install_attendance_break_dispatch
from vera_web_v2_attendance_policy_patch import install_attendance_policy_patch
from vera_web_v2_department_attendance import install_department_attendance_routes
from vera_web_v2_department_payroll import install_department_payroll_routes
from vera_web_v2_contracts import install_contract_1_routes
from vera_web_v2_break_alert_control import install_break_alert_control
from vera_web_v2_break_return_penalty import install_break_return_penalty
from vera_web_v2_auto_check import install_auto_check_routes
from vera_web_v2_excel_export_style import install_excel_export_style
from vera_web_v2_leave_preview import install_leave_preview_routes
from vera_web_v2_leave_source_export import install_leave_source_export_routes
from vera_web_v2_leave_day_stats import install_leave_day_stats_routes
from vera_web_v2_leave_sync_queue import install_leave_sync_queue
from vera_web_v2_leave_violation_split import install_leave_violation_split_routes
from vera_web_v2_letan_leave_guard import install_letan_leave_guard
from vera_web_v2_long_leave_admin import install_long_leave_admin_routes
from vera_web_v2_operations_v41 import install_operations_v41
from vera_web_v2_outside_leave_rule import install_outside_leave_rule
from vera_web_v2_payroll_debt_sync import install_payroll_debt_sync_routes
from vera_web_v2_payroll_enhancements import install_payroll_enhancement_routes
from vera_web_v2_payroll_personal import install_payroll_personal_defaults, install_payroll_personal_routes
from vera_web_v2_payroll_saved_edit import install_payroll_saved_edit_routes
from vera_web_v2_payroll_timesoft_auto import install_payroll_timesoft_auto_routes
from vera_web_v2_payroll_v38 import PAYROLL_V38_RELEASE, install_payroll_v38_routes
from vera_web_v2_policy_v39 import install_policy_v39
from vera_web_v2_policy_v40 import install_policy_v40
from vera_web_v2_people import invalidate_tour_cache
from vera_web_v2_purchase_reconcile import install_purchase_reconcile_routes
from vera_web_v2_purchase_reconcile_alert_check import install_purchase_reconcile_alert_check
from vera_web_v2_purchase_reconcile_v2 import install_purchase_reconcile_v2
from vera_web_v2_revenue_leave_list import install_revenue_leave_list_routes
from vera_web_v2_revenue_report_target import install_revenue_report_target
from vera_web_v2_shift_break_admin import install_shift_break_admin_routes
from vera_web_v2_staff_security import install_staff_security_routes
from vera_web_v2_staff_status_sort import install_staff_status_sort
from vera_web_v2_support_shift_break import install_support_shift_break
from vera_web_v2_system_name import install_system_name_routes
from vera_web_v2_tour_leave_sync import install_tour_leave_sync_routes
from vera_web_v2_tour_source import install_tour_source_routes
from vera_web_v2_violation_unlimited import install_violation_unlimited
from vera_web_v2_work_schedule import install_work_schedule_routes
from vera_web_v2_work_schedule_permissions import install_work_schedule_permissions

_api = _shared._api
install_work_schedule_permissions()
install_payroll_personal_defaults(api_module=_api)
_audit_archive.identity_type = _api.Identity
_audit_archive.leave_update_type = _api.LeaveUpdate
_audit_archive.leave_delete_type = _api.LeaveDelete
_staff_sort.identity_type = _api.Identity


# CCCD images remain required/stored normally, but Web V2 no longer performs
# OCR, auto-fill, or name/number matching against image text. Employees enter
# identification fields manually. Keep this override here so every already-
# installed profile/staff route and the contract route use the same behavior.
def _no_cccd_ocr(*_args, **_kwargs):
    return {}


_staff_security._extract_cccd_fields = _no_cccd_ocr
_staff_security.validate_saved_identity_matches = _no_cccd_ocr
_profile.validate_saved_identity_matches = _no_cccd_ocr
_staff.validate_saved_identity_matches = _no_cccd_ocr
_contracts._extract_cccd_fields = _no_cccd_ocr


def _login_profile(employee_username: str) -> dict:
    """Build the verified UI profile without a second Supabase /auth/user hop."""
    with _api._engine_instance().connect() as conn:
        row = conn.execute(text("""
            SELECT username, COALESCE(role,'nhanvien'), COALESCE(full_name,''),
                   COALESCE(email,''),
                   lower(COALESCE(payload->>'must_change_password','')) IN ('1','true','yes','y')
            FROM employees
            WHERE username=:username
              AND COALESCE(login_locked,false)=false
              AND COALESCE(
                    payload->>'Trạng thái làm việc',
                    payload->>'employment_status',
                    'Đang làm việc'
                  ) = 'Đang làm việc'
            LIMIT 1
        """), {"username": employee_username}).first()
        if not row:
            raise HTTPException(403, "Tài khoản chưa được liên kết với nhân viên VERA đang hoạt động.")
        ident = _api.Identity(
            auth_user_id="",
            employee_username=row[0],
            role=str(row[1] or "nhanvien").lower(),
            full_name=row[2],
            email=row[3],
            must_change_password=bool(row[4]),
        )
        permission_payload = _api._permission_payload(conn)
        permissions = {
            feature: _api._feature_allowed(conn, ident, feature, permission_payload)
            for feature in _api.WEB_V2_FEATURES
        }
        registration_locked = _api._registration_role_locked(conn, ident.role)
    return {
        **ident.model_dump(),
        "permissions": permissions,
        "registration_locked": registration_locked,
        "is_active": True,
    }


install_auth_gateway(
    _shared.app,
    supabase_url=_api.SUPABASE_URL,
    supabase_anon_key=_api.SUPABASE_ANON_KEY,
    profile_loader=_login_profile,
    verified_token_callback=_api.remember_verified_token,
)

install_payroll_v38_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, identity_type=_api.Identity, google_client=_api._google_client)
install_department_payroll_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, norm=_api._norm)
install_payroll_timesoft_auto_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, norm=_api._norm)
install_payroll_debt_sync_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, google_client=_api._google_client)
install_payroll_enhancement_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, identity_type=_api.Identity)
install_payroll_personal_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, identity_type=_api.Identity, norm=_api._norm)
install_accumulation_permission(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, api_module=_api)
install_payroll_saved_edit_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, identity_type=_api.Identity)
install_staff_security_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, identity_type=_api.Identity)
install_contract_1_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, feature_allowed=_api._feature_allowed, norm=_api._norm, identity_type=_api.Identity)
install_staff_status_sort(_shared.app, current_identity=_api.current_identity, identity_type=_api.Identity)
install_shift_break_admin_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, identity_type=_api.Identity)
install_system_name_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, identity_type=_api.Identity)
install_tour_leave_sync_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, google_client=_api._google_client, leave_sheet_id=_api.LEAVE_SHEET_ID, vn_tz=_api.VN_TZ, invalidate_tour_cache=invalidate_tour_cache)
install_tour_source_routes(_shared.app, current_identity=_api.current_identity, identity_type=_api.Identity, invalidate_tour_cache=invalidate_tour_cache)
install_leave_source_export_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, norm=_api._norm, google_client=_api._google_client, leave_sheet_id=_api.LEAVE_SHEET_ID)
install_work_schedule_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, feature_allowed=_api._feature_allowed)
install_auto_check_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity)
install_policy_v39(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, vn_tz=_api.VN_TZ)
install_policy_v40(_shared.app, shared_module=_shared)
install_violation_unlimited(_shared.app, shared_module=_shared)
install_leave_day_stats_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, feature_allowed=_api._feature_allowed, daily_quota_config=_api._daily_quota_config, employee_name_matches=_api._employee_name_matches, norm=_api._norm, weekday_short_label=_api._weekday_short_label, identity_type=_api.Identity)
install_leave_violation_split_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, feature_allowed=_api._feature_allowed, policy_rows=_api._policy_rows, field=_api._field, reason_item=_api._reason_item, role_tokens=_api._role_tokens, day_allowed=_api._day_allowed, norm=_api._norm)
install_leave_preview_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, feature_allowed=_api._feature_allowed, validate_and_prepare=_shared._validate_and_prepare, identity_type=_api.Identity)
install_long_leave_admin_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, identity_type=_api.Identity, norm=_api._norm, google_client=_api._google_client, leave_sheet_id=_api.LEAVE_SHEET_ID, vn_tz=_api.VN_TZ, validate_and_prepare=_shared._validate_and_prepare, leave_create_type=_api.LeaveCreate, sheet_row_for_record=_api._sheet_row_for_record, insert_record=_api._insert_record)
install_admin_audit_archive_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, leave_update_type=_api.LeaveUpdate, leave_delete_type=_api.LeaveDelete)
install_leave_sync_queue(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, validate_and_prepare=_shared._validate_and_prepare, identity_type=_api.Identity, api_module=_api)
install_letan_leave_guard(_shared.app, api_module=_api, vn_tz=_api.VN_TZ)
install_revenue_leave_list_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, feature_allowed=_api._feature_allowed, norm=_api._norm, progressive_key=_api._progressive_key, google_client=_api._google_client)
install_revenue_report_target(_shared.app, current_identity=_api.current_identity)
install_purchase_reconcile_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, google_client=_api._google_client)
install_purchase_reconcile_v2(_shared.app, engine_instance=_api._engine_instance, api_module=_api, current_identity=_api.current_identity, identity_type=_api.Identity)
install_purchase_reconcile_alert_check(_shared.app, engine_instance=_api._engine_instance, api_module=_api, current_identity=_api.current_identity, identity_type=_api.Identity, norm=_api._norm, google_client=_api._google_client)

install_attendance_v42(_shared.app, engine_instance=_api._engine_instance)
install_department_attendance_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, identity_type=_api.Identity)
install_attendance_break_window(_shared.app)
install_attendance_break_alerts(_shared.app, engine_instance=_api._engine_instance, api_module=_api, current_identity=_api.current_identity, identity_type=_api.Identity, vn_tz=_api.VN_TZ)
install_attendance_policy_patch()
install_outside_leave_rule(_shared.app, engine_instance=_api._engine_instance)
# Apply recognized Hỗ trợ-ca schedules to every employee after the full attendance
# chain is installed. This removes only false 'đi trễ' break restrictions.
install_support_shift_break(_shared.app, engine_instance=_api._engine_instance, snapshot_module=_snapshot)
install_break_alert_control(_shared.app, engine_instance=_api._engine_instance, api_module=_api, current_identity=_api.current_identity, identity_type=_api.Identity)
install_break_return_penalty(_shared.app, engine_instance=_api._engine_instance, api_module=_api, vn_tz=_api.VN_TZ)
install_attendance_break_dispatch(_shared.app, engine_instance=_api._engine_instance, api_module=_api, vn_tz=_api.VN_TZ)
install_operations_v41(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity)
install_admin_change_push(_shared.app, engine_instance=_api._engine_instance, api_module=_api, current_identity=_api.current_identity, identity_type=_api.Identity, leave_create_type=_api.LeaveCreate, leave_update_type=_api.LeaveUpdate, leave_delete_type=_api.LeaveDelete)
install_excel_export_style(_shared.app)

app = _shared.app
app.version = PAYROLL_V38_RELEASE

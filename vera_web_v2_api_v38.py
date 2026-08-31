"""Web V2 shared API entrypoint + Payroll 3.8 installers."""
from __future__ import annotations

import vera_web_v2_api_shared as _shared
import vera_web_v2_admin_audit_archive as _audit_archive
import vera_web_v2_staff_status_sort as _staff_sort
from vera_web_v2_admin_audit_archive import install_admin_audit_archive_routes
from vera_web_v2_admin_change_push import install_admin_change_push
from vera_web_v2_attendance_v42 import install_attendance_v42
from vera_web_v2_auto_check import install_auto_check_routes
from vera_web_v2_excel_export_style import install_excel_export_style
from vera_web_v2_leave_preview import install_leave_preview_routes
from vera_web_v2_leave_day_stats import install_leave_day_stats_routes
from vera_web_v2_leave_violation_split import install_leave_violation_split_routes
from vera_web_v2_letan_leave_guard import install_letan_leave_guard
from vera_web_v2_long_leave_admin import install_long_leave_admin_routes
from vera_web_v2_operations_v41 import install_operations_v41
from vera_web_v2_payroll_debt_sync import install_payroll_debt_sync_routes
from vera_web_v2_payroll_enhancements import install_payroll_enhancement_routes
from vera_web_v2_payroll_saved_edit import install_payroll_saved_edit_routes
from vera_web_v2_payroll_timesoft_auto import install_payroll_timesoft_auto_routes
from vera_web_v2_payroll_v38 import PAYROLL_V38_RELEASE, install_payroll_v38_routes
from vera_web_v2_policy_v39 import install_policy_v39
from vera_web_v2_policy_v40 import install_policy_v40
from vera_web_v2_purchase_reconcile import install_purchase_reconcile_routes
from vera_web_v2_purchase_reconcile_alert_check import install_purchase_reconcile_alert_check
from vera_web_v2_purchase_reconcile_v2 import install_purchase_reconcile_v2
from vera_web_v2_revenue_leave_list import install_revenue_leave_list_routes
from vera_web_v2_shift_break_admin import install_shift_break_admin_routes
from vera_web_v2_single_device import install_single_device_guard
from vera_web_v2_staff_security import install_staff_security_routes
from vera_web_v2_staff_status_sort import install_staff_status_sort
from vera_web_v2_violation_unlimited import install_violation_unlimited
from vera_web_v2_work_schedule import install_work_schedule_routes

_api = _shared._api

_audit_archive.identity_type = _api.Identity
_audit_archive.leave_update_type = _api.LeaveUpdate
_audit_archive.leave_delete_type = _api.LeaveDelete
_staff_sort.identity_type = _api.Identity

install_payroll_v38_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, identity_type=_api.Identity, google_client=_api._google_client)
install_payroll_timesoft_auto_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, norm=_api._norm)
install_payroll_debt_sync_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, google_client=_api._google_client)
install_payroll_enhancement_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, identity_type=_api.Identity)
install_payroll_saved_edit_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, identity_type=_api.Identity)
install_staff_security_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, norm=_api._norm, identity_type=_api.Identity)
install_staff_status_sort(_shared.app, current_identity=_api.current_identity, identity_type=_api.Identity)
install_shift_break_admin_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, identity_type=_api.Identity)
install_work_schedule_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity)
install_auto_check_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity)
install_policy_v39(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, vn_tz=_api.VN_TZ)

# Policy 4.0 narrows the monthly weekend cap to Group 3 and permits only
# Quản lý/Lễ tân to backfill past rows whose canonical Loại nghỉ is Vi phạm.
# Install before preview/write wrappers so every Web V2 registration path uses it.
install_policy_v40(_shared.app, shared_module=_shared)

# Nội quy Loại nghỉ is authoritative for same-day grouping. Vi phạm rows have
# no per-employee/day count limit even when their reason text contains KHÔNG phép.
install_violation_unlimited(_shared.app, shared_module=_shared)

install_leave_day_stats_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    feature_allowed=_api._feature_allowed,
    daily_quota_config=_api._daily_quota_config,
    employee_name_matches=_api._employee_name_matches,
    norm=_api._norm,
    weekday_short_label=_api._weekday_short_label,
    identity_type=_api.Identity,
)

install_leave_violation_split_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, feature_allowed=_api._feature_allowed, policy_rows=_api._policy_rows, field=_api._field, reason_item=_api._reason_item, role_tokens=_api._role_tokens, day_allowed=_api._day_allowed, norm=_api._norm)
install_leave_preview_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, feature_allowed=_api._feature_allowed, validate_and_prepare=_shared._validate_and_prepare, identity_type=_api.Identity)
install_long_leave_admin_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, identity_type=_api.Identity, norm=_api._norm, google_client=_api._google_client, leave_sheet_id=_api.LEAVE_SHEET_ID, vn_tz=_api.VN_TZ, validate_and_prepare=_shared._validate_and_prepare, leave_create_type=_api.LeaveCreate, sheet_row_for_record=_api._sheet_row_for_record, insert_record=_api._insert_record)
install_admin_audit_archive_routes(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, require_feature=_api._require_feature, identity_type=_api.Identity, leave_update_type=_api.LeaveUpdate, leave_delete_type=_api.LeaveDelete)
install_letan_leave_guard(_shared.app, api_module=_api, vn_tz=_api.VN_TZ)

install_revenue_leave_list_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    feature_allowed=_api._feature_allowed,
    norm=_api._norm,
    progressive_key=_api._progressive_key,
    google_client=_api._google_client,
)

install_purchase_reconcile_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    norm=_api._norm,
    google_client=_api._google_client,
)
install_purchase_reconcile_v2(
    _shared.app,
    engine_instance=_api._engine_instance,
    api_module=_api,
    current_identity=_api.current_identity,
    identity_type=_api.Identity,
)
install_purchase_reconcile_alert_check(
    _shared.app,
    engine_instance=_api._engine_instance,
    api_module=_api,
    current_identity=_api.current_identity,
    identity_type=_api.Identity,
    norm=_api._norm,
    google_client=_api._google_client,
)

install_attendance_v42(_shared.app, engine_instance=_api._engine_instance)

install_operations_v41(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    identity_type=_api.Identity,
)

install_admin_change_push(
    _shared.app,
    engine_instance=_api._engine_instance,
    api_module=_api,
    current_identity=_api.current_identity,
    identity_type=_api.Identity,
    leave_create_type=_api.LeaveCreate,
    leave_update_type=_api.LeaveUpdate,
    leave_delete_type=_api.LeaveDelete,
)

install_single_device_guard(_shared.app, engine_instance=_api._engine_instance, current_identity=_api.current_identity, identity_type=_api.Identity)
install_excel_export_style(_shared.app)

app = _shared.app
app.version = PAYROLL_V38_RELEASE
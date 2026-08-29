"""Web V2 shared API entrypoint + Payroll 3.8 installers."""
from __future__ import annotations

import vera_web_v2_api_shared as _shared
import vera_web_v2_admin_audit_archive as _audit_archive
import vera_web_v2_staff_status_sort as _staff_sort
from vera_web_v2_admin_audit_archive import install_admin_audit_archive_routes
from vera_web_v2_leave_preview import install_leave_preview_routes
from vera_web_v2_leave_violation_split import install_leave_violation_split_routes
from vera_web_v2_long_leave_admin import install_long_leave_admin_routes
from vera_web_v2_payroll_debt_sync import install_payroll_debt_sync_routes
from vera_web_v2_payroll_enhancements import install_payroll_enhancement_routes
from vera_web_v2_payroll_saved_edit import install_payroll_saved_edit_routes
from vera_web_v2_payroll_v38 import PAYROLL_V38_RELEASE, install_payroll_v38_routes
from vera_web_v2_policy_v39 import install_policy_v39
from vera_web_v2_shift_break_admin import install_shift_break_admin_routes
from vera_web_v2_single_device import install_single_device_guard
from vera_web_v2_staff_security import install_staff_security_routes
from vera_web_v2_staff_status_sort import install_staff_status_sort

_api = _shared._api

# These installers use local model types in FastAPI route annotations while
# postponed annotations are enabled. Publish the concrete types in their module
# namespaces before route registration so FastAPI can resolve them reliably.
_audit_archive.identity_type = _api.Identity
_audit_archive.leave_update_type = _api.LeaveUpdate
_audit_archive.leave_delete_type = _api.LeaveDelete
_staff_sort.identity_type = _api.Identity

install_payroll_v38_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    norm=_api._norm,
    identity_type=_api.Identity,
    google_client=_api._google_client,
)

# Install after Payroll 3.8 so the final /v2/payroll/calculate wrapper refreshes
# legacy NoViPham first, then delegates through the complete 3.8 calculation.
install_payroll_debt_sync_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    identity_type=_api.Identity,
    google_client=_api._google_client,
)

# Completion/history/deferral routes wrap the final Payroll 3.8 save/history
# endpoints. Saved-payroll edit is mounted last and reuses those canonical
# save/history paths instead of creating a second source of truth.
install_payroll_enhancement_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    norm=_api._norm,
    identity_type=_api.Identity,
)

install_payroll_saved_edit_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    norm=_api._norm,
    identity_type=_api.Identity,
)

install_staff_security_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    norm=_api._norm,
    identity_type=_api.Identity,
    google_client=_api._google_client,
)

# Employee list order is status-first: active, temporarily away, then left.
install_staff_status_sort(
    _shared.app,
    current_identity=_api.current_identity,
    identity_type=_api.Identity,
)

# Admin edits the same shift definitions/break fallback that CHẤM CÔNG reads.
install_shift_break_admin_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    identity_type=_api.Identity,
)

# V3.9 installs before leave-preview/long-leave so every registration path sees
# the same late-month 3-day cap. It also forces payroll imports to Sheet2 and
# exposes authenticated period detection for the browser.
install_policy_v39(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    vn_tz=_api.VN_TZ,
)

# Admin/Quản lý/Lễ tân receive a second registration dropdown for policy rows
# whose "Loại nghỉ" is "Vi phạm". The catalog is generated directly from the
# active Nội quy, so edits in BẢNG NỘI QUY flow through without hard-coded names.
install_leave_violation_split_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    feature_allowed=_api._feature_allowed,
    policy_rows=_api._policy_rows,
    field=_api._field,
    reason_item=_api._reason_item,
    role_tokens=_api._role_tokens,
    day_allowed=_api._day_allowed,
    norm=_api._norm,
)

# Registration preview delegates to the exact canonical validator/calculator,
# so the displayed Người Thứ N penalty is the amount that POST /records stores.
install_leave_preview_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    feature_allowed=_api._feature_allowed,
    validate_and_prepare=_shared._validate_and_prepare,
    identity_type=_api.Identity,
)

# Web V2 Admin can now review the full pending request and approve/reject it on
# the same Phase-14/NghiDaiHan data used by the legacy workflow. Annual-leave
# approval creates daily leave rows through the shared validator.
install_long_leave_admin_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    identity_type=_api.Identity,
    norm=_api._norm,
    google_client=_api._google_client,
    leave_sheet_id=_api.LEAVE_SHEET_ID,
    vn_tz=_api.VN_TZ,
    validate_and_prepare=_shared._validate_and_prepare,
    leave_create_type=_api.LeaveCreate,
    sheet_row_for_record=_api._sheet_row_for_record,
    insert_record=_api._insert_record,
)

# Every insert/edit/delete is captured by a database trigger. The pre-edit or
# deleted version stays available to Admin for 30 days, while the change feed
# returns exact field-level before/after values.
install_admin_audit_archive_routes(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    require_feature=_api._require_feature,
    identity_type=_api.Identity,
    leave_update_type=_api.LeaveUpdate,
    leave_delete_type=_api.LeaveDelete,
)

# Install the one-device lease guard last so it protects all authenticated V2
# business routes, including the installers above. Fresh login claims replace
# any previous active device for the same Supabase user.
install_single_device_guard(
    _shared.app,
    engine_instance=_api._engine_instance,
    current_identity=_api.current_identity,
    identity_type=_api.Identity,
)

app = _shared.app
app.version = PAYROLL_V38_RELEASE

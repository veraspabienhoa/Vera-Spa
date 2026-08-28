"""Web V2 shared API entrypoint + Payroll 3.8 installers."""
from __future__ import annotations

import vera_web_v2_api_shared as _shared
from vera_web_v2_payroll_debt_sync import install_payroll_debt_sync_routes
from vera_web_v2_payroll_enhancements import install_payroll_enhancement_routes
from vera_web_v2_payroll_saved_edit import install_payroll_saved_edit_routes
from vera_web_v2_payroll_v38 import PAYROLL_V38_RELEASE, install_payroll_v38_routes
from vera_web_v2_staff_security import install_staff_security_routes

_api = _shared._api

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

app = _shared.app
app.version = PAYROLL_V38_RELEASE

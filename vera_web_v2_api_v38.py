"""Web V2 shared API entrypoint + Payroll 3.8 installers."""
from __future__ import annotations

import vera_web_v2_api_shared as _shared
from vera_web_v2_payroll_debt_sync import install_payroll_debt_sync_routes
from vera_web_v2_payroll_v38 import PAYROLL_V38_RELEASE, install_payroll_v38_routes

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

app = _shared.app
app.version = PAYROLL_V38_RELEASE

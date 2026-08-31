"""Separate personal accumulation access from full payroll permissions.

Admin can grant ``accumulation_view`` without granting payroll history or any
payroll-management feature.  The existing Web V2 sidebar currently uses the
``payroll_history`` flag only to decide whether the Bảng lương entry is visible;
for accumulation-only users we expose that flag in ``/v2/me`` as a UI alias
only.  Server-side payroll endpoints continue to evaluate the real
``payroll_history`` permission and therefore remain inaccessible.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends

import vera_web_v2_permissions as permissions
from vera_web_v2_payroll_timesoft_upload_fix import install_payroll_timesoft_upload_fix


# The API V3.8 imports this module during startup after the canonical Payroll
# routes have been registered.  Patching the module global here means the
# existing calculate route automatically uses the resilient TimeSoft reader
# without replacing the payroll calculation or permission flow.
install_payroll_timesoft_upload_fix()


RELEASE = "accumulation-permission-2026-09-01.1"
ACCUMULATION_FEATURE = "accumulation_view"
ACCUMULATION_LABEL = "Xem Tiền tích lũy cá nhân"
_TRACKED_ROLES = ("leader", "nhanvien")


def _remove_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            app.router.routes.remove(route)
            return route.endpoint
    raise RuntimeError(f"Cannot find {wanted} {path} to wrap")


def _install_permission_catalog(api_module=None) -> None:
    group = permissions.FEATURE_GROUPS.setdefault("Tiền tích lũy", {})
    group[ACCUMULATION_FEATURE] = ACCUMULATION_LABEL
    permissions.FEATURES[ACCUMULATION_FEATURE] = ACCUMULATION_LABEL

    # Admin always has every feature.  Leader/Nhân viên no longer receive
    # payroll_history merely because they need to see their accumulation.
    permissions.DEFAULT_ROLE_FEATURES.setdefault("admin", set()).add(ACCUMULATION_FEATURE)
    permissions.EMPLOYEE.discard("payroll_history")
    for role in _TRACKED_ROLES:
        defaults = permissions.DEFAULT_ROLE_FEATURES.setdefault(role, set())
        defaults.discard("payroll_history")
        # Tiền tích lũy must be explicitly granted by Admin at role/account scope.
        defaults.discard(ACCUMULATION_FEATURE)

    if api_module is not None:
        features = getattr(api_module, "WEB_V2_FEATURES", None)
        if isinstance(features, dict):
            features[ACCUMULATION_FEATURE] = ACCUMULATION_LABEL
        defaults = getattr(api_module, "WEB_V2_DEFAULT_FEATURES", None)
        if isinstance(defaults, dict):
            defaults.setdefault("admin", set()).add(ACCUMULATION_FEATURE)
            for role in _TRACKED_ROLES:
                role_defaults = defaults.setdefault(role, set())
                role_defaults.discard("payroll_history")
                role_defaults.discard(ACCUMULATION_FEATURE)


def install_accumulation_permission(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature,
    identity_type,
    api_module=None,
) -> None:
    """Install permission catalog, personal API guard, and sidebar UI alias."""
    if getattr(app.state, "accumulation_permission_installed", False):
        return

    _install_permission_catalog(api_module=api_module)

    original_me = _remove_route(app, "/v2/me", "GET")
    original_tracking = _remove_route(app, "/v2/payroll/personal-tracking", "GET")

    @app.get("/v2/me")
    def me_with_accumulation_permission(ident: identity_type = Depends(current_identity)):
        payload = dict(original_me(ident=ident) or {})
        feature_map = dict(payload.get("permissions") or {})
        accumulation_allowed = bool(feature_map.get(ACCUMULATION_FEATURE))
        actual_payroll_history = bool(feature_map.get("payroll_history"))

        # AppShell currently gates the Bảng lương navigation item with
        # payroll_history.  Set a response-only alias so an accumulation-only
        # account can open its personal panel.  This never changes the stored
        # permission and server payroll endpoints still deny payroll_history.
        if accumulation_allowed and not actual_payroll_history:
            feature_map["payroll_history"] = True
            payload["payroll_menu_mode"] = "accumulation_only"
        payload["permissions"] = feature_map
        payload["accumulation_permission_release"] = RELEASE
        return payload

    @app.get("/v2/payroll/personal-tracking")
    def personal_accumulation_guard(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, ACCUMULATION_FEATURE)
        return original_tracking(ident=ident)

    app.state.accumulation_permission_installed = True
    app.state.accumulation_permission_release = RELEASE

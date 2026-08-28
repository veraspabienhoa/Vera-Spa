"""Automatic legacy NoViPham debt sync for Web V2 Payroll.

The legacy system remains the source of truth for carried violation debt.  This
wrapper refreshes only the NoViPham dataset before payroll calculation (and when
the obligation panel is opened), then lets the canonical Payroll 3.7/3.8 path
apply the existing status/due-date rules to the current payroll.
"""
from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, HTTPException, Query
from sqlalchemy import text

import vera_web_v2_payroll as _payroll


PAYROLL_DEBT_SYNC_RELEASE = "3.8-auto-legacy-obligations"
LEGACY_DEBT_DATASET_KEY = "violation_debt"


def _cached_obligation_state(conn) -> tuple[bool, int]:
    row = conn.execute(text("""
        SELECT payload
        FROM vera_dataset_cache
        WHERE dataset_key=:key
        LIMIT 1
    """), {"key": LEGACY_DEBT_DATASET_KEY}).first()
    if row is None:
        return False, 0
    payload = row[0] or []
    count = len([item for item in payload if isinstance(item, dict)]) if isinstance(payload, list) else 0
    return True, count


def _read_legacy_obligations(google_client) -> list[dict[str, Any]]:
    spreadsheet = google_client().open_by_key(_payroll.LEGACY_SPREADSHEET_ID)
    response = spreadsheet.values_batch_get(
        [f"'{_payroll.LEGACY_OBLIGATION_WORKSHEET}'!A:N"],
        params={"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE"},
    )
    ranges = response.get("valueRanges", []) if isinstance(response, dict) else []
    if len(ranges) != 1:
        raise RuntimeError("Google Sheets không trả dữ liệu NoViPham.")
    values = ranges[0].get("values", []) if isinstance(ranges[0], dict) else []
    records = _payroll._sheet_records_from_values(values, _payroll.LEGACY_OBLIGATION_HEADERS)
    for item in records:
        item.pop("__legacy_sheet_row", None)
    return records


def _refresh_legacy_obligations(*, engine_instance, google_client) -> dict[str, Any]:
    """Refresh NoViPham safely; never silently drop carried debt on Google failure."""
    try:
        records = _read_legacy_obligations(google_client)
    except Exception as exc:
        with engine_instance().connect() as conn:
            cache_exists, cached_count = _cached_obligation_state(conn)
        if cache_exists:
            return {
                "status": "cached",
                "count": cached_count,
                "warning": (
                    "Không làm mới được NoViPham; hệ thống đang dùng dữ liệu nợ đã lưu gần nhất. "
                    f"({str(exc)[:180]})"
                ),
            }
        raise HTTPException(
            502,
            "Không tải được Nợ vi phạm kỳ trước từ hệ thống cũ và chưa có dữ liệu cache an toàn. "
            "Đã dừng tính lương để tránh bỏ sót khấu trừ.",
        ) from exc

    with engine_instance().begin() as conn:
        _payroll._write_dataset_cache(
            conn,
            LEGACY_DEBT_DATASET_KEY,
            records,
            "legacy_google_sheet_auto",
        )
    return {"status": "fresh", "count": len(records), "warning": ""}


def _find_route(app, path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") == path and wanted in methods:
            return route
    return None


def install_payroll_debt_sync_routes(
    app,
    *,
    engine_instance,
    current_identity,
    require_feature,
    identity_type,
    google_client,
) -> None:
    """Install automatic NoViPham refresh around Payroll 3.8 routes."""
    if getattr(app.state, "payroll_debt_sync_installed", False):
        return

    calculate_route = _find_route(app, "/v2/payroll/calculate", "POST")
    if calculate_route is None:
        raise RuntimeError("Debt sync cannot find the Payroll calculate route.")
    original_calculate = calculate_route.endpoint
    app.router.routes.remove(calculate_route)

    obligations_route = _find_route(app, "/v2/payroll/obligations", "GET")
    original_obligations = obligations_route.endpoint if obligations_route is not None else None
    if obligations_route is not None:
        app.router.routes.remove(obligations_route)

    @app.get("/v2/payroll-debt-sync/health")
    def payroll_debt_sync_health():
        return {"ok": True, "release": PAYROLL_DEBT_SYNC_RELEASE}

    @app.post("/v2/payroll-debt-sync/refresh")
    def refresh_payroll_debt(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
        sync = _refresh_legacy_obligations(
            engine_instance=engine_instance,
            google_client=google_client,
        )
        return {
            "ok": True,
            "release": PAYROLL_DEBT_SYNC_RELEASE,
            "legacy_obligation_source": _payroll.LEGACY_OBLIGATION_WORKSHEET,
            "legacy_obligation_sync": sync["status"],
            "legacy_obligation_count": sync["count"],
            "legacy_obligation_warning": sync["warning"],
        }

    if original_obligations is not None:
        @app.get("/v2/payroll/obligations", name=getattr(obligations_route, "name", "obligations"))
        def obligations_with_legacy_refresh(ident: identity_type = Depends(current_identity)):
            with engine_instance().connect() as conn:
                require_feature(conn, ident, "payroll_penalty_obligation")
            sync = _refresh_legacy_obligations(
                engine_instance=engine_instance,
                google_client=google_client,
            )
            result = original_obligations(ident=ident)
            payload = dict(result or {})
            payload.update({
                "legacy_obligation_source": _payroll.LEGACY_OBLIGATION_WORKSHEET,
                "legacy_obligation_sync": sync["status"],
                "legacy_obligation_count": sync["count"],
                "legacy_obligation_warning": sync["warning"],
            })
            return payload

    @app.post("/v2/payroll/calculate", name=getattr(calculate_route, "name", "calculate_payroll"))
    async def calculate_payroll_with_legacy_debt(
        month: str = Query(...),
        period_no: int = Query(..., ge=1, le=2),
        payload: bytes = Body(
            ...,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ident: identity_type = Depends(current_identity),
    ):
        # Authenticate/authorize before touching the legacy source. The wrapped
        # Payroll endpoint performs its normal permission check again as well.
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")

        # Refresh BEFORE calculation so canonical _obligation_map() reads the
        # newest NoViPham rows and writes them into "Vi phạm kỳ trước".
        sync = _refresh_legacy_obligations(
            engine_instance=engine_instance,
            google_client=google_client,
        )
        result = await original_calculate(
            month=month,
            period_no=period_no,
            payload=payload,
            ident=ident,
        )
        output = dict(result or {})
        output.update({
            "legacy_obligation_source": _payroll.LEGACY_OBLIGATION_WORKSHEET,
            "legacy_obligation_sync": sync["status"],
            "legacy_obligation_count": sync["count"],
            "legacy_obligation_warning": sync["warning"],
            "debt_sync_release": PAYROLL_DEBT_SYNC_RELEASE,
        })
        return output

    app.state.payroll_debt_sync_installed = True
    app.state.payroll_debt_sync_release = PAYROLL_DEBT_SYNC_RELEASE

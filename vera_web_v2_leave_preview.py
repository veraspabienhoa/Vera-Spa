"""Live leave-registration preview routes for Web V2.

The preview deliberately calls the exact same shared validation/calculation path as
POST /v2/leave/records.  This keeps progressive "Người Thứ N" penalties in the
form aligned with the amount that will actually be stored when the user presses
Ghi.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text


LEAVE_PREVIEW_RELEASE = "leave-progressive-preview-v1"


class LeavePreviewRequest(BaseModel):
    leave_date: date
    employee_name: str = Field(min_length=1, max_length=200)
    leave_reason: str = Field(min_length=1, max_length=300)
    detail: str = Field(default="", max_length=3000)
    manual_penalty: float | None = Field(default=None, ge=0)


def _ordinal(detail: Any) -> int | None:
    match = re.match(r"^\s*Người\s+Thứ\s+(\d+)", str(detail or ""), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def install_leave_preview_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature: Callable[[Any, Any, str], None],
    feature_allowed: Callable[[Any, Any, str], bool],
    validate_and_prepare: Callable[..., Any],
    identity_type,
) -> None:
    if getattr(app.state, "leave_preview_routes_installed", False):
        return

    @app.get("/v2/leave/preview/health")
    def leave_preview_health():
        return {"ok": True, "release": LEAVE_PREVIEW_RELEASE}

    @app.post("/v2/leave/preview")
    def leave_preview(
        body: LeavePreviewRequest,
        ident: identity_type = Depends(current_identity),
    ):
        # Use the same advisory lock as the real write.  The preview therefore
        # observes a stable progressive ordinal instead of racing a concurrent
        # registration that is being committed at the same moment.
        with engine_instance().begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
            require_feature(conn, ident, "leave_create")
            record, warnings = validate_and_prepare(conn, body, ident)
            can_view_penalty = (
                str(getattr(ident, "role", "") or "").lower() == "admin"
                or bool(feature_allowed(conn, ident, "employee_penalty_view"))
            )

        ordinal = _ordinal(record.get("detail"))
        penalty = float(record.get("penalty") or 0) if can_view_penalty else None
        return {
            "ok": True,
            "release": LEAVE_PREVIEW_RELEASE,
            "employee_name": record.get("employee_name", ""),
            "leave_reason": record.get("leave_reason", ""),
            "calculated_days": float(record.get("calculated_days") or 0),
            "penalty": penalty,
            "ordinal": ordinal,
            "progressive": ordinal is not None,
            "warnings": list(warnings or []),
        }

    app.state.leave_preview_routes_installed = True
    app.state.leave_preview_release = LEAVE_PREVIEW_RELEASE

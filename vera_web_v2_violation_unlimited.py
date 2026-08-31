"""Keep Loại nghỉ = Vi phạm unlimited per employee/day.

The canonical Nội quy is authoritative for grouping.  Previously, a Vi phạm
reason whose display name contained "KHÔNG phép" (for example "Qua tour KHÔNG
phép") fell back to name-based grouping and was incorrectly treated as a normal
KHÔNG phép leave registration.  That caused the same-day duplicate-group guard
to reject a second Vi phạm row after an existing Về sớm KHÔNG phép row.

This installer makes canonical Loại nghỉ decisive whenever it is present:
- Có phép -> co_phep
- Không phép -> khong_phep
- Phát sinh -> phat_sinh
- every other non-empty canonical type, including Vi phạm -> no leave group
Only legacy rows with a blank/missing type fall back to the reason-name parser.
"""
from __future__ import annotations

from typing import Any


RELEASE = "violation-unlimited-per-day-2026-08-31-v1"


def install_violation_unlimited(app, *, shared_module) -> None:
    if getattr(app.state, "violation_unlimited_installed", False):
        return

    def policy_group(conn, reason: str) -> str:
        try:
            item = shared_module._reason_item(conn, reason)
            type_key = shared_module.norm(item.get("leave_type", ""))
            if "khong phep" in type_key:
                return "khong_phep"
            if "phat sinh" in type_key:
                return "phat_sinh"
            if "co phep" in type_key:
                return "co_phep"
            if type_key:
                return ""
        except Exception:
            pass
        return shared_module.group(reason)

    shared_module._policy_group = policy_group

    @app.get("/v2/violation-unlimited/health")
    def violation_unlimited_health():
        return {
            "ok": True,
            "release": RELEASE,
            "rule": "canonical_leave_type_authoritative",
            "violation_same_day_limit": None,
        }

    app.state.violation_unlimited_installed = True
    app.state.violation_unlimited_release = RELEASE

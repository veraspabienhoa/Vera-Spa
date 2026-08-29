"""Split leave registration reasons into leave reasons and violation reasons.

The source of truth stays the official Nội quy/LoaiNghi policy.  Web V2 uses
this catalog only for presentation: records are still validated and written by
the canonical leave endpoints, so penalties, progressive Người Thứ N rules,
day restrictions, and manual-penalty requirements remain unchanged.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import Depends, Query


VIOLATION_ENTRY_ROLES = {"admin", "quanly", "letan"}


def _leave_type_key(value: Any, norm: Callable[[Any], str]) -> str:
    token = norm(value)
    if "vi pham" in token:
        return "vi_pham"
    if "khong phep" in token:
        return "khong_phep"
    if "co phep" in token:
        return "co_phep"
    if "phat sinh" in token:
        return "phat_sinh"
    return "khac"


def install_leave_violation_split_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature,
    feature_allowed,
    policy_rows,
    field,
    reason_item,
    role_tokens,
    day_allowed,
    norm,
) -> None:
    if getattr(app.state, "leave_violation_split_installed", False):
        return

    @app.get("/v2/leave/reason-groups")
    def reason_groups(date_value: date = Query(alias="date"), ident=Depends(current_identity)):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "leave")
            can_view_penalty = bool(feature_allowed(conn, ident, "employee_penalty_view"))
            leave_reasons: list[dict[str, Any]] = []
            violations: list[dict[str, Any]] = []
            seen: set[str] = set()

            for row in policy_rows(conn):
                name = str(field(row, "Lý do nghỉ", default="") or "").strip()
                key = norm(name)
                if not name or key in seen:
                    continue
                item = reason_item(conn, name)
                allowed = role_tokens(item.get("allowed_roles", ""))
                if allowed and role not in allowed:
                    continue
                if not day_allowed(item.get("allowed_days", ""), date_value):
                    continue

                is_violation = "vi pham" in norm(item.get("leave_type", ""))
                # Violation rows are intentionally exposed only to the three
                # operational roles requested by VERA.  The auto-update job is
                # server-side and does not consume this browser catalog.
                if is_violation and role not in VIOLATION_ENTRY_ROLES:
                    continue

                payload = {
                    "name": item["name"],
                    "leave_type": item.get("leave_type", ""),
                    "days": item.get("days", 0),
                    "penalty": item.get("penalty", 0) if can_view_penalty else None,
                    "requires_manual_penalty": bool(item.get("requires_manual_penalty")),
                    "allowed_roles": sorted(allowed),
                }
                (violations if is_violation else leave_reasons).append(payload)
                seen.add(key)

        return {
            "ok": True,
            "date": date_value.isoformat(),
            "role": role,
            "leave_reasons": leave_reasons,
            "violations": violations,
            "violation_entry_roles": sorted(VIOLATION_ENTRY_ROLES),
            "source": "BẢNG NỘI QUY · Loại nghỉ",
        }

    @app.get("/v2/leave/reason-types")
    def reason_types(ident=Depends(current_identity)):
        """Return the current Nội quy leave-type mapping without penalty data.

        This endpoint powers the DANH SÁCH type filter for every account.  It
        intentionally returns only reason name + type, so changing Loại nghỉ in
        BẢNG NỘI QUY is reflected without duplicating policy in the browser.
        """
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "leave")
            items: list[dict[str, str]] = []
            seen: set[str] = set()
            for row in policy_rows(conn):
                name = str(field(row, "Lý do nghỉ", default="") or "").strip()
                key = norm(name)
                if not name or key in seen:
                    continue
                item = reason_item(conn, name)
                leave_type = str(item.get("leave_type", "") or "").strip()
                items.append({
                    "name": item["name"],
                    "leave_type": leave_type,
                    "type_key": _leave_type_key(leave_type, norm),
                })
                seen.add(key)
        return {
            "ok": True,
            "items": items,
            "source": "BẢNG NỘI QUY · Loại nghỉ",
        }

    app.state.leave_violation_split_installed = True

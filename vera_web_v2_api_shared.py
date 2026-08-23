"""Web V2 API entrypoint with shared leave-registration rule engine installed.

This wrapper keeps the existing production API implementation intact while
making its policy helpers delegate to the same framework-independent module that
can also be consumed by the Streamlit runtime.
"""
from __future__ import annotations

from fastapi import HTTPException

import vera_web_v2_api as _api
from vera_leave_registration_shared import (
    LeaveRuleError,
    day_allowed,
    field,
    group,
    is_annual,
    is_long_sick,
    is_video,
    norm,
    number,
    parse_first_number,
    progressive_key,
    reason_item,
    role_tokens,
    validate_registration_rule,
    weekday_label,
)


def _reason_item(conn, reason: str) -> dict:
    try:
        return reason_item(_api._policy_rows(conn), reason)
    except LeaveRuleError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def _registration_rule(item: dict, role: str, target):
    try:
        return validate_registration_rule(item, role, target)
    except LeaveRuleError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


# Patch only pure policy helpers. Database/auth/write functions remain the
# original API implementation and therefore preserve record_uid, audit/mirror,
# PostgreSQL transactions and current endpoint contracts.
_api._norm = norm
_api._num = number
_api._field = field
_api._reason_item = _reason_item
_api._role_tokens = role_tokens
_api._weekday_label = weekday_label
_api._day_allowed = day_allowed
_api._parse_first_number = parse_first_number
_api._registration_rule = _registration_rule
_api._group = group
_api._is_video = is_video
_api._is_long_sick = is_long_sick
_api._is_annual = is_annual
_api._progressive_key = progressive_key

app = _api.app

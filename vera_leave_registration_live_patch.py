"""Route the immutable V92.6.99 live leave validator through the shared engine.

Only the body of `_validate_leave_registration_request_live` is replaced.  All
legacy helper functions remain the runtime policy implementation, so Streamlit
behavior is preserved while Web V2 can call the same validation sequence.
"""
from __future__ import annotations

import re


_PATTERN = re.compile(
    r"(?ms)^def _validate_leave_registration_request_live\(payload, live_df, credentials_df\):\n.*?(?=^def _leave_registration_pending_matches_current\()"
)

_REPLACEMENT = '''def _validate_leave_registration_request_live(payload, live_df, credentials_df):
    """V92.23.2 - shared validation sequence; legacy helpers remain authoritative."""
    from vera_leave_registration_live_shared import validate_leave_registration_request_live as _vera_shared_validate_leave_live

    _vera_shared_runtime = {
        "clean_leave_reason_display": clean_leave_reason_display,
        "is_annual_leave_range_reason": is_annual_leave_range_reason,
        "is_long_sick_leave_range_reason": is_long_sick_leave_range_reason,
        "normalize_leave_reason": normalize_leave_reason,
        "employee_registration_window": employee_registration_window,
        "validate_leave_registration_notice": validate_leave_registration_notice,
        "employee_like_roles": EMPLOYEE_LIKE_ROLES,
        "validate_monthly_weekend_registration_limit": _validate_monthly_weekend_registration_limit,
        "is_video_leave_reason": is_video_leave_reason,
        "leave_rows_counting_toward_quota": _leave_rows_counting_toward_quota,
        "normalize_login_name": normalize_login_name,
        "is_special_day_rule_exempt": is_special_day_rule_exempt,
        "leave_exists_in_sources": _leave_exists_in_sources,
        "validate_daily_employee_registration_rule": _validate_daily_employee_registration_rule,
        "validate_daily_group_quota": _validate_daily_group_quota,
        "get_progressive_penalty_reason": get_progressive_penalty_reason,
        "progressive_ordinal_and_bonus": _progressive_ordinal_and_bonus,
        "now_vn": lambda: datetime.now(VN_TZ),
    }
    return _vera_shared_validate_leave_live(payload, live_df, credentials_df, _vera_shared_runtime)


'''


def apply(source: str):
    matches = list(_PATTERN.finditer(source))
    if len(matches) != 1:
        return source, [f"shared_leave_live_validator:{len(matches)}"]
    return _PATTERN.sub(_REPLACEMENT, source, count=1), []

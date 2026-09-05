"""Canonical policy for VERA's daily ``Người Thứ n`` surcharge.

The base amount always comes from the official leave-policy catalog.  This
module decides only whether the progressive 100,000 VND surcharge applies and
keeps every API path on the same reason/date classification.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import re
import unicodedata
from typing import Any

SETTING_CATEGORY = "leave_rules"
SETTING_KEY = "weekend_unpaid_nth_penalty"
CONFIG_SHEET_KEY = "weekend_unpaid_nth_penalty_enabled"
DEFAULT_WEEKEND_UNPAID_ENABLED = False
SURCHARGE_STEP = 100_000
SURCHARGE_PER_PERSON = SURCHARGE_STEP

_UNPAID_LEAVE = "Nghỉ không phép"
_LATE_UNPAID = "Đi trễ không phép"
_EARLY_UNPAID = "Về sớm không phép"


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").replace("🔴", "").strip())
    raw = "".join(char for char in raw if unicodedata.category(char) != "Mn")
    raw = raw.replace("đ", "d").replace("Đ", "D").casefold()
    return re.sub(r"\s+", " ", raw).strip()


_KEY_BY_CANONICAL = {
    _UNPAID_LEAVE: "nghi_khong_phep",
    _LATE_UNPAID: "di_tre_khong_phep",
    _EARLY_UNPAID: "ve_som_khong_phep",
}


def canonical_reason(reason: Any) -> str | None:
    """Return one of the three supported progressive groups, or ``None``."""
    key = _norm(reason)
    if "khong phep" not in key:
        return None
    if "di tre" in key:
        return _LATE_UNPAID
    if "ve som" in key or "ra som" in key:
        return _EARLY_UNPAID
    if "nghi" in key:
        return _UNPAID_LEAVE
    return None


def progressive_key(reason: Any) -> str:
    """Return the stable key used when rebalancing a progressive group."""
    return _KEY_BY_CANONICAL.get(canonical_reason(reason), "")


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text_value, pattern).date()
        except ValueError:
            continue
    return None


def applies(
    target_date: Any,
    reason: Any,
    *,
    weekend_unpaid_enabled: bool = DEFAULT_WEEKEND_UNPAID_ENABLED,
) -> bool:
    """Whether this row receives an ordinal/potential progressive surcharge."""
    canonical = canonical_reason(reason)
    if canonical is None:
        return False
    parsed_date = _as_date(target_date)
    if (
        canonical == _UNPAID_LEAVE
        and parsed_date is not None
        and parsed_date.weekday() >= 5
    ):
        return bool(weekend_unpaid_enabled)
    return True


def bonus(
    ordinal: Any,
    target_date: Any,
    reason: Any,
    *,
    weekend_unpaid_enabled: bool = DEFAULT_WEEKEND_UNPAID_ENABLED,
) -> int:
    """Return only the surcharge; the official base penalty is untouched."""
    if not applies(
        target_date,
        reason,
        weekend_unpaid_enabled=weekend_unpaid_enabled,
    ):
        return 0
    try:
        position = max(1, int(ordinal))
    except (TypeError, ValueError):
        position = 1
    return max(0, position - 2) * SURCHARGE_PER_PERSON


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, dict):
        value = value.get("enabled", default)
    if isinstance(value, bool):
        return value
    key = _norm(value)
    if key in {"1", "true", "yes", "y", "on", "enabled", "bat"}:
        return True
    if key in {"0", "false", "no", "n", "off", "disabled", "tat"}:
        return False
    return bool(default)


def load_weekend_unpaid_enabled(conn) -> bool:
    """Read the Admin switch; missing/invalid/unavailable config fails off."""
    if conn is None:
        return DEFAULT_WEEKEND_UNPAID_ENABLED
    try:
        query = """
            SELECT value_json
            FROM vera_app_setting
            WHERE category=:category AND setting_key=:setting_key
            LIMIT 1
        """
        try:
            from sqlalchemy import text
            statement = text(query)
        except ModuleNotFoundError:
            # Keeps the pure policy module testable without the service stack;
            # production SQLAlchemy connections always use ``text(query)``.
            statement = query
        value = conn.execute(statement, {
            "category": SETTING_CATEGORY,
            "setting_key": SETTING_KEY,
        }).scalar()
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            return DEFAULT_WEEKEND_UNPAID_ENABLED
        return as_bool(
            value.get("enabled", DEFAULT_WEEKEND_UNPAID_ENABLED),
            DEFAULT_WEEKEND_UNPAID_ENABLED,
        )
    except Exception:
        return DEFAULT_WEEKEND_UNPAID_ENABLED

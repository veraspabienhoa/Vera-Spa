"""Dynamic employee leave self-service policy stored in ``vera_app_setting``."""
from __future__ import annotations

from typing import Any

CATEGORY = "leave_rules"
SETTING_KEY = "employee_self_service_policy"
DEFAULT_ENABLED = True
DEFAULT_REGULAR_NOTICE_DAYS = 3
DEFAULT_UNPAID_NOTICE_DAYS = 1
MAX_NOTICE_DAYS = 60


def normalize_policy(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}

    def notice_days(key: str, default: int) -> int:
        try:
            return max(0, min(MAX_NOTICE_DAYS, int(raw.get(key, default))))
        except (TypeError, ValueError):
            return default

    enabled = raw.get("enabled", DEFAULT_ENABLED)
    if not isinstance(enabled, bool):
        enabled = str(enabled or "").strip().lower() in {"1", "true", "yes", "y", "co", "có", "x"}
    return {
        "enabled": enabled,
        "regular_notice_days": notice_days("regular_notice_days", DEFAULT_REGULAR_NOTICE_DAYS),
        "unpaid_notice_days": notice_days("unpaid_notice_days", DEFAULT_UNPAID_NOTICE_DAYS),
    }


def load_policy(conn) -> dict[str, Any]:
    from sqlalchemy import text

    row = conn.execute(text("""
        SELECT value_json, revision, updated_at, updated_by
        FROM vera_app_setting
        WHERE category=:category AND setting_key=:setting_key
        LIMIT 1
    """), {"category": CATEGORY, "setting_key": SETTING_KEY}).mappings().first()
    policy = normalize_policy(row["value_json"] if row else None)
    return {
        **policy,
        "revision": int(row["revision"] or 0) if row else 0,
        "updated_at": row["updated_at"].isoformat() if row and row["updated_at"] else "",
        "updated_by": str(row["updated_by"] or "") if row else "",
    }


def notice_days(policy: dict[str, Any], *items: dict) -> int:
    unpaid = any("khong phep" in _normalize(item.get("leave_type", "")) for item in items)
    key = "unpaid_notice_days" if unpaid else "regular_notice_days"
    default = DEFAULT_UNPAID_NOTICE_DAYS if unpaid else DEFAULT_REGULAR_NOTICE_DAYS
    try:
        return max(0, min(MAX_NOTICE_DAYS, int(policy.get(key, default))))
    except (TypeError, ValueError):
        return default


def _normalize(value: Any) -> str:
    import unicodedata

    text_value = unicodedata.normalize("NFD", str(value or ""))
    return " ".join(
        "".join(char for char in text_value if unicodedata.category(char) != "Mn")
        .replace("đ", "d").replace("Đ", "D").lower().split()
    )

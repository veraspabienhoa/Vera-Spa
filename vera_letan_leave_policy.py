"""Dynamic same-day edit/delete policy for Lễ tân and Quản lý."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


CATEGORY = "leave_rules"
SETTING_KEY = "letan_leave_edit_delete_policy"
MAX_GROUPS = 20
MAX_REASONS_PER_GROUP = 20

DEFAULT_GROUPS = [
    {
        "id": "group_1",
        "name": "Nhóm 1",
        "reasons": ["Nghỉ CÓ phép", "Đi trễ CÓ phép", "Về sớm CÓ phép"],
    },
    {
        "id": "group_2",
        "name": "Nhóm 2",
        "reasons": ["Nghỉ KHÔNG phép", "Đi trễ KHÔNG phép", "Về sớm KHÔNG phép"],
    },
    {
        "id": "group_3",
        "name": "Nhóm 3",
        "reasons": [
            "Nghỉ CUỐI TUẦN CÓ phép",
            "Đi trễ CUỐI TUẦN CÓ phép",
            "Về sớm CUỐI TUẦN CÓ phép",
        ],
    },
    {
        "id": "group_4",
        "name": "Nhóm 4",
        "reasons": [
            "Nghỉ CUỐI TUẦN KHÔNG phép",
            "Đi trễ CUỐI TUẦN KHÔNG phép",
            "Về sớm CUỐI TUẦN KHÔNG phép",
        ],
    },
    {
        "id": "group_5",
        "name": "Nhóm 5",
        "reasons": [
            "Leader nghỉ phép theo chính sách",
            "Leader đi trễ sớm theo chính sách",
            "Leader về sớm về sớm theo chính sách",
        ],
    },
]


def normalize_policy(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        enabled = str(enabled or "").strip().lower() in {"1", "true", "yes", "y", "co", "có", "x"}

    source_groups = raw.get("groups") if isinstance(raw.get("groups"), list) else DEFAULT_GROUPS
    groups: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    used_reasons: set[str] = set()
    for index, item in enumerate(source_groups[:MAX_GROUPS], start=1):
        if not isinstance(item, dict):
            continue
        group_id = str(item.get("id") or f"group_{index}").strip()[:80] or f"group_{index}"
        if group_id in used_ids:
            group_id = f"group_{index}"
        name = str(item.get("name") or f"Nhóm {index}").strip()[:100] or f"Nhóm {index}"
        raw_reasons = item.get("reasons") if isinstance(item.get("reasons"), list) else []
        reasons: list[str] = []
        for reason in raw_reasons[:MAX_REASONS_PER_GROUP]:
            reason_text = str(reason or "").strip()[:300]
            reason_key = _normalize(reason_text)
            if not reason_text or reason_key in used_reasons:
                continue
            reasons.append(reason_text)
            used_reasons.add(reason_key)
        if reasons:
            groups.append({"id": group_id, "name": name, "reasons": reasons})
            used_ids.add(group_id)

    if not groups:
        groups = deepcopy(DEFAULT_GROUPS)
    return {"enabled": enabled, "groups": groups}


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


def reason_group(policy: dict[str, Any], reason: Any, norm=None) -> dict[str, Any] | None:
    normalizer = norm if callable(norm) else _normalize
    key = normalizer(reason)
    if not key:
        return None
    for group in policy.get("groups", []) or []:
        if any(normalizer(item) == key for item in group.get("reasons", []) or []):
            return group
    # Preserve compatibility with the corrected Group 5 wording while the
    # historical Nội quy value contains the duplicated “về sớm”.
    if key == normalizer("Leader về sớm theo chính sách"):
        for group in policy.get("groups", []) or []:
            if any(normalizer(item) == normalizer("Leader về sớm về sớm theo chính sách") for item in group.get("reasons", []) or []):
                return group
    return None


def _normalize(value: Any) -> str:
    import unicodedata

    text_value = unicodedata.normalize("NFD", str(value or ""))
    return " ".join(
        "".join(char for char in text_value if unicodedata.category(char) != "Mn")
        .replace("đ", "d").replace("Đ", "D").lower().split()
    )

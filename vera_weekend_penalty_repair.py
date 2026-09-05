"""Repair obsolete weekend Người Thứ N surcharges in PostgreSQL.

When the Admin weekend switch is off, weekend absence, late-arrival and
early-leave records must keep the official base penalty.  This repair is
deliberately conservative: it only changes rows whose current amount exactly
equals ``official base + the ordinal surcharge`` evidenced by the row detail.
"""
from __future__ import annotations

from decimal import Decimal
import json
import re
import unicodedata
from typing import Any, Mapping

from sqlalchemy import text

from vera_progressive_penalty import (
    SURCHARGE_PER_PERSON,
    load_weekend_unpaid_enabled,
    progressive_key,
)


def _norm(value: Any) -> str:
    raw = str(value or "").strip().casefold().replace("đ", "d")
    raw = "".join(
        char for char in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"[a-z0-9]+", raw))


def _money(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal(0)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    raw = re.sub(r"[^0-9,.-]", "", str(value))
    if "," in raw and "." in raw:
        raw = (
            raw.replace(".", "").replace(",", ".")
            if raw.rfind(",") > raw.rfind(".")
            else raw.replace(",", "")
        )
    elif "," in raw:
        tail = raw.rsplit(",", 1)[-1]
        raw = raw.replace(",", "") if len(tail) == 3 else raw.replace(",", ".")
    elif "." in raw:
        parts = raw.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[-1]) == 3):
            raw = raw.replace(".", "")
    try:
        return Decimal(raw or 0)
    except Exception:
        return Decimal(0)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except Exception:
            return {}
    return {}


def _policy_map(value: Any) -> dict[str, Decimal]:
    document = _payload(value)
    rows = document.get("rows", [])
    if not isinstance(rows, list):
        return {}
    result: dict[str, Decimal] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        reason = row.get("Lý do nghỉ", row.get("Ly do nghi", ""))
        key = _norm(reason)
        if key:
            result[key] = _money(row.get("Phạt vi phạm", row.get("Phat vi pham", 0)))
    return result


def _ordinal(detail: Any) -> int | None:
    match = re.search(r"\bnguoi\s+thu\s+(\d+)\b", _norm(detail))
    return int(match.group(1)) if match else None


def _strip_progressive_prefix(detail: Any) -> str:
    return re.sub(
        r"^\s*Người\s+Thứ\s+\d+\s+"
        r"(?:nghỉ|đi\s+trễ|về\s+sớm|ra\s+sớm)\s+không\s+phép\s*(?:\|\s*)?",
        "",
        str(detail or ""),
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def _repair_target(row: Mapping[str, Any], official: Mapping[str, Decimal]):
    reason = row.get("leave_reason", "")
    if not progressive_key(reason):
        return None
    ordinal = _ordinal(row.get("detail"))
    if ordinal is None or ordinal < 3:
        return None
    base = official.get(_norm(reason))
    if base is None:
        return None
    expected = base + Decimal((ordinal - 2) * SURCHARGE_PER_PERSON)
    if _money(row.get("penalty")) != expected:
        return None
    return base, _strip_progressive_prefix(row.get("detail"))


def repair_connection(conn) -> dict[str, int | bool]:
    """Repair exact obsolete surcharges using an existing SQL transaction."""
    status: dict[str, int | bool] = {"enabled": True, "scanned": 0, "repaired": 0}
    if load_weekend_unpaid_enabled(conn):
        status["enabled"] = False
        return status

    policy_value = conn.execute(text("""
        SELECT value_json
        FROM vera_app_setting
        WHERE category='official_policy' AND setting_key='leave_rules'
        LIMIT 1
    """)).scalar()
    official = _policy_map(policy_value)
    if not official:
        status["enabled"] = False
        return status

    rows = conn.execute(text("""
        SELECT record_uid, leave_reason, leave_date, detail, penalty, payload
        FROM leave_records
        WHERE record_uid IS NOT NULL
          AND BTRIM(record_uid) <> ''
          AND EXTRACT(ISODOW FROM leave_date) IN (6, 7)
        ORDER BY id
    """)).mappings().all()
    status["scanned"] = len(rows)

    for row in rows:
        target = _repair_target(row, official)
        if target is None:
            continue
        penalty, detail = target
        result = conn.execute(text("""
            UPDATE leave_records
            SET penalty=:penalty,
                detail=:detail,
                payload=jsonb_set(
                    jsonb_set(
                        COALESCE(payload, '{}'::jsonb),
                        ARRAY['Phạt vi phạm'],
                        to_jsonb(CAST(:penalty AS numeric)),
                        true
                    ),
                    ARRAY['Chi tiết'],
                    to_jsonb(CAST(:detail AS text)),
                    true
                ),
                updated_at=NOW()
            WHERE record_uid=:record_uid
        """), {
            "penalty": penalty,
            "detail": detail,
            "record_uid": str(row.get("record_uid") or "").strip(),
        })
        if int(result.rowcount or 0) != 1:
            raise RuntimeError(
                f"Weekend penalty repair affected {result.rowcount} rows for "
                f"record_uid={row.get('record_uid')}"
            )
        status["repaired"] = int(status["repaired"]) + 1
    return status


def repair_engine(engine) -> dict[str, int | bool | str]:
    try:
        with engine.begin() as conn:
            return repair_connection(conn)
    except Exception as exc:
        return {
            "enabled": False,
            "scanned": 0,
            "repaired": 0,
            "error": f"{type(exc).__name__}:{exc}",
        }

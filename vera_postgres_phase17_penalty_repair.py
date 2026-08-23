"""Phase 17.3 leave penalty migration integrity repair.

Repairs one specific historical migration corruption observed after the Google Sheets
-> PostgreSQL cutover: normalized ``leave_records.penalty`` values that became
exactly 10x the original source value while the original Sheet value remained
preserved in the row JSONB payload.

Safety:
- PostgreSQL stays canonical; this repair reads only PostgreSQL payload + column.
- No Google Sheets write/read is performed here.
- A row is changed only when current_penalty == payload_penalty * 10 and
  payload_penalty is positive.
- Every UPDATE is keyed strictly by record_uid.
- The repair is idempotent and safe to scan on each process start.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy import text

import vera_postgres_phase3 as _phase3


PHASE17_PENALTY_REPAIR_VERSION = 1
PHASE17_PENALTY_COMPONENT = "phase17_leave_penalty_migration_repair"
LEAVE_DATASET = "leave_primary"

_LAST_STATUS = {
    "enabled": False,
    "scanned": 0,
    "eligible": 0,
    "repaired": 0,
    "skipped": 0,
}


def _enabled(vpg) -> bool:
    if vpg is None:
        return False
    if not bool(getattr(vpg, "_vera_phase17_uid_crud_installed", False)):
        return False
    fn = getattr(vpg, "phase17_is_enabled", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            return False
    return False


def _event(vpg, event_type: str, detail: str = "") -> None:
    try:
        vpg.record_event(LEAVE_DATASET, str(event_type), str(detail or "")[:1800])
    except Exception:
        pass


def _payload_dict(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except Exception:
            return {}
    return {}


def _payload_penalty(payload: Any):
    obj = _payload_dict(payload)
    if "Phạt vi phạm" not in obj:
        return None
    raw = obj.get("Phạt vi phạm")
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    return _phase3._safe_decimal(raw)


def repair(vpg) -> dict:
    global _LAST_STATUS
    status = {
        "enabled": bool(_enabled(vpg)),
        "scanned": 0,
        "eligible": 0,
        "repaired": 0,
        "skipped": 0,
    }
    if not status["enabled"]:
        _LAST_STATUS = status
        return dict(status)

    version_table = getattr(vpg, "SCHEMA_VERSION_TABLE", "vera_schema_version")
    repaired_uids = []

    with vpg.get_engine().begin() as conn:
        rows = conn.execute(text("""
            SELECT record_uid, penalty, payload
            FROM leave_records
            WHERE record_uid IS NOT NULL
              AND BTRIM(record_uid) <> ''
              AND payload ? 'Phạt vi phạm'
            ORDER BY id
        """)).mappings().all()

        status["scanned"] = len(rows)
        for row in rows:
            uid = str(row.get("record_uid") or "").strip()
            source_penalty = _payload_penalty(row.get("payload"))
            current_penalty = _phase3._safe_decimal(row.get("penalty"))

            if not uid or source_penalty is None or source_penalty <= 0:
                status["skipped"] += 1
                continue

            status["eligible"] += 1
            if current_penalty != source_penalty * 10:
                continue

            result = conn.execute(
                text("""
                    UPDATE leave_records
                    SET penalty=:penalty, updated_at=NOW()
                    WHERE record_uid=:record_uid
                """),
                {"penalty": source_penalty, "record_uid": uid},
            )
            if int(result.rowcount or 0) != 1:
                raise RuntimeError(
                    f"Penalty repair affected {result.rowcount} rows for record_uid={uid}"
                )
            status["repaired"] += 1
            if len(repaired_uids) < 20:
                repaired_uids.append(uid)

        conn.execute(text(f"""
            INSERT INTO {version_table}(component, version, updated_at)
            VALUES (:component, :version, NOW())
            ON CONFLICT (component) DO UPDATE
            SET version=GREATEST({version_table}.version, EXCLUDED.version),
                updated_at=NOW()
        """), {
            "component": PHASE17_PENALTY_COMPONENT,
            "version": PHASE17_PENALTY_REPAIR_VERSION,
        })

    _LAST_STATUS = dict(status)
    _event(
        vpg,
        "phase17_penalty_migration_repair",
        "scanned={scanned}; eligible={eligible}; repaired={repaired}; "
        "uids={uids}".format(
            scanned=status["scanned"],
            eligible=status["eligible"],
            repaired=status["repaired"],
            uids=",".join(repaired_uids),
        ),
    )
    return dict(status)


def get_status(vpg=None) -> dict:
    out = dict(_LAST_STATUS)
    out.update({
        "version": PHASE17_PENALTY_REPAIR_VERSION,
        "repair_condition": "current_penalty == payload_penalty * 10",
        "mutation_key": "record_uid_only",
        "source": "postgres_payload",
    })
    if vpg is not None:
        out["enabled"] = bool(_enabled(vpg))
    return out


def install(vpg) -> bool:
    if vpg is None:
        return False
    if getattr(vpg, "_vera_phase17_penalty_repair_installed", False):
        return True
    if not callable(getattr(vpg, "get_engine", None)):
        return False

    if _enabled(vpg):
        repair(vpg)

    vpg.phase17_repair_leave_penalties = lambda: repair(vpg)
    vpg.phase17_penalty_repair_status = lambda: get_status(vpg)
    vpg._vera_phase17_penalty_repair_installed = True
    _event(vpg, "phase17_penalty_repair_installed", "10x migration guard enabled")
    return True

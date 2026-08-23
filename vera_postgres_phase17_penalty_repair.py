"""Phase 17 leave-penalty integrity repair for VERA SPA.

Repairs the historical x10 penalty corruption by comparing each PostgreSQL leave
record with the *official Nội quy* stored in PostgreSQL. The old v1 guard used the
row JSON payload as its expected value; that could miss a bad row when the payload
itself already carried the x10 value.

Safety properties
-----------------
* PostgreSQL stays canonical. No Google Sheet is read or written here.
* Expected money comes from ``official_policy/leave_rules`` (Nội quy canonical).
* A row changes only when ``current_penalty == official_penalty * 10`` and the
  official amount is positive.
* Every database UPDATE is keyed strictly by stable ``record_uid``.
* Reason matching is accent/case/order tolerant, but token-signature matching is
  accepted only when one signature maps to one unique official amount.
* The database repair is a one-time versioned migration. Once version 3 has been
  recorded, later intentional Nội quy changes cannot retroactively trigger this
  historical x10 repair.
* Until that migration succeeds, Phase-17 reads retry it and use a last-mile UI
  guard. After success, normal policy/history behavior is left untouched.
"""
from __future__ import annotations

from decimal import Decimal
import os
import re
import unicodedata
from typing import Any

from sqlalchemy import text

import vera_postgres_phase3 as _phase3


PHASE17_PENALTY_REPAIR_VERSION = 3
PHASE17_PENALTY_COMPONENT = "phase17_leave_penalty_migration_repair"
LEAVE_DATASET = "leave_primary"
_RULES_CATEGORY = "official_policy"
_RULES_KEY = "leave_rules"

_LAST_STATUS = {
    "enabled": False,
    "scanned": 0,
    "eligible": 0,
    "repaired": 0,
    "skipped": 0,
    "policy_rows": 0,
    "already_applied": False,
    "source": "official_policy_postgres",
}

# Conservative bootstrap fallback. It is used only when the canonical policy
# setting has not been bootstrapped yet, and still only repairs an exact x10 row.
_FALLBACK_RULES = {
    "Nghỉ KHÔNG phép": "100.000 mỗi ngày",
    "Nghỉ không phép CUỐI TUẦN": "1.000.000 mỗi ngày",
    "Về sớm CUỐI TUẦN KHÔNG phép": "500.000 mỗi ngày",
    "Đi trễ CUỐI TUẦN KHÔNG phép": "200.000 mỗi ngày",
    "OFFLINE CUỐI TUẦN": "500.000 mỗi ngày",
    "Vừa đi trễ + Vừa về sớm (Phạt kép)": "200.000 mỗi ngày",
    "Lỗi vi phạm khác": "0",
}


def _env_enabled() -> bool:
    return str(os.getenv("VERA_PHASE17_AUTO_REPAIR_PENALTY_OUTLIERS", "1") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _enabled(vpg) -> bool:
    if not _env_enabled() or vpg is None:
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


def _reason_key(value: Any) -> str:
    """Case/accent/punctuation-insensitive reason key, preserving word order."""
    raw = str(value or "").strip().casefold().replace("đ", "d")
    raw = "".join(
        ch for ch in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(ch)
    )
    return " ".join(re.findall(r"[a-z0-9]+", raw))


def _reason_signature(value: Any) -> str:
    """Order-insensitive key used only when its official amount is unambiguous."""
    return " ".join(sorted(_reason_key(value).split()))


def _money(value: Any) -> Decimal:
    return _phase3._safe_decimal(value)


def _version_table(vpg) -> str:
    return str(getattr(vpg, "SCHEMA_VERSION_TABLE", "vera_schema_version"))


def _migration_version(vpg) -> int:
    if not _enabled(vpg):
        return 0
    try:
        table = _version_table(vpg)
        with vpg.get_engine().connect() as conn:
            value = conn.execute(
                text(f"SELECT version FROM {table} WHERE component=:component"),
                {"component": PHASE17_PENALTY_COMPONENT},
            ).scalar()
        return int(value or 0)
    except Exception:
        return 0


def _migration_complete(vpg) -> bool:
    return _migration_version(vpg) >= PHASE17_PENALTY_REPAIR_VERSION


def _policy_rows(vpg) -> list[dict]:
    value = None
    try:
        if callable(getattr(vpg, "read_setting", None)):
            value = vpg.read_setting(_RULES_CATEGORY, _RULES_KEY, None)
    except Exception:
        value = None

    rows = value.get("rows", []) if isinstance(value, dict) else []
    if isinstance(rows, list) and rows:
        return [dict(row) for row in rows if isinstance(row, dict)]
    return [
        {"Lý do nghỉ": reason, "Phạt vi phạm": amount}
        for reason, amount in _FALLBACK_RULES.items()
    ]


def _policy_maps(vpg):
    rows = _policy_rows(vpg)
    exact: dict[str, Decimal] = {}
    sig_values: dict[str, set[Decimal]] = {}
    for row in rows:
        reason = row.get("Lý do nghỉ", row.get("Ly do nghi", ""))
        key = _reason_key(reason)
        if not key:
            continue
        amount = _money(row.get("Phạt vi phạm", row.get("Phat vi pham", 0)))
        exact[key] = amount
        sig = _reason_signature(reason)
        sig_values.setdefault(sig, set()).add(amount)

    signatures = {
        sig: next(iter(values))
        for sig, values in sig_values.items()
        if sig and len(values) == 1
    }
    return exact, signatures, len(rows)


def _official_penalty(reason: Any, exact, signatures):
    key = _reason_key(reason)
    if not key:
        return None
    if key in exact:
        return exact[key]
    return signatures.get(_reason_signature(reason))


def _correct_frame(frame, vpg):
    """Temporary UI guard used only while the one-time migration is incomplete."""
    try:
        if _migration_complete(vpg):
            return frame
        if frame is None or not hasattr(frame, "columns") or frame.empty:
            return frame
        reason_col = next((c for c in ("Lý do nghỉ", "Lý do", "leave_reason") if c in frame.columns), None)
        penalty_col = next((c for c in ("Phạt vi phạm", "penalty") if c in frame.columns), None)
        if not reason_col or not penalty_col:
            return frame
        exact, signatures, _ = _policy_maps(vpg)
        out = frame.copy()
        for idx in out.index:
            expected = _official_penalty(out.at[idx, reason_col], exact, signatures)
            current = _money(out.at[idx, penalty_col])
            if expected is not None and expected > 0 and current == expected * 10:
                out.at[idx, penalty_col] = float(expected) if expected % 1 else int(expected)
        return out
    except Exception:
        return frame


def repair(vpg) -> dict:
    global _LAST_STATUS
    status = {
        "enabled": bool(_enabled(vpg)),
        "scanned": 0,
        "eligible": 0,
        "repaired": 0,
        "skipped": 0,
        "policy_rows": 0,
        "already_applied": False,
        "source": "official_policy_postgres",
    }
    if not status["enabled"]:
        _LAST_STATUS = status
        return dict(status)

    if _migration_complete(vpg):
        status["already_applied"] = True
        _LAST_STATUS = status
        return dict(status)

    exact, signatures, policy_count = _policy_maps(vpg)
    status["policy_rows"] = policy_count
    version_table = _version_table(vpg)
    repaired_uids = []

    with vpg.get_engine().begin() as conn:
        # Recheck inside the write transaction in case another app instance won
        # the migration race while this process was preparing the policy map.
        existing = conn.execute(
            text(f"SELECT version FROM {version_table} WHERE component=:component"),
            {"component": PHASE17_PENALTY_COMPONENT},
        ).scalar()
        if int(existing or 0) >= PHASE17_PENALTY_REPAIR_VERSION:
            status["already_applied"] = True
            _LAST_STATUS = status
            return dict(status)

        rows = conn.execute(text("""
            SELECT record_uid, leave_reason, penalty
            FROM leave_records
            WHERE record_uid IS NOT NULL
              AND BTRIM(record_uid) <> ''
            ORDER BY id
        """)).mappings().all()

        status["scanned"] = len(rows)
        for row in rows:
            uid = str(row.get("record_uid") or "").strip()
            expected = _official_penalty(row.get("leave_reason"), exact, signatures)
            current = _money(row.get("penalty"))

            if not uid or expected is None or expected <= 0:
                status["skipped"] += 1
                continue

            status["eligible"] += 1
            if current != expected * 10:
                continue

            result = conn.execute(
                text("""
                    UPDATE leave_records
                    SET penalty=:penalty, updated_at=NOW()
                    WHERE record_uid=:record_uid
                """),
                {"penalty": expected, "record_uid": uid},
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
        "phase17_penalty_official_rules_repair",
        "scanned={scanned}; eligible={eligible}; repaired={repaired}; policy_rows={policy}; "
        "uids={uids}".format(
            scanned=status["scanned"], eligible=status["eligible"],
            repaired=status["repaired"], policy=status["policy_rows"],
            uids=",".join(repaired_uids),
        ),
    )
    return dict(status)


def _safe_repair(vpg) -> dict:
    try:
        return repair(vpg)
    except Exception as exc:
        _event(vpg, "phase17_penalty_repair_error", f"{type(exc).__name__}:{exc}")
        out = dict(_LAST_STATUS)
        out["error"] = f"{type(exc).__name__}:{exc}"
        return out


def get_status(vpg=None) -> dict:
    out = dict(_LAST_STATUS)
    out.update({
        "version": PHASE17_PENALTY_REPAIR_VERSION,
        "repair_condition": "current_penalty == official_policy_penalty * 10",
        "mutation_key": "record_uid_only",
        "source": "official_policy_postgres",
        "one_time_migration": True,
        "ui_guard_until_migrated": True,
    })
    if vpg is not None:
        out["enabled"] = bool(_enabled(vpg))
        try:
            out["migration_complete"] = bool(_migration_complete(vpg))
        except Exception:
            out["migration_complete"] = False
    return out


def install(vpg) -> bool:
    if vpg is None:
        return False
    if getattr(vpg, "_vera_phase17_penalty_repair_installed", False):
        return True
    if not callable(getattr(vpg, "get_engine", None)):
        return False

    # Repair now, but never make a transient repair failure prevent app startup.
    if _enabled(vpg) and not _migration_complete(vpg):
        _safe_repair(vpg)

    # Retry only while the one-time migration is incomplete. Once version 3 is
    # committed, the wrapper becomes a transparent pass-through and later policy
    # edits cannot be mistaken for historical x10 corruption.
    original_leave_dataframe = getattr(vpg, "phase17_leave_dataframe", None)
    if callable(original_leave_dataframe) and not getattr(original_leave_dataframe, "_vera_penalty_guard", False):
        def guarded_leave_dataframe(*args, **kwargs):
            pending = bool(_enabled(vpg) and not _migration_complete(vpg))
            if pending:
                _safe_repair(vpg)
            frame = original_leave_dataframe(*args, **kwargs)
            return _correct_frame(frame, vpg) if pending else frame
        guarded_leave_dataframe._vera_penalty_guard = True
        vpg.phase17_leave_dataframe = guarded_leave_dataframe

    vpg.phase17_repair_leave_penalties = lambda: _safe_repair(vpg)
    vpg.phase17_penalty_repair_status = lambda: get_status(vpg)
    vpg._vera_phase17_penalty_repair_installed = True
    _event(vpg, "phase17_penalty_repair_installed", "versioned official-policy x10 migration enabled")
    return True

"""Vera Spa PostgreSQL Phase 17: final PostgreSQL cutover.

PostgreSQL becomes canonical for normal runtime reads. Google Sheets mirror can be
sync/optional/off; optional/off never compensates committed PostgreSQL data.
Remaining runtime-only Sheet state is stored in PostgreSQL and leave records receive
a stable logical record_uid while physical Sheet rows remain compatibility metadata.

Rollback:
- VERA_PHASE17_FINAL_BACKEND=sheets disables Phase 17.
- VERA_SHEETS_MIRROR_MODE=sync restores pre-Phase17 synchronous mirror semantics.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from typing import Any, Callable, Mapping, Optional

import pandas as pd
from sqlalchemy import text

PHASE17_SCHEMA_VERSION = 17
RUNTIME_TABLE = "vera_phase17_runtime_state"
NOTICE_TABLE = "vera_phase17_notice_dismiss"
GUIDE_TABLE = "vera_phase17_usage_guide"
EMAIL_LOG_TABLE = "vera_phase17_auto_email_log"


def _enabled(vpg):
    try:
        return bool(vpg.is_enabled())
    except Exception:
        return False


def _mode(vpg):
    try:
        return str(vpg.data_backend_mode() or "sheets").strip().lower()
    except Exception:
        return "sheets"


def final_backend(vpg):
    raw = str(os.getenv("VERA_PHASE17_FINAL_BACKEND", "") or "").strip().lower()
    if raw in {"sheets", "google", "google_sheets", "legacy"}:
        return "sheets"
    if raw in {"postgres", "postgresql", "pg"}:
        return "postgres"
    return "postgres" if _enabled(vpg) and _mode(vpg) == "postgres" else "sheets"


def mirror_mode(vpg=None):
    raw = str(os.getenv("VERA_SHEETS_MIRROR_MODE", "optional") or "optional").strip().lower()
    aliases = {
        "best_effort": "optional", "besteffort": "optional", "async": "optional",
        "none": "off", "disabled": "off", "disable": "off",
        "required": "sync", "synchronous": "sync",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in {"sync", "optional", "off"} else "optional"


def is_active(vpg):
    return (
        _enabled(vpg)
        and _mode(vpg) == "postgres"
        and final_backend(vpg) == "postgres"
        and callable(getattr(vpg, "get_engine", None))
    )


def _event(vpg, event_type, detail=""):
    try:
        vpg.record_event("phase17", str(event_type), str(detail or "")[:1800])
    except Exception:
        pass


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except Exception:
            pass
    return value


def _payload(value):
    return json.dumps(_jsonable(value), ensure_ascii=False, default=str, allow_nan=False)


def _decode(value, default=None):
    if value is None:
        return copy.deepcopy(default)
    if isinstance(value, (dict, list, int, float, bool)):
        return copy.deepcopy(value)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return copy.deepcopy(default)
    return copy.deepcopy(default)


def _ensure_schema(vpg):
    if not _enabled(vpg):
        return
    version_table = getattr(vpg, "SCHEMA_VERSION_TABLE", "vera_schema_version")
    with vpg.get_engine().begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {RUNTIME_TABLE} (
                state_key TEXT PRIMARY KEY,
                value_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                source TEXT NOT NULL DEFAULT '',
                updated_by TEXT NOT NULL DEFAULT '',
                revision BIGINT NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {NOTICE_TABLE} (
                username_key TEXT NOT NULL,
                notice_id TEXT NOT NULL,
                notice_key TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(username_key, notice_id)
            )
        """))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{NOTICE_TABLE}_user ON {NOTICE_TABLE}(username_key, dismissed_at DESC)"))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {GUIDE_TABLE} (
                singleton SMALLINT PRIMARY KEY DEFAULT 1 CHECK(singleton=1),
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                content BYTEA,
                sha256 TEXT NOT NULL DEFAULT '',
                updated_by TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {EMAIL_LOG_TABLE} (
                id BIGSERIAL PRIMARY KEY,
                payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{EMAIL_LOG_TABLE}_created ON {EMAIL_LOG_TABLE}(created_at DESC)"))

        conn.execute(text("ALTER TABLE leave_records ADD COLUMN IF NOT EXISTS record_uid TEXT"))
        conn.execute(text("""
            UPDATE leave_records
            SET record_uid = 'lr-' || md5(COALESCE(source_sheet_id,'') || ':' || COALESCE(source_row::text,'') || ':' || id::text)
            WHERE record_uid IS NULL OR btrim(record_uid)=''
        """))
        conn.execute(text("""
            ALTER TABLE leave_records
            ALTER COLUMN record_uid SET DEFAULT ('lr-' || md5(random()::text || clock_timestamp()::text))
        """))
        conn.execute(text("ALTER TABLE leave_records ALTER COLUMN record_uid SET NOT NULL"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_leave_records_record_uid ON leave_records(record_uid)"))

        conn.execute(text(f"""
            INSERT INTO {version_table}(component, version, updated_at)
            VALUES ('phase17_final_cutover', :version, NOW())
            ON CONFLICT(component) DO UPDATE
            SET version=GREATEST({version_table}.version, EXCLUDED.version), updated_at=NOW()
        """), {"version": PHASE17_SCHEMA_VERSION})


def get_state(vpg, key, default=None):
    if not is_active(vpg):
        return copy.deepcopy(default)
    with vpg.get_engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT value_json FROM {RUNTIME_TABLE} WHERE state_key=:k"),
            {"k": str(key)},
        ).mappings().first()
    if not row:
        return copy.deepcopy(default)
    value = row.get("value_json")
    return _decode(value, default) if isinstance(value, str) else copy.deepcopy(value)


def set_state(vpg, key, value, *, updated_by="", source="postgres_primary"):
    if not is_active(vpg):
        return value
    with vpg.get_engine().begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {RUNTIME_TABLE}(state_key,value_json,source,updated_by,revision,created_at,updated_at)
            VALUES(:k,CAST(:v AS jsonb),:s,:u,1,NOW(),NOW())
            ON CONFLICT(state_key) DO UPDATE SET
                value_json=EXCLUDED.value_json, source=EXCLUDED.source,
                updated_by=EXCLUDED.updated_by, revision={RUNTIME_TABLE}.revision+1,
                updated_at=NOW()
        """), {
            "k": str(key), "v": _payload(value), "s": str(source or ""),
            "u": str(updated_by or ""),
        })
    return copy.deepcopy(value)


def _result_failed(result):
    if isinstance(result, bool):
        return result is False
    if isinstance(result, (tuple, list)) and result and isinstance(result[0], bool):
        return result[0] is False
    return False


def _success_like(result=None):
    if isinstance(result, tuple) and result and isinstance(result[0], bool):
        return tuple([True] + list(result[1:]))
    if isinstance(result, list) and result and isinstance(result[0], bool):
        out = list(result); out[0] = True; return out
    return True


def safe_mirror(vpg, mirror_fn, context="", result_hint=None):
    mode = mirror_mode(vpg)
    if mode == "off":
        _event(vpg, "phase17_sheet_mirror_skipped", context)
        return _success_like(result_hint)
    try:
        result = mirror_fn()
        if _result_failed(result):
            if mode == "sync":
                return result
            _event(vpg, "phase17_sheet_mirror_failed", f"{context}; result={str(result)[:900]}")
            return _success_like(result_hint if result_hint is not None else result)
        _event(vpg, "phase17_sheet_mirror_ok", context)
        return result
    except Exception as exc:
        if mode == "sync":
            raise
        _event(vpg, "phase17_sheet_mirror_error", f"{context}; {type(exc).__name__}: {str(exc)[:1000]}")
        return _success_like(result_hint)


def birthday_login(vpg, username_key, username_display, today_key):
    key = f"birthday:{username_key}:{today_key}"
    with vpg.get_engine().begin() as conn:
        row = conn.execute(
            text(f"SELECT value_json FROM {RUNTIME_TABLE} WHERE state_key=:k FOR UPDATE"),
            {"k": key},
        ).mappings().first()
        state = dict(row.get("value_json") or {}) if row else {}
        count = int(state.get("count") or 0) + 1
        muted = bool(state.get("muted"))
        value = {
            "username": str(username_display or ""), "date": str(today_key),
            "count": count, "muted": muted,
        }
        conn.execute(text(f"""
            INSERT INTO {RUNTIME_TABLE}(state_key,value_json,source,updated_by,revision,created_at,updated_at)
            VALUES(:k,CAST(:v AS jsonb),'postgres_primary',:u,1,NOW(),NOW())
            ON CONFLICT(state_key) DO UPDATE SET value_json=EXCLUDED.value_json,
                source='postgres_primary',updated_by=EXCLUDED.updated_by,
                revision={RUNTIME_TABLE}.revision+1,updated_at=NOW()
        """), {"k": key, "v": _payload(value), "u": str(username_display or "")})
    return count, muted


def birthday_mute(vpg, username_key, username_display, today_key):
    key = f"birthday:{username_key}:{today_key}"
    current = get_state(vpg, key, {}) or {}
    count = max(1, int(current.get("count") or 0))
    set_state(vpg, key, {
        "username": str(username_display or ""), "date": str(today_key),
        "count": count, "muted": True,
    }, updated_by=username_display)
    return True


def notice_ids(vpg, username_key):
    if not is_active(vpg) or not username_key:
        return set()
    with vpg.get_engine().connect() as conn:
        rows = conn.execute(
            text(f"SELECT notice_id FROM {NOTICE_TABLE} WHERE username_key=:u"),
            {"u": str(username_key)},
        ).all()
    return {str(r[0]) for r in rows if r and str(r[0]).strip()}


def seed_notice_ids(vpg, username_key, values):
    ids = [str(x).strip() for x in (values or []) if str(x).strip()]
    with vpg.get_engine().begin() as conn:
        for notice_id in ids:
            conn.execute(text(f"""
                INSERT INTO {NOTICE_TABLE}(username_key,notice_id,notice_key,message,dismissed_at)
                VALUES(:u,:n,'','',NOW()) ON CONFLICT(username_key,notice_id) DO NOTHING
            """), {"u": str(username_key), "n": notice_id})
    set_state(vpg, f"notice_seeded:{username_key}", {"seeded": True},
              updated_by="phase17-seed", source="legacy_seed")


def dismiss_notice(vpg, username_key, notice_id, notice_key="", message=""):
    with vpg.get_engine().begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {NOTICE_TABLE}(username_key,notice_id,notice_key,message,dismissed_at)
            VALUES(:u,:n,:k,:m,NOW())
            ON CONFLICT(username_key,notice_id) DO UPDATE SET
                notice_key=EXCLUDED.notice_key,message=EXCLUDED.message,dismissed_at=NOW()
        """), {
            "u": str(username_key), "n": str(notice_id),
            "k": str(notice_key or ""), "m": str(message or ""),
        })
    return True


def guide_get(vpg):
    if not is_active(vpg):
        return None, None
    with vpg.get_engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT metadata,content FROM {GUIDE_TABLE} WHERE singleton=1")
        ).mappings().first()
    if not row or row.get("content") is None:
        return None, None
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        meta = _decode(meta, {}) or {}
    return dict(meta), bytes(row.get("content"))


def guide_save(vpg, metadata: Mapping[str, Any], raw: bytes, updated_by=""):
    raw = bytes(raw or b"")
    digest = hashlib.sha256(raw).hexdigest()
    meta = dict(metadata or {})
    meta["SHA256"] = digest
    meta["Dung lượng"] = str(len(raw))
    with vpg.get_engine().begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {GUIDE_TABLE}(singleton,metadata,content,sha256,updated_by,updated_at)
            VALUES(1,CAST(:m AS jsonb),:c,:s,:u,NOW())
            ON CONFLICT(singleton) DO UPDATE SET metadata=EXCLUDED.metadata,
                content=EXCLUDED.content,sha256=EXCLUDED.sha256,
                updated_by=EXCLUDED.updated_by,updated_at=NOW()
        """), {"m": _payload(meta), "c": raw, "s": digest, "u": str(updated_by or "")})
    return meta


def guide_update_metadata(vpg, metadata, updated_by=""):
    current, raw = guide_get(vpg)
    if current is None or raw is None:
        return False
    merged = dict(current); merged.update(dict(metadata or {}))
    guide_save(vpg, merged, raw, updated_by=updated_by)
    return True


def guide_delete(vpg):
    with vpg.get_engine().begin() as conn:
        conn.execute(text(f"DELETE FROM {GUIDE_TABLE} WHERE singleton=1"))
    return True


def append_auto_email_log(vpg, payload):
    if not is_active(vpg):
        return
    with vpg.get_engine().begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {EMAIL_LOG_TABLE}(payload,created_at)
            VALUES(CAST(:p AS jsonb),NOW())
        """), {"p": _payload(dict(payload or {}))})


def leave_dataframe(vpg):
    """Phase-5 compatible leave frame plus stable __record_uid."""
    base_fn = (
        getattr(vpg, "_phase17_original_phase5_leave_dataframe", None)
        or getattr(vpg, "phase5_leave_dataframe", None)
    )
    base = base_fn() if callable(base_fn) else pd.DataFrame()
    if not isinstance(base, pd.DataFrame):
        base = pd.DataFrame(base if base is not None else [])
    try:
        raw = vpg.list_leave_records_pg()
        if not isinstance(raw, pd.DataFrame):
            raw = pd.DataFrame(raw if raw is not None else [])
        if raw.empty or "record_uid" not in raw.columns:
            if "__record_uid" not in base.columns:
                base["__record_uid"] = ""
            return base
        uid_map = {}
        for _, row in raw.iterrows():
            key = (str(row.get("source_sheet_id") or ""), int(row.get("source_row") or 0))
            uid_map[key] = str(row.get("record_uid") or "")
        out = base.copy()
        out["__record_uid"] = [
            uid_map.get((str(r.get("__source_sheet_id") or ""), int(r.get("__source_row") or 0)), "")
            for _, r in out.iterrows()
        ]
        return out
    except Exception:
        out = base.copy()
        if "__record_uid" not in out.columns:
            out["__record_uid"] = ""
        return out


def _patch_mirror_callable(vpg, name, mirror_index, confirm_index=None):
    original = getattr(vpg, name, None)
    if not callable(original) or getattr(original, "_vera_phase17_wrapped", False):
        return

    def wrapped(*args, **kwargs):
        if not is_active(vpg) or mirror_mode(vpg) == "sync":
            return original(*args, **kwargs)
        args2 = list(args)
        mirror_fn = kwargs.get("mirror_fn")
        if mirror_fn is None and len(args2) > mirror_index:
            mirror_fn = args2[mirror_index]
        if callable(mirror_fn):
            safe = lambda: safe_mirror(vpg, mirror_fn, context=name)
            if "mirror_fn" in kwargs:
                kwargs = dict(kwargs); kwargs["mirror_fn"] = safe
            elif len(args2) > mirror_index:
                args2[mirror_index] = safe
        if "confirm_fn" in kwargs:
            kwargs = dict(kwargs); kwargs["confirm_fn"] = None
        elif confirm_index is not None and len(args2) > confirm_index:
            args2[confirm_index] = None
        return original(*tuple(args2), **kwargs)

    wrapped._vera_phase17_wrapped = True
    wrapped._vera_phase17_original = original
    setattr(vpg, name, wrapped)


def _install_mirror_policy(vpg):
    targets = [
        ("phase4_employee_upsert", 1, None),
        ("phase4_employee_batch_upsert", 1, None),
        ("phase4_employee_delete", 1, None),
        ("phase4_leave_upsert", 1, None),
        ("phase4_leave_batch_upsert", 1, None),
        ("phase4_leave_delete", 1, None),
        ("phase7_tichluy_commit", 1, 3),
        ("phase8_dataset_commit", 2, 4),
        ("phase10_commit_setting", 2, 5),
        ("phase11_commit_auth_setting", 2, 5),
        ("phase12_commit_theme", 1, 3),
        ("phase13_commit_config", 2, 4),
        ("phase14_mutate_records", 3, 5),
        ("phase15_commit_config", 2, 4),
        ("phase15_employee_upsert", 1, None),
        ("phase15_employee_batch_upsert", 1, None),
        ("phase16_mutate_records", 3, None),
    ]
    for item in targets:
        _patch_mirror_callable(vpg, *item)


def _install_strict_primary_reads(vpg):
    original_load = getattr(vpg, "load_dataset", None)
    if not callable(original_load) or getattr(original_load, "_vera_phase17_wrapped", False):
        return
    original_cred = getattr(vpg, "phase5_credentials_dataframe", None)
    original_leave = getattr(vpg, "phase5_leave_dataframe", None)
    if callable(original_leave):
        vpg._phase17_original_phase5_leave_dataframe = original_leave

    def final_load(dataset_key, source_loader, ttl_seconds=120, force_refresh=False, wait_seconds=3.0):
        if not is_active(vpg) or str(dataset_key) not in {"credentials", "leave_primary"}:
            return original_load(
                dataset_key, source_loader, ttl_seconds=ttl_seconds,
                force_refresh=force_refresh, wait_seconds=wait_seconds,
            )
        if force_refresh and str(os.getenv("VERA_PHASE17_ALLOW_LEGACY_REFRESH", "") or "").strip().lower() in {"1","true","yes","on"}:
            return original_load(
                dataset_key, source_loader, ttl_seconds=ttl_seconds,
                force_refresh=True, wait_seconds=wait_seconds,
            )
        if str(dataset_key) == "credentials" and callable(original_cred):
            out = original_cred()
        else:
            out = leave_dataframe(vpg)
        _event(vpg, "phase17_pg_canonical_read", f"dataset={dataset_key}; rows={len(out) if isinstance(out,pd.DataFrame) else 0}")
        return out

    final_load._vera_phase17_wrapped = True
    final_load._vera_phase17_original = original_load
    vpg.load_dataset = final_load
    vpg.phase17_leave_dataframe = lambda: leave_dataframe(vpg)


def get_status(vpg):
    out = {
        "enabled": bool(is_active(vpg)),
        "final_backend": final_backend(vpg),
        "mirror_mode": mirror_mode(vpg),
        "data_backend": _mode(vpg),
        "schema_version": PHASE17_SCHEMA_VERSION,
        "legacy_refresh_allowed": str(os.getenv("VERA_PHASE17_ALLOW_LEGACY_REFRESH", "") or "").strip().lower() in {"1","true","yes","on"},
    }
    if not _enabled(vpg):
        return out
    try:
        with vpg.get_engine().connect() as conn:
            out["usage_guide"] = bool(conn.execute(text(f"SELECT 1 FROM {GUIDE_TABLE} WHERE singleton=1 AND content IS NOT NULL")).first())
            out["dismissed_notice_count"] = int(conn.execute(text(f"SELECT COUNT(*) FROM {NOTICE_TABLE}")).scalar() or 0)
            out["auto_email_log_count"] = int(conn.execute(text(f"SELECT COUNT(*) FROM {EMAIL_LOG_TABLE}")).scalar() or 0)
            out["leave_uid_missing"] = int(conn.execute(text("SELECT COUNT(*) FROM leave_records WHERE record_uid IS NULL OR btrim(record_uid)='' ")).scalar() or 0)
    except Exception as exc:
        out["status_error"] = f"{type(exc).__name__}: {exc}"
    return out


def install(vpg):
    if vpg is None:
        return False
    if getattr(vpg, "_vera_phase17_installed", False):
        return True
    if not callable(getattr(vpg, "get_engine", None)):
        return False
    if _enabled(vpg):
        _ensure_schema(vpg)
    if is_active(vpg):
        _install_mirror_policy(vpg)
        _install_strict_primary_reads(vpg)
    vpg.phase17_is_enabled = lambda: is_active(vpg)
    vpg.phase17_final_backend = lambda: final_backend(vpg)
    vpg.phase17_mirror_mode = lambda: mirror_mode(vpg)
    vpg.phase17_safe_mirror = lambda mirror_fn, context="", result_hint=None: safe_mirror(vpg, mirror_fn, context=context, result_hint=result_hint)
    vpg.phase17_get_state = lambda key, default=None: get_state(vpg, key, default)
    vpg.phase17_set_state = lambda key, value, updated_by="", source="postgres_primary": set_state(vpg, key, value, updated_by=updated_by, source=source)
    vpg.phase17_birthday_login = lambda username_key, username_display, today_key: birthday_login(vpg, username_key, username_display, today_key)
    vpg.phase17_birthday_mute = lambda username_key, username_display, today_key: birthday_mute(vpg, username_key, username_display, today_key)
    vpg.phase17_notice_ids = lambda username_key: notice_ids(vpg, username_key)
    vpg.phase17_seed_notice_ids = lambda username_key, ids: seed_notice_ids(vpg, username_key, ids)
    vpg.phase17_dismiss_notice = lambda username_key, notice_id, notice_key="", message="": dismiss_notice(vpg, username_key, notice_id, notice_key, message)
    vpg.phase17_guide_get = lambda: guide_get(vpg)
    vpg.phase17_guide_save = lambda metadata, raw, updated_by="": guide_save(vpg, metadata, raw, updated_by=updated_by)
    vpg.phase17_guide_update_metadata = lambda metadata, updated_by="": guide_update_metadata(vpg, metadata, updated_by=updated_by)
    vpg.phase17_guide_delete = lambda: guide_delete(vpg)
    vpg.phase17_append_auto_email_log = lambda payload: append_auto_email_log(vpg, payload)
    vpg.get_phase17_status = lambda: get_status(vpg)
    vpg.ensure_phase17_schema = lambda: _ensure_schema(vpg)
    vpg._vera_phase17_installed = True
    return True

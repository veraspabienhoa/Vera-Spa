# V92.22.4 - Phase 17 strict record_uid canonical leave CRUD (2026-08-23)
"""VERA SPA V92.22.4.

PostgreSQL migration Phase 4-17 remains enabled while preserving the V92.6.99 core,
MENU routes, authorization, UI, and business rules.

V92.22.4 strict leave CRUD hardening:
- keeps the V92.22.3 record_uid canonical CRUD layer;
- UPDATE/DELETE are executed strictly by stable record_uid;
- legacy source_sheet_id/source_row may only resolve an ingress record to record_uid;
- existing canonical source_row cannot be overwritten by stale UI input;
- record_uid is enforced UNIQUE + NOT NULL when Phase 17 is active;
- ambiguous/missing legacy locators fail closed instead of mutating the wrong row;
- source_row remains mirror-position metadata and is reindexed only as mirror metadata;
- Google Sheets remains an optional/sync/off mirror and cannot roll back committed
  PostgreSQL mutations.

Rollback / compatibility:
- VERA_PHASE17_FINAL_BACKEND=sheets -> disable Phase 17 wrappers and UID hardening.
- VERA_SHEETS_MIRROR_MODE=sync      -> require the mirror result synchronously.
- VERA_SHEETS_MIRROR_MODE=optional  -> default best-effort mirror.
- VERA_SHEETS_MIRROR_MODE=off       -> do not execute Phase17-controlled Sheet mirrors.
- VERA_PHASE17_ALLOW_LEGACY_REFRESH=1 -> allow explicit force-refresh from legacy Sheets.
Existing Phase 4-16 rollback environment variables remain supported.

Explicit Admin import/export/backup/refresh actions may still use the two legacy Google
Sheets. Their IDs are unchanged. Normal PostgreSQL data remains canonical.
"""
from datetime import datetime as _datetime
from pathlib import Path as _Path
import importlib as _importlib
import os as _os

import pandas as _pd
import streamlit as _st


def _excel_safe_dataframe(df):
    """Return a copy safe for Excel writers by removing timezone metadata only."""
    if df is None:
        return _pd.DataFrame()
    if not hasattr(df, "copy"):
        return df
    out = df.copy()
    def _excel_safe_value(value):
        if isinstance(value, _pd.Timestamp):
            if value.tzinfo is not None:
                try: return value.tz_localize(None)
                except Exception: return value
            return value
        if isinstance(value, _datetime) and value.tzinfo is not None:
            try: return value.replace(tzinfo=None)
            except Exception: return value
        return value
    for _column in out.columns:
        try:
            _series = out[_column]
            _tz = getattr(getattr(_series, "dtype", None), "tz", None)
            if _tz is not None:
                out[_column] = _series.dt.tz_localize(None)
            elif str(getattr(_series, "dtype", "")) == "object":
                out[_column] = _series.map(_excel_safe_value)
        except Exception:
            try: out[_column] = out[_column].map(_excel_safe_value)
            except Exception: pass
    return out


_vpg_runtime = None
_phase_install_warnings_v92224 = []
try:
    import vera_postgres as _vpg_runtime
    if callable(getattr(_vpg_runtime, "is_enabled", None)) and _vpg_runtime.is_enabled() and not str(_os.getenv("VERA_DATA_BACKEND", "") or "").strip():
        _os.environ["VERA_DATA_BACKEND"] = "postgres"
    for _phase_no_v92224 in (2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17):
        try:
            _mod_v92224 = _importlib.import_module(f"vera_postgres_phase{_phase_no_v92224}")
            _install_v92224 = getattr(_mod_v92224, "install", None)
            if callable(_install_v92224):
                _install_v92224(_vpg_runtime)
        except Exception as _phase_install_error_v92224:
            _phase_install_warnings_v92224.append(f"phase{_phase_no_v92224}:{type(_phase_install_error_v92224).__name__}")
    try:
        _uid_mod_v92224 = _importlib.import_module("vera_postgres_phase17_uid")
        _uid_install_v92224 = getattr(_uid_mod_v92224, "install", None)
        if callable(_uid_install_v92224):
            _uid_install_v92224(_vpg_runtime)
    except Exception as _uid_install_error_v92224:
        _phase_install_warnings_v92224.append(f"phase17_uid:{type(_uid_install_error_v92224).__name__}")
except Exception:
    _vpg_runtime = None


def _phase4_call(method, mirror_fn, *args, **kwargs):
    fn = getattr(_vpg_runtime, method, None) if _vpg_runtime is not None else None
    if callable(fn):
        return fn(*args, mirror_fn=mirror_fn, **kwargs)
    return mirror_fn()


def _vera_phase4_employee_upsert(record, mirror_fn, operation="upsert"):
    return _phase4_call("phase4_employee_upsert", mirror_fn, record, operation=operation)

def _vera_phase4_employee_batch_upsert(records, mirror_fn, operation="batch_upsert"):
    return _phase4_call("phase4_employee_batch_upsert", mirror_fn, records, operation=operation)

def _vera_phase4_employee_delete(usernames, mirror_fn, operation="delete"):
    return _phase4_call("phase4_employee_delete", mirror_fn, usernames, operation=operation)

def _vera_phase4_leave_upsert(record, mirror_fn, operation="upsert"):
    return _phase4_call("phase4_leave_upsert", mirror_fn, record, operation=operation)

def _vera_phase4_leave_batch_upsert(records, mirror_fn, operation="batch_upsert"):
    return _phase4_call("phase4_leave_batch_upsert", mirror_fn, records, operation=operation)

def _vera_phase4_leave_delete(records, mirror_fn, operation="delete"):
    return _phase4_call("phase4_leave_delete", mirror_fn, records, operation=operation)


_core_path_v92224 = _Path(__file__).with_name("app_v92699_core.py")
_core_build_id_v92224 = "v92.22.4-phase17-strict-record-uid-crud-1"


@_st.cache_resource(show_spinner=False)
def _build_core_v92224(build_id):
    _ = build_id
    _source_v92224 = _core_path_v92224.read_text(encoding="utf-8")
    _patch_specs_v92224 = [
        (4, "vera_postgres_phase4_patch"), (7, "vera_postgres_phase7_patch"),
        (8, "vera_postgres_phase8_patch"), (10, "vera_postgres_phase10_patch"),
        (11, "vera_postgres_phase11_patch"), (12, "vera_postgres_phase12_patch"),
        (13, "vera_postgres_phase13_patch"), (14, "vera_postgres_phase14_patch"),
        (15, "vera_postgres_phase15_patch_fix"), (16, "vera_postgres_phase16_patch"),
        (17, "vera_postgres_phase17_patch_fix"),
    ]
    _patch_warnings_v92224 = {}
    for _phase_no_v92224, _module_name_v92224 in _patch_specs_v92224:
        try:
            _patch_mod_v92224 = _importlib.import_module(_module_name_v92224)
            _apply_v92224 = getattr(_patch_mod_v92224, "apply")
            _source_v92224, _warn_v92224 = _apply_v92224(_source_v92224)
            _patch_warnings_v92224[_phase_no_v92224] = list(_warn_v92224 or [])
        except Exception as _patch_error_v92224:
            _patch_warnings_v92224[_phase_no_v92224] = [f"patch_module:{type(_patch_error_v92224).__name__}"]
    _old_menu_map_v92224 = '_MENU_DISPLAY_LABELS_V92699 = {"🧾 Log Book": "Log Book"}'
    _new_menu_map_v92224 = """_MENU_DISPLAY_LABELS_V92699 = {
        "📅 Đăng ký nghỉ phép": "📅 Đăng ký nghỉ",
        "📘 Hướng dẫn sử dụng": "📘 Hướng dẫn",
        "⚙️ Giao diện tùy chỉnh": "⚙️ Giao diện",
        "🔐 Phân quyền chức năng": "🔐 Phân quyền",
        "🏖️ Phép năm - Làm đẹp": "🏖️ Phép năm",
        "⏰ Quản lý ca làm việc": "⏰ Quản lý ca",
        "🏷️ Trạng thái nhân viên": "🏷️ Trạng thái NV",
        "🔐 Khóa đăng ký LNP": "🔐 Khóa đăng ký",
        "🧾 Log Book": "Log Book",
    }"""
    if _old_menu_map_v92224 in _source_v92224:
        _source_v92224 = _source_v92224.replace(_old_menu_map_v92224, _new_menu_map_v92224, 1)
    else:
        _patch_warnings_v92224.setdefault(4, []).append("menu_display_labels:0")
    _source_v92224 = _source_v92224.replace("MENU CHỨC NĂNG", "MENU")
    _first_line_v92224, _sep_v92224, _rest_v92224 = _source_v92224.partition("\n")
    _source_v92224 = "# V92.22.4 - Phase 17 strict record_uid canonical leave CRUD (2026-08-23)\n" + _rest_v92224
    _compiled_v92224 = compile(_source_v92224, str(_core_path_v92224), "exec")
    return _compiled_v92224, _patch_warnings_v92224


_compiled_core_v92224, _patch_warnings_v92224 = _build_core_v92224(_core_build_id_v92224)

if _vpg_runtime is not None:
    for _phase_no_v92224, _warnings_v92224 in _patch_warnings_v92224.items():
        if not _warnings_v92224:
            continue
        try:
            _vpg_runtime.record_event(f"phase{_phase_no_v92224}", f"phase{_phase_no_v92224}_patch_warning", ",".join(_warnings_v92224)[:1800])
        except Exception:
            pass
    if _phase_install_warnings_v92224:
        try:
            _vpg_runtime.record_event("phase17", "phase17_install_warning", ",".join(_phase_install_warnings_v92224)[:1800])
        except Exception:
            pass

exec(_compiled_core_v92224, globals(), globals())

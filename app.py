# V92.23.1 - Penalty repair, safe landing and zero-downtime deploy (2026-08-23)
"""VERA SPA V92.23.1.

PostgreSQL migration Phase 4-17 remains enabled while preserving the V92.6.99 core,
MENU routes, authorization, UI, and business rules.

V92.23.1 operational hardening:
- repairs historical leave penalties only when the stored PostgreSQL amount is
  exactly 10x the canonical official Nội quy amount, strictly by record_uid;
- rechecks the penalty guard before Phase-17 leave reads so corrected totals appear
  on the next Streamlit rerun without asking users to recreate leave records;
- opens 📅 Đăng ký nghỉ as the first application page after login while preserving
  normal menu navigation after the initial landing selection;
- deployment is designed for candidate-revision health checks before traffic cutover.

V92.23.0 official rules remain active:
- upgrades the existing Quản lý lý do nghỉ menu slot to 📜 Nội quy, preserving the
  existing menu count/order on Desktop and Mobile;
- stores the full official LoaiNghi-style grid as a versioned PostgreSQL document;
- supports direct cell editing, copy/paste, add/delete rows and optional columns,
  Excel import/export, and explicit "Ghi thay đổi & áp dụng";
- PostgreSQL is canonical; the legacy LoaiNghi worksheet is synchronized as a
  compatibility mirror for residual jobs/readers;
- get_loai_nghi reads canonical PostgreSQL rules after one-time bootstrap from the
  existing LoaiNghi worksheet;
- required business columns are protected at apply-time so policy edits cannot
  silently disable leave/penalty calculations.

V92.22.4 strict leave CRUD hardening remains active:
- UPDATE/DELETE are executed strictly by stable record_uid;
- legacy source_sheet_id/source_row may only resolve an ingress record to record_uid;
- record_uid is enforced UNIQUE + NOT NULL when Phase 17 is active;
- Google Sheets remains a compatibility mirror and cannot replace PostgreSQL canonical data.

Rollback / compatibility:
- VERA_PHASE17_FINAL_BACKEND=sheets -> disable Phase 17 wrappers and UID hardening.
- VERA_PHASE17_AUTO_REPAIR_PENALTY_OUTLIERS=0 -> disable the x10 repair guard.
- VERA_SHEETS_MIRROR_MODE=sync|optional|off remains supported.
- VERA_PHASE17_ALLOW_LEGACY_REFRESH=1 remains supported.
Existing Phase 4-16 rollback environment variables remain supported.

The two legacy Google Sheet IDs are unchanged.
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
_phase_install_warnings_v92231 = []

# Install before executing the legacy core so the authenticated main-menu widget
# can choose the leave-registration route on its first appearance.
try:
    _landing_mod_v92231 = _importlib.import_module("vera_postlogin_default_page")
    _landing_install_v92231 = getattr(_landing_mod_v92231, "install", None)
    if callable(_landing_install_v92231):
        _landing_install_v92231()
except Exception as _landing_install_error_v92231:
    _phase_install_warnings_v92231.append(
        f"postlogin_landing:{type(_landing_install_error_v92231).__name__}"
    )

try:
    import vera_postgres as _vpg_runtime
    if callable(getattr(_vpg_runtime, "is_enabled", None)) and _vpg_runtime.is_enabled() and not str(_os.getenv("VERA_DATA_BACKEND", "") or "").strip():
        _os.environ["VERA_DATA_BACKEND"] = "postgres"
    for _phase_no_v92231 in (2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17):
        try:
            _mod_v92231 = _importlib.import_module(f"vera_postgres_phase{_phase_no_v92231}")
            _install_v92231 = getattr(_mod_v92231, "install", None)
            if callable(_install_v92231):
                _install_v92231(_vpg_runtime)
        except Exception as _phase_install_error_v92231:
            _phase_install_warnings_v92231.append(f"phase{_phase_no_v92231}:{type(_phase_install_error_v92231).__name__}")
    try:
        _uid_mod_v92231 = _importlib.import_module("vera_postgres_phase17_uid")
        _uid_install_v92231 = getattr(_uid_mod_v92231, "install", None)
        if callable(_uid_install_v92231):
            _uid_install_v92231(_vpg_runtime)
    except Exception as _uid_install_error_v92231:
        _phase_install_warnings_v92231.append(f"phase17_uid:{type(_uid_install_error_v92231).__name__}")
    try:
        _penalty_mod_v92231 = _importlib.import_module("vera_postgres_phase17_penalty_repair")
        _penalty_install_v92231 = getattr(_penalty_mod_v92231, "install", None)
        if callable(_penalty_install_v92231):
            _penalty_install_v92231(_vpg_runtime)
    except Exception as _penalty_install_error_v92231:
        _phase_install_warnings_v92231.append(f"phase17_penalty:{type(_penalty_install_error_v92231).__name__}")
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


_core_path_v92231 = _Path(__file__).with_name("app_v92699_core.py")
_core_build_id_v92231 = "v92.23.1-penalty-landing-safe-deploy-1"


@_st.cache_resource(show_spinner=False)
def _build_core_v92231(build_id):
    _ = build_id
    _source_v92231 = _core_path_v92231.read_text(encoding="utf-8")
    _patch_specs_v92231 = [
        (4, "vera_postgres_phase4_patch"), (7, "vera_postgres_phase7_patch"),
        (8, "vera_postgres_phase8_patch"), (10, "vera_postgres_phase10_patch"),
        (11, "vera_postgres_phase11_patch"), (12, "vera_postgres_phase12_patch"),
        (13, "vera_postgres_phase13_patch"), (14, "vera_postgres_phase14_patch"),
        (15, "vera_postgres_phase15_patch_fix"), (16, "vera_postgres_phase16_patch"),
        (17, "vera_postgres_phase17_patch_fix"), (18, "vera_official_rules_patch"),
    ]
    _patch_warnings_v92231 = {}
    for _phase_no_v92231, _module_name_v92231 in _patch_specs_v92231:
        try:
            _patch_mod_v92231 = _importlib.import_module(_module_name_v92231)
            _apply_v92231 = getattr(_patch_mod_v92231, "apply")
            _source_v92231, _warn_v92231 = _apply_v92231(_source_v92231)
            _patch_warnings_v92231[_phase_no_v92231] = list(_warn_v92231 or [])
        except Exception as _patch_error_v92231:
            _patch_warnings_v92231[_phase_no_v92231] = [f"patch_module:{type(_patch_error_v92231).__name__}"]
    _old_menu_map_v92231 = '_MENU_DISPLAY_LABELS_V92699 = {"🧾 Log Book": "Log Book"}'
    _new_menu_map_v92231 = """_MENU_DISPLAY_LABELS_V92699 = {
        "📅 Đăng ký nghỉ phép": "📅 Đăng ký nghỉ",
        "📘 Hướng dẫn sử dụng": "📘 Hướng dẫn",
        "⚙️ Giao diện tùy chỉnh": "⚙️ Giao diện",
        "🔐 Phân quyền chức năng": "🔐 Phân quyền",
        "🏖️ Phép năm - Làm đẹp": "🏖️ Phép năm",
        "⏰ Quản lý ca làm việc": "⏰ Quản lý ca",
        "🏷️ Trạng thái nhân viên": "🏷️ Trạng thái NV",
        "🔐 Khóa đăng ký LNP": "🔐 Khóa đăng ký",
        "🧾 Quản lý lý do nghỉ": "📜 Nội quy",
        "🧾 Log Book": "Log Book",
    }"""
    if _old_menu_map_v92231 in _source_v92231:
        _source_v92231 = _source_v92231.replace(_old_menu_map_v92231, _new_menu_map_v92231, 1)
    else:
        _patch_warnings_v92231.setdefault(4, []).append("menu_display_labels:0")
    _source_v92231 = _source_v92231.replace("MENU CHỨC NĂNG", "MENU")
    _first_line_v92231, _sep_v92231, _rest_v92231 = _source_v92231.partition("\n")
    _source_v92231 = "# V92.23.1 - Penalty repair + post-login leave landing (2026-08-23)\n" + _rest_v92231
    _compiled_v92231 = compile(_source_v92231, str(_core_path_v92231), "exec")
    return _compiled_v92231, _patch_warnings_v92231


_compiled_core_v92231, _patch_warnings_v92231 = _build_core_v92231(_core_build_id_v92231)

if _vpg_runtime is not None:
    for _phase_no_v92231, _warnings_v92231 in _patch_warnings_v92231.items():
        if not _warnings_v92231:
            continue
        try:
            _vpg_runtime.record_event(f"phase{_phase_no_v92231}", f"phase{_phase_no_v92231}_patch_warning", ",".join(_warnings_v92231)[:1800])
        except Exception:
            pass
    if _phase_install_warnings_v92231:
        try:
            _vpg_runtime.record_event("phase17", "phase17_install_warning", ",".join(_phase_install_warnings_v92231)[:1800])
        except Exception:
            pass

exec(_compiled_core_v92231, globals(), globals())

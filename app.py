# V92.22.0 - PostgreSQL Phase 17 final cutover (2026-08-23)
"""VERA SPA V92.22.0.

PostgreSQL migration Phase 4-17 is enabled while preserving the V92.6.99 core,
MENU routes, authorization, UI, and business rules.

Phase 17 final cutover:
- credentials + leave_primary normal reads are PostgreSQL canonical;
- runtime Hướng dẫn sử dụng, birthday notice state, dismissed notices,
  Auto Update email state/log and midshift daily state are PostgreSQL-backed;
- leave_records has stable record_uid logical identity;
- Google Sheets mirror defaults to best-effort optional and no longer rolls back
  committed PostgreSQL merely because the mirror is unavailable.

Rollback / compatibility:
- VERA_PHASE17_FINAL_BACKEND=sheets -> disable Phase 17 wrappers.
- VERA_SHEETS_MIRROR_MODE=sync      -> restore synchronous required mirror behavior.
- VERA_SHEETS_MIRROR_MODE=optional  -> default best-effort mirror.
- VERA_SHEETS_MIRROR_MODE=off       -> do not execute Phase17-controlled Sheet mirrors.
- VERA_PHASE17_ALLOW_LEGACY_REFRESH=1 -> allow explicit force-refresh from legacy Sheets.
Existing Phase 4-16 rollback environment variables remain supported.

Explicit Admin import/export/backup/refresh actions may still use the two legacy Google
Sheets. Their IDs are unchanged. Normal PostgreSQL data remains canonical.
"""
from pathlib import Path as _Path
import importlib as _importlib
import os as _os

_vpg_runtime = None
_phase_install_warnings_v92220 = []
try:
    import vera_postgres as _vpg_runtime
    if (
        callable(getattr(_vpg_runtime, "is_enabled", None))
        and _vpg_runtime.is_enabled()
        and not str(_os.getenv("VERA_DATA_BACKEND", "") or "").strip()
    ):
        _os.environ["VERA_DATA_BACKEND"] = "postgres"

    for _phase_no_v92220 in (2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17):
        try:
            _mod_v92220 = _importlib.import_module(f"vera_postgres_phase{_phase_no_v92220}")
            _install_v92220 = getattr(_mod_v92220, "install", None)
            if callable(_install_v92220):
                _install_v92220(_vpg_runtime)
        except Exception as _phase_install_error_v92220:
            _phase_install_warnings_v92220.append(
                f"phase{_phase_no_v92220}:{type(_phase_install_error_v92220).__name__}"
            )
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


_core_path_v92220 = _Path(__file__).with_name("app_v92699_core.py")
_source_v92220 = _core_path_v92220.read_text(encoding="utf-8")

_patch_specs_v92220 = [
    (4, "vera_postgres_phase4_patch"),
    (7, "vera_postgres_phase7_patch"),
    (8, "vera_postgres_phase8_patch"),
    (10, "vera_postgres_phase10_patch"),
    (11, "vera_postgres_phase11_patch"),
    (12, "vera_postgres_phase12_patch"),
    (13, "vera_postgres_phase13_patch"),
    (14, "vera_postgres_phase14_patch"),
    (15, "vera_postgres_phase15_patch_fix"),
    (16, "vera_postgres_phase16_patch"),
    (17, "vera_postgres_phase17_patch"),
]
_patch_warnings_v92220 = {}
for _phase_no_v92220, _module_name_v92220 in _patch_specs_v92220:
    try:
        _patch_mod_v92220 = _importlib.import_module(_module_name_v92220)
        _apply_v92220 = getattr(_patch_mod_v92220, "apply")
        _source_v92220, _warn_v92220 = _apply_v92220(_source_v92220)
        _patch_warnings_v92220[_phase_no_v92220] = list(_warn_v92220 or [])
    except Exception as _patch_error_v92220:
        _patch_warnings_v92220[_phase_no_v92220] = [
            f"patch_module:{type(_patch_error_v92220).__name__}"
        ]

# Existing V92.6.101 display-only MENU patch.
_old_menu_map_v92220 = '_MENU_DISPLAY_LABELS_V92699 = {"🧾 Log Book": "Log Book"}'
_new_menu_map_v92220 = """_MENU_DISPLAY_LABELS_V92699 = {
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
if _old_menu_map_v92220 in _source_v92220:
    _source_v92220 = _source_v92220.replace(_old_menu_map_v92220, _new_menu_map_v92220, 1)
else:
    _patch_warnings_v92220.setdefault(4, []).append("menu_display_labels:0")
_source_v92220 = _source_v92220.replace("MENU CHỨC NĂNG", "MENU")
_first_line_v92220, _sep_v92220, _rest_v92220 = _source_v92220.partition("\n")
_source_v92220 = "# V92.22.0 - PostgreSQL Phase 17 final cutover (2026-08-23)\n" + _rest_v92220

if _vpg_runtime is not None:
    for _phase_no_v92220, _warnings_v92220 in _patch_warnings_v92220.items():
        if not _warnings_v92220:
            continue
        try:
            _vpg_runtime.record_event(
                f"phase{_phase_no_v92220}",
                f"phase{_phase_no_v92220}_patch_warning",
                ",".join(_warnings_v92220)[:1800],
            )
        except Exception:
            pass
    if _phase_install_warnings_v92220:
        try:
            _vpg_runtime.record_event(
                "phase17",
                "phase17_install_warning",
                ",".join(_phase_install_warnings_v92220)[:1800],
            )
        except Exception:
            pass

exec(
    compile(_source_v92220, str(_core_path_v92220), "exec"),
    globals(),
    globals(),
)

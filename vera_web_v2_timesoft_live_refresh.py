"""Direct production TimeSoft -> PostgreSQL refresh for Web V2 attendance.

The Web V2 alert/snapshot flow can run frequently. To avoid false attendance
results from stale PostgreSQL data, this module refreshes today's TimeSoft
check-in dataset synchronously when the cached dataset is older than the
configured freshness threshold. Concurrent requests share one refresh.

Normal authentication is browserless through TimeSoft /User/ValidateUser so a
missing Chromium shared library cannot take Chấm công offline. Playwright is kept
only as a compatibility fallback when the HTTP protocol itself changes.
SearchElastic is the minimum authoritative attendance source. The detailed
FaceID export is best-effort and may recover independently.
"""
from __future__ import annotations

from datetime import datetime
import os
import threading
import time
from typing import Any

import timesoft_sync_job as ts
from timesoft_detailed_checkin import install as install_detailed_checkin
from timesoft_http_auth import install as install_http_auth, refresh_runtime_credentials
from timesoft_recalculate_checkin import install as install_recalculate_checkin


RELEASE = "timesoft-live-refresh-2026-09-07-v4-runtime-credentials"
MIN_INTERVAL_SECONDS = max(10, min(60, int(os.getenv("TIMESOFT_LIVE_REFRESH_SECONDS", "20") or 20)))

_lock = threading.Lock()
_session = None
_last_success_monotonic = 0.0
_last_error = ""
_last_meta: dict[str, Any] = {}

# Keep the legacy browser recalculation path available as fallback, preserve
# detailed FaceID when TimeSoft serves it, then wrap session creation with the
# HTTP-first login so production does not depend on Chromium system packages.
install_recalculate_checkin(ts)
install_detailed_checkin(ts)
install_http_auth(ts)


def _credentials_ready() -> bool:
    try:
        username, password = refresh_runtime_credentials(ts)
    except Exception:
        return False
    return bool(str(username or "").strip() and str(password or ""))


def _write_today(checkin_df) -> None:
    today = datetime.now(ts.VN_TZ).date()
    ts.vpg.write_dataset(
        "timesoft_employee_checkin_today",
        checkin_df,
        ttl_seconds=1800,
        source_version=today.isoformat(),
    )


def refresh_today(force: bool = False) -> dict[str, Any]:
    """Refresh today's TimeSoft check-in dataset, single-flight and rate-limited."""
    global _session, _last_success_monotonic, _last_error, _last_meta

    if not _credentials_ready():
        return {
            "ok": False,
            "refreshed": False,
            "release": RELEASE,
            "error_code": "TIMESOFT_CREDENTIALS_MISSING",
            "error": "TimeSoft production credentials are not configured on Web V2 API.",
        }

    age = time.monotonic() - _last_success_monotonic if _last_success_monotonic else None
    if not force and age is not None and age < MIN_INTERVAL_SECONDS:
        return {
            "ok": True,
            "refreshed": False,
            "release": RELEASE,
            "age_seconds": round(age, 3),
            **_last_meta,
        }

    with _lock:
        age = time.monotonic() - _last_success_monotonic if _last_success_monotonic else None
        if not force and age is not None and age < MIN_INTERVAL_SECONDS:
            return {
                "ok": True,
                "refreshed": False,
                "release": RELEASE,
                "age_seconds": round(age, 3),
                **_last_meta,
            }

        try:
            # Always refresh credentials before establishing/reusing a session.
            # If the runtime credential file changed, discard the old session so
            # the next request authenticates with the new account immediately.
            before = (str(ts.USERNAME or ""), str(ts.PASSWORD or ""))
            refresh_runtime_credentials(ts)
            after = (str(ts.USERNAME or ""), str(ts.PASSWORD or ""))
            if before != after:
                _session = None

            if _session is None:
                _session = ts.create_authenticated_session()
            today = datetime.now(ts.VN_TZ).date()
            checkin_df, meta = ts.fetch_checkin(_session, today)
            _write_today(checkin_df)
            _last_success_monotonic = time.monotonic()
            _last_error = ""
            _last_meta = {
                "rows": int(len(checkin_df)),
                "total": int(meta.get("Total") or 0),
                "summary_rows": int(meta.get("SummaryRows") or 0),
                "raw_log_rows": int(meta.get("RawLogRows") or 0),
                "combined_rows": int(meta.get("CombinedRows") or len(checkin_df)),
                "detailed_log_ready": bool(meta.get("DetailedLogReady")),
                "detailed_log_error": str(meta.get("DetailedLogError") or "")[:500],
                "detailed_log_release": str(meta.get("DetailedLogRelease") or ""),
                "auth_mode": str(getattr(_session, "_vera_timesoft_auth_mode", "unknown")),
                "auth_release": str(getattr(_session, "_vera_timesoft_auth_release", "")),
                "source_version": today.isoformat(),
            }
            return {
                "ok": True,
                "refreshed": True,
                "release": RELEASE,
                **_last_meta,
            }
        except Exception as exc:
            _session = None
            _last_error = f"{type(exc).__name__}: {exc}"[:1000]
            lower = _last_error.lower()
            error_code = (
                "TIMESOFT_AUTH_REJECTED"
                if "tài khoản/mật khẩu" in lower or "us0006" in lower or "mật khẩu" in lower
                else "TIMESOFT_REFRESH_FAILED"
            )
            return {
                "ok": False,
                "refreshed": False,
                "release": RELEASE,
                "error_code": error_code,
                "error": _last_error,
            }


def health() -> dict[str, Any]:
    age = time.monotonic() - _last_success_monotonic if _last_success_monotonic else None
    return {
        "ok": True,
        "release": RELEASE,
        "credentials_ready": _credentials_ready(),
        "credentials_source": str(getattr(ts, "_timesoft_runtime_credentials_source", "environment")),
        "min_interval_seconds": MIN_INTERVAL_SECONDS,
        "last_success_age_seconds": round(age, 3) if age is not None else None,
        "last_error": _last_error,
        "source": str(ts.BASE_URL),
        "target": "PostgreSQL vera_dataset_cache/timesoft_employee_checkin_today",
        "authentication": "HTTP /User/ValidateUser first; Playwright compatibility fallback",
        "recalculate_policy": "Playwright fallback may recalculate; HTTP availability path reads SearchElastic directly",
        "detailed_faceid_best_effort": True,
        "detailed_checkin_release": str(getattr(ts, "_detailed_checkin_patch_release", "")),
        "http_auth_release": str(getattr(ts, "_timesoft_http_auth_release", "")),
        **_last_meta,
    }

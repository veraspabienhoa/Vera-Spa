"""Direct production TimeSoft -> PostgreSQL refresh for Web V2 attendance alerts.

The alert endpoint may run every 15 seconds. To avoid false overdue decisions from
stale PostgreSQL data, this module refreshes today's TimeSoft check-in dataset
synchronously when the cached dataset is older than the configured freshness
threshold. Concurrent requests share one refresh via a process lock.

Authentication uses the existing production TimeSoft secrets injected into the
Web V2 Cloud Run API. A new authenticated session runs the existing
"Tính lại ngày công" guard before SearchElastic is read. Every refresh also
loads TimeSoft's ExportCheckinLogElastic workbook so intermediate FaceID events
are preserved for break-out / break-return reconstruction.
"""
from __future__ import annotations

from datetime import datetime
import os
import threading
import time
from typing import Any

import timesoft_sync_job as ts
from timesoft_detailed_checkin import install as install_detailed_checkin
from timesoft_recalculate_checkin import install as install_recalculate_checkin


RELEASE = "timesoft-live-refresh-2026-09-02-v2-detailed-faceid"
MIN_INTERVAL_SECONDS = max(10, min(60, int(os.getenv("TIMESOFT_LIVE_REFRESH_SECONDS", "20") or 20)))

_lock = threading.Lock()
_session = None
_last_success_monotonic = 0.0
_last_error = ""
_last_meta: dict[str, Any] = {}

# Every new login first asks TimeSoft to recalculate today's attendance so the
# summary fields are fresh, then every read is augmented with the raw detailed
# FaceID workbook. The detailed patch fails closed rather than overwriting a
# good cache with a summary-only snapshot that would lose mid-shift punches.
install_recalculate_checkin(ts)
install_detailed_checkin(ts)


def _credentials_ready() -> bool:
    return bool(str(ts.USERNAME or "").strip() and str(ts.PASSWORD or ""))


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

    # Do not let several Web V2 viewers log in/export TimeSoft simultaneously.
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
                "detailed_log_release": str(meta.get("DetailedLogRelease") or ""),
            }
            return {
                "ok": True,
                "refreshed": True,
                "release": RELEASE,
                **_last_meta,
            }
        except Exception as exc:
            # The TimeSoft web session may have expired. Drop it so the next
            # request performs a clean authenticated login + recalculation.
            _session = None
            _last_error = f"{type(exc).__name__}: {exc}"[:1000]
            return {
                "ok": False,
                "refreshed": False,
                "release": RELEASE,
                "error": _last_error,
            }


def health() -> dict[str, Any]:
    age = time.monotonic() - _last_success_monotonic if _last_success_monotonic else None
    return {
        "ok": True,
        "release": RELEASE,
        "credentials_ready": _credentials_ready(),
        "min_interval_seconds": MIN_INTERVAL_SECONDS,
        "last_success_age_seconds": round(age, 3) if age is not None else None,
        "last_error": _last_error,
        "source": str(ts.BASE_URL),
        "target": "PostgreSQL vera_dataset_cache/timesoft_employee_checkin_today",
        "recalculate_before_new_session": True,
        "detailed_faceid_required": True,
        "detailed_checkin_release": str(getattr(ts, "_detailed_checkin_patch_release", "")),
        **_last_meta,
    }

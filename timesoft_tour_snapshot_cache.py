"""Persist the TourVera Input snapshot loaded by background jobs.

Web requests must not download the XLSM from Google Drive. The scheduled
TimeSoft/Auto Check jobs cache that same DataFrame in PostgreSQL and Web V2
consumes it locally.

Admin may pause only the frequent Web V2 TourVera cache refresh. When paused:
- the snapshot job does not download TourVera merely to refresh this cache;
- an Auto Check run that genuinely needs TourVera may still read its workbook,
  but the result is not written into the Web V2 cache;
- Web V2 ignores old cache data immediately via vera_web_v2_tour_cache_perf.
"""
from __future__ import annotations

from datetime import datetime

import vera_tour_cache_control as cache_control


RELEASE = "tourvera-postgres-cache-2026-08-31-v3-pausable"
DATASET_KEY = cache_control.DATASET_KEY
TTL_SECONDS = 15 * 60


def _cache_disabled(ts) -> bool:
    try:
        with ts.vpg.get_engine().connect() as conn:
            return cache_control.disabled(conn)
    except Exception as exc:
        # A transient control-read failure must not silently stop the existing
        # background pipeline. Admin can retry the switch from Web V2.
        ts._log(f"TOUR CACHE CONTROL WARN: {type(exc).__name__}: {exc}")
        return False


def install(ts) -> None:
    if getattr(ts, "_tour_snapshot_cache_patch_release", "") == RELEASE:
        return

    original_load = ts.load_bang_tour_input
    original_run_sync = ts.run_sync
    state = {"loaded_during_run": False}

    def load_and_cache():
        # This wrapper can also be called by a genuine Auto Check execution.
        # Preserve that source read even when the Web V2 cache is paused.
        df = original_load()
        state["loaded_during_run"] = True
        if _cache_disabled(ts):
            ts._log("TOUR CACHE PAUSED BY ADMIN: bỏ qua ghi PostgreSQL cache")
            return df
        try:
            if df is not None and not getattr(df, "empty", True):
                now = datetime.now(ts.VN_TZ)
                ts.vpg.write_dataset(
                    DATASET_KEY,
                    df,
                    ttl_seconds=TTL_SECONDS,
                    source_version=now.isoformat(),
                )
                ts._log(f"TOUR CACHE: PostgreSQL {DATASET_KEY} rows={len(df)}")
        except Exception as exc:
            # Cache failure must not change existing Auto Check behaviour.
            ts._log(f"TOUR CACHE WARN: {type(exc).__name__}: {exc}")
        return df

    def run_sync_with_tour_cache():
        state["loaded_during_run"] = False
        result = original_run_sync()
        if not state["loaded_during_run"]:
            if _cache_disabled(ts):
                # Critical overload guard: do not touch Google Drive at all when
                # this run would only be refreshing the Web V2 Tour cache.
                ts._log("TOUR CACHE PAUSED BY ADMIN: bỏ qua tải TourVera cho cache")
                return result
            try:
                load_and_cache()
            except Exception as exc:
                # TimeSoft snapshot success is more important than Tour fallback.
                # The next scheduled run will retry this cache refresh.
                ts._log(f"TOUR CACHE REFRESH WARN: {type(exc).__name__}: {exc}")
        return result

    ts.load_bang_tour_input = load_and_cache
    ts.run_sync = run_sync_with_tour_cache
    ts._tour_snapshot_cache_patch_release = RELEASE

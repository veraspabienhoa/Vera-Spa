"""Persist the TourVera Input snapshot loaded by background jobs.

Web requests must not download the XLSM from Google Drive. The scheduled
TimeSoft/Auto Check jobs cache that same DataFrame in PostgreSQL and Web V2
consumes it locally. If Auto Check is paused and therefore does not read the
workbook, the snapshot job still refreshes the cache once before it exits.
"""
from __future__ import annotations

from datetime import datetime


RELEASE = "tourvera-postgres-cache-2026-08-31-v2"
DATASET_KEY = "tourvera_input_today"
TTL_SECONDS = 15 * 60


def install(ts) -> None:
    if getattr(ts, "_tour_snapshot_cache_patch_release", "") == RELEASE:
        return

    original_load = ts.load_bang_tour_input
    original_run_sync = ts.run_sync
    state = {"loaded_during_run": False}

    def load_and_cache():
        df = original_load()
        state["loaded_during_run"] = True
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

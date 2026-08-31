"""Persist the TourVera Input snapshot loaded by background jobs.

Web requests must not download the XLSM from Google Drive.  The scheduled
TimeSoft/Auto Check jobs already read TourVera, so cache that same DataFrame in
PostgreSQL and let attendance/alert APIs consume it locally.
"""
from __future__ import annotations

from datetime import datetime


RELEASE = "tourvera-postgres-cache-2026-08-31-v1"
DATASET_KEY = "tourvera_input_today"
TTL_SECONDS = 15 * 60


def install(ts) -> None:
    if getattr(ts, "_tour_snapshot_cache_patch_release", "") == RELEASE:
        return

    original = ts.load_bang_tour_input

    def load_and_cache():
        df = original()
        try:
            if df is not None and not getattr(df, "empty", True):
                now = datetime.now(ts.VN_TZ)
                ts.vpg.write_dataset(
                    DATASET_KEY,
                    df,
                    ttl_seconds=TTL_SECONDS,
                    source_version=now.isoformat(),
                )
                ts._log(
                    f"TOUR CACHE: PostgreSQL {DATASET_KEY} rows={len(df)}"
                )
        except Exception as exc:
            # Cache failure must not change existing Auto Check behaviour.
            ts._log(f"TOUR CACHE WARN: {type(exc).__name__}: {exc}")
        return df

    ts.load_bang_tour_input = load_and_cache
    ts._tour_snapshot_cache_patch_release = RELEASE

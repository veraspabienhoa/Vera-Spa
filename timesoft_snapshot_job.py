"""Five-minute TimeSoft snapshot job.

The external scheduler owns cadence. Each invocation performs exactly one TimeSoft
sync and exits; there is no 30-second polling tail competing with application work.
"""
from __future__ import annotations

import sys

import timesoft_sync_job as ts
from timesoft_detailed_checkin import install as install_detailed_checkin
from timesoft_http_auth import install as install_http_auth
from timesoft_recalculate_checkin import install as install_recalculate_checkin
from timesoft_tour_snapshot_cache import install as install_tour_snapshot_cache

RELEASE = "timesoft-direct-attendance-2026-09-16-v4-5min"

install_recalculate_checkin(ts)
install_detailed_checkin(ts)
install_http_auth(ts)
install_tour_snapshot_cache(ts)


def _skip_tour_penalties(*_args, **_kwargs):
    return {"eligible": 0, "added": 0, "skipped": 0, "errors": 0}


def main() -> int:
    ts.process_tour_penalties = _skip_tour_penalties
    ts._log(
        "V85.2 DIRECT ATTENDANCE: one TimeSoft -> PostgreSQL synchronization per "
        "scheduled run; scheduler cadence is five minutes; no fast polling tail."
    )
    return int(ts.run_sync())


if __name__ == "__main__":
    sys.exit(main())

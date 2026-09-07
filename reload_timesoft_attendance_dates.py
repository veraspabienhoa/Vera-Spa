from __future__ import annotations

import os
from datetime import date, datetime

import timesoft_sync_job as ts
from timesoft_detailed_checkin import install as install_detailed_checkin


TARGET_DATES = [date(2026, 9, 6), date(2026, 9, 7)]


def main() -> int:
    install_detailed_checkin(ts)
    session = ts.create_authenticated_session()
    today = datetime.now(ts.VN_TZ).date()

    for target_date in TARGET_DATES:
        checkin_df, meta = ts.fetch_checkin(session, target_date)
        source_version = f"manual-reload-{target_date.isoformat()}"
        key = ts._key("timesoft_employee_checkin", target_date)
        ts.vpg.write_dataset(
            key,
            checkin_df,
            ttl_seconds=ts.TIMESOFT_HISTORY_TTL_SECONDS,
            source_version=source_version,
        )
        if target_date == today:
            ts.vpg.write_dataset(
                "timesoft_employee_checkin_today",
                checkin_df,
                ttl_seconds=1800,
                source_version=source_version,
            )
        ts._log(
            f"MANUAL ATTENDANCE RELOAD {target_date.isoformat()}: "
            f"rows={len(checkin_df)}; summary={int(meta.get('SummaryRows') or 0)}; "
            f"raw={int(meta.get('RawLogRows') or 0)}; detailed_ready={bool(meta.get('DetailedLogReady'))}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

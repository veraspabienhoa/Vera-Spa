"""V85.1 - Đồng bộ TimeSoft và phạt chấm công trực tiếp trong PostgreSQL.

Cloud Scheduler hiện gọi job nền theo chu kỳ khoảng 5 phút. Sau lần snapshot đầy
đủ, tiến trình giữ sống thêm một cửa sổ ngắn và đọc cả SearchElastic lẫn
ExportCheckinLogElastic của hôm nay mỗi 30 giây để đẩy đầy đủ FaceID vào
PostgreSQL. Nhờ vậy Web V2 có thể xác định đúng cặp nghỉ giữa ca và xóa cảnh báo
ngay sau khi nhân viên FaceID vào lại.

V85.1 ưu tiên đăng nhập HTTP /User/ValidateUser. Chromium/Playwright chỉ còn là
fallback tương thích, vì vậy thiếu thư viện hệ điều hành của Chromium không còn
được phép làm mất dữ liệu Chấm công.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

import timesoft_sync_job as ts
from timesoft_detailed_checkin import install as install_detailed_checkin
from timesoft_http_auth import install as install_http_auth
from timesoft_recalculate_checkin import install as install_recalculate_checkin
from timesoft_tour_snapshot_cache import install as install_tour_snapshot_cache


RELEASE = "timesoft-direct-attendance-penalty-2026-09-07-v3-http-auth"
FAST_INTERVAL_SECONDS = max(15, min(120, int(os.getenv("TIMESOFT_FAST_CHECKIN_SECONDS", "30") or 30)))
FAST_WINDOW_SECONDS = max(60, min(360, int(os.getenv("TIMESOFT_FAST_CHECKIN_WINDOW_SECONDS", "240") or 240)))

# Preserve the legacy browser recalculation fallback and detailed FaceID merge,
# then make the normal session browserless. Explicitly rejected credentials are
# reported immediately instead of being retried through a broken Chromium.
install_recalculate_checkin(ts)
install_detailed_checkin(ts)
install_http_auth(ts)
# Performance: persist TourVera Input for Web V2 reads, unless Admin pauses it.
install_tour_snapshot_cache(ts)


def _skip_tour_penalties(*_args, **_kwargs):
    """The frequent job owns direct TimeSoft late penalties, not Tour penalties."""
    return {"eligible": 0, "added": 0, "skipped": 0, "errors": 0}


def _write_today_checkin(checkin_df) -> None:
    today = datetime.now(ts.VN_TZ).date()
    ts.vpg.write_dataset(
        "timesoft_employee_checkin_today",
        checkin_df,
        ttl_seconds=1800,
        source_version=today.isoformat(),
    )


def _fast_checkin_tail() -> None:
    deadline = time.monotonic() + FAST_WINDOW_SECONDS
    session = None
    success = 0
    errors = 0
    while time.monotonic() < deadline:
        started = time.monotonic()
        try:
            if session is None:
                session = ts.create_authenticated_session()
                ts._log(
                    f"FAST CHECKIN AUTH: {getattr(session, '_vera_timesoft_auth_mode', 'unknown')}"
                )
            today = datetime.now(ts.VN_TZ).date()
            checkin_df, meta = ts.fetch_checkin(session, today)
            _write_today_checkin(checkin_df)
            employee_map = ts.load_employee_name_map()
            missing_result = ts.missing_checkin_notifications.notify_missing_scheduled_checkins(
                ts.vpg.get_engine(), checkin_df, today, employee_map, datetime.now(ts.VN_TZ),
            )
            success += 1
            ts._log(
                f"FAST CHECKIN {RELEASE}: combined={len(checkin_df)}; "
                f"summary={int(meta.get('SummaryRows') or 0)}; "
                f"raw={int(meta.get('RawLogRows') or 0)}; "
                f"total={int(meta.get('Total') or 0)}; "
                f"missing_alerts={missing_result.get('notified', 0)}; "
                f"interval={FAST_INTERVAL_SECONDS}s"
            )
        except Exception as exc:
            errors += 1
            session = None
            ts._log(f"FAST CHECKIN ERROR: {type(exc).__name__}: {exc}")

        remaining = FAST_INTERVAL_SECONDS - (time.monotonic() - started)
        if remaining > 0 and time.monotonic() + remaining < deadline:
            time.sleep(remaining)

    ts._log(f"FAST CHECKIN DONE: success={success}; errors={errors}; window={FAST_WINDOW_SECONDS}s")


def main() -> int:
    ts.process_tour_penalties = _skip_tour_penalties
    ts._log(
        f"V85.1 DIRECT ATTENDANCE: HTTP auth -> TimeSoft -> PostgreSQL -> "
        "phạt đi trễ đầu ca/vào lại trễ sau nghỉ giữa ca; "
        f"fast check-in mỗi {FAST_INTERVAL_SECONDS}s trong {FAST_WINDOW_SECONDS}s; "
        "Playwright chỉ fallback; TourVera cache theo công tắc Admin."
    )
    result = int(ts.run_sync())
    if result != 0:
        return result
    try:
        _fast_checkin_tail()
    except Exception as exc:
        ts._log(f"FAST CHECKIN TAIL ABORTED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

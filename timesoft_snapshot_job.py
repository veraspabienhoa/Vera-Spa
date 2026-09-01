"""V84.8 - Cloud Run Job đồng bộ snapshot TimeSoft + raw FaceID fast tail.

Cloud Scheduler hiện gọi job nền theo chu kỳ khoảng 5 phút. Sau lần snapshot đầy
đủ (có Tính lại ngày công), tiến trình giữ sống thêm một cửa sổ ngắn và đọc cả
SearchElastic lẫn ExportCheckinLogElastic của hôm nay mỗi 30 giây để đẩy đầy đủ
FaceID vào PostgreSQL. Nhờ vậy Web V2 có thể xác định đúng cặp nghỉ giữa ca và
xóa cảnh báo ngay sau khi nhân viên FaceID vào lại, thay vì chỉ thấy mốc đầu/cuối.

Fast tail chỉ cập nhật dataset `timesoft_employee_checkin_today`; không tải hóa
đơn, không chạy Auto Check, không ghi phạt và không đụng dữ liệu lịch sử.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

import timesoft_sync_job as ts
from timesoft_detailed_checkin import install as install_detailed_checkin
from timesoft_recalculate_checkin import install as install_recalculate_checkin
from timesoft_tour_snapshot_cache import install as install_tour_snapshot_cache


RELEASE = "timesoft-snapshot-fast-tail-2026-09-02-v2-detailed-faceid"
FAST_INTERVAL_SECONDS = max(15, min(120, int(os.getenv("TIMESOFT_FAST_CHECKIN_SECONDS", "30") or 30)))
FAST_WINDOW_SECONDS = max(60, min(360, int(os.getenv("TIMESOFT_FAST_CHECKIN_WINDOW_SECONDS", "240") or 240)))

# Accuracy first: click TimeSoft "Tính lại ngày công" before the initial login
# session is converted to requests cookies, and preserve every raw FaceID event
# from TimeSoft's own detailed check-in export.
install_recalculate_checkin(ts)
install_detailed_checkin(ts)
# Performance: persist TourVera Input for Web V2 reads, unless Admin pauses it.
install_tour_snapshot_cache(ts)


_original_auto_load_config = ts.auto_check.load_config


def _snapshot_only_auto_config(conn):
    """Preserve policy values but never execute/consume Auto Check in this job."""
    cfg = dict(_original_auto_load_config(conn) or {})
    cfg["status"] = ts.AUTO_PENALTY_PAUSED
    cfg["manual_run_requested"] = False
    return cfg


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
                # New login also runs the installed "Tính lại ngày công" guard,
                # giving each fast-tail window a fresh authoritative baseline.
                session = ts.create_authenticated_session()
            today = datetime.now(ts.VN_TZ).date()
            checkin_df, meta = ts.fetch_checkin(session, today)
            _write_today_checkin(checkin_df)
            success += 1
            ts._log(
                f"FAST CHECKIN {RELEASE}: combined={len(checkin_df)}; "
                f"summary={int(meta.get('SummaryRows') or 0)}; "
                f"raw={int(meta.get('RawLogRows') or 0)}; "
                f"total={int(meta.get('Total') or 0)}; "
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
    # run_sync() now reads PostgreSQL Auto Check config directly. Override that
    # reader for this process so the frequent snapshot job cannot also download
    # TourVera / write penalties. The dedicated Auto Check job remains unchanged.
    ts.auto_check.load_config = _snapshot_only_auto_config
    ts._log(
        f"V84.8 SNAPSHOT-ONLY: Tính lại ngày công -> SearchElastic + raw FaceID -> PostgreSQL; "
        f"fast check-in mỗi {FAST_INTERVAL_SECONDS}s trong {FAST_WINDOW_SECONDS}s; "
        "không chạy Auto Check; TourVera cache theo công tắc Admin."
    )
    result = int(ts.run_sync())
    if result != 0:
        return result
    try:
        _fast_checkin_tail()
    except Exception as exc:
        # Initial authoritative snapshot already succeeded. A fast-tail problem
        # must not turn the whole scheduled execution into a failed sync.
        ts._log(f"FAST CHECKIN TAIL ABORTED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

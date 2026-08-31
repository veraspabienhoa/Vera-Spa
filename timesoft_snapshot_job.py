"""V84.6 - Cloud Run Job đồng bộ snapshot TimeSoft chính xác.

Job này được Cloud Scheduler gọi định kỳ (hiện mỗi 5 phút). Trước khi đọc
SearchElastic, Playwright bắt buộc bấm "Tính lại ngày công" trên báo cáo
check-in TimeSoft để dữ liệu FaceID/check-out đã được TimeSoft tổng hợp đầy đủ.

Job 5 phút chỉ đồng bộ snapshot. Auto Check/ghi phạt chạy ở job chuyên biệt,
không được lặp lại ở đây. TourVera chỉ được tải để làm mới cache Web V2 khi
Admin chưa tạm dừng chức năng này.
"""
from __future__ import annotations

import sys
import timesoft_sync_job as ts
from timesoft_recalculate_checkin import install as install_recalculate_checkin
from timesoft_tour_snapshot_cache import install as install_tour_snapshot_cache


# Accuracy first: click TimeSoft "Tính lại ngày công" before fetch_checkin().
install_recalculate_checkin(ts)
# Performance: persist TourVera Input for Web V2 reads, unless Admin pauses it.
install_tour_snapshot_cache(ts)


_original_auto_load_config = ts.auto_check.load_config


def _snapshot_only_auto_config(conn):
    """Preserve policy values but never execute/consume Auto Check in this job."""
    cfg = dict(_original_auto_load_config(conn) or {})
    cfg["status"] = ts.AUTO_PENALTY_PAUSED
    cfg["manual_run_requested"] = False
    return cfg


def main() -> int:
    # run_sync() now reads PostgreSQL Auto Check config directly. Override that
    # reader for this process so the frequent snapshot job cannot also download
    # TourVera / write penalties. The dedicated Auto Check job remains unchanged.
    ts.auto_check.load_config = _snapshot_only_auto_config
    ts._log(
        "V84.6 SNAPSHOT-ONLY: Tính lại ngày công -> TimeSoft/PostgreSQL; "
        "không chạy Auto Check; TourVera cache theo công tắc Admin."
    )
    return int(ts.run_sync())


if __name__ == "__main__":
    sys.exit(main())

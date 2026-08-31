"""V84.5 - Cloud Run Job đồng bộ snapshot TimeSoft chính xác.

Job này được Cloud Scheduler gọi định kỳ (hiện mỗi 5 phút). Trước khi đọc
SearchElastic, Playwright bắt buộc bấm "Tính lại ngày công" trên báo cáo
check-in TimeSoft để dữ liệu FaceID/check-out đã được TimeSoft tổng hợp đầy đủ.
TourVera Input được cache vào PostgreSQL khi background job đọc workbook, để
Web V2 không phải tải Google Drive trong luồng mở trang.
"""
from __future__ import annotations

import sys
import timesoft_sync_job as ts
from timesoft_recalculate_checkin import install as install_recalculate_checkin
from timesoft_tour_snapshot_cache import install as install_tour_snapshot_cache


# Accuracy first: click TimeSoft "Tính lại ngày công" before fetch_checkin().
install_recalculate_checkin(ts)
# Performance: persist the already-downloaded TourVera Input for Web V2 reads.
install_tour_snapshot_cache(ts)


_original_load_auto_penalty_config = ts.load_auto_penalty_config


def _snapshot_only_config(client):
    """Đọc ngưỡng thật nhưng luôn khóa phần ghi phạt cho job snapshot legacy."""
    cfg = _original_load_auto_penalty_config(client)
    cfg = dict(cfg or {})
    cfg["paused"] = True
    cfg["status"] = "SNAPSHOT_ONLY"
    return cfg


def main() -> int:
    ts.load_auto_penalty_config = _snapshot_only_config
    ts._log(
        "V84.5 SNAPSHOT: Tính lại ngày công -> đồng bộ TimeSoft/PostgreSQL; "
        "TourVera cache PostgreSQL."
    )
    return int(ts.run_sync())


if __name__ == "__main__":
    sys.exit(main())

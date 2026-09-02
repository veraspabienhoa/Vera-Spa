"""VERA Auto Update V3.9 policy wrapper.

Keeps the hardened V93.4 runtime/login/run-log wrapper and changes business
policy only:
- Auto late threshold comes from the Nội quy configuration.
- TimeSoft late penalties are delegated to the frequent PostgreSQL sync, so
  this legacy 20:00 Sheet job cannot charge the same violation twice.
- Support reasons retain their legacy grace allowances (120/180/60 minutes),
  but are evaluated by the same five-minute engine.
- Bảng tour uses the current LoaiNghi names <=30/<=60/<=120/>120.
- TimeSoft check-in is recalculated in the browser before SearchElastic is read.
"""
from __future__ import annotations

import sys

import auto_penalty_runtime_wrapper as base
from timesoft_recalculate_checkin import install as install_recalculate_checkin
from timesoft_tour_snapshot_cache import install as install_tour_snapshot_cache


ts = base.ts
daily = base.daily

# base has already installed the hardened login wrapper. Wrap that final login
# so the same browser session clicks TimeSoft "Tính lại ngày công" first.
install_recalculate_checkin(ts)
install_tour_snapshot_cache(ts)

DEFAULT_AUTO_THRESHOLD_MINUTES = 5


def _configured_threshold(cfg) -> int:
    try:
        return max(1, min(180, int((cfg or {}).get("threshold_minutes", DEFAULT_AUTO_THRESHOLD_MINUTES))))
    except (TypeError, ValueError):
        return DEFAULT_AUTO_THRESHOLD_MINUTES


# Exact current catalog label plus backward-compatible alias.
daily.SUPPORT_LATE_ALLOWANCES.update({
    ts._norm("Hỗ trợ Ca 1 sau 23H đi trễ 2 tiếng"): 120,
    ts._norm("Hỗ trợ Ca 1 đi trễ 2 tiếng"): 120,
    ts._norm("Hỗ trợ Ca 1 sau 0:0H đi trễ 3 tiếng"): 180,
    ts._norm("Hỗ trợ Ca 2 sau 0:0H đi trễ 1 tiếng"): 60,
})

# Current LoaiNghi naming: inclusive upper bounds. Keep aliases for old sheets.
_ORIGINAL_OUTSIDE_REASON = ts._outside_reason


def _outside_reason_v39(minutes, catalog):
    value = float(minutes or 0)
    if value <= 30:
        candidates = [
            "Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút",
            "Ra ngoài vào muộn dưới 30 phút",
        ]
    elif value <= 60:
        candidates = [
            "Ra ngoài vào muộn nhỏ hơn hoặc bằng 60 phút",
            "Ra ngoài vào muộn dưới 60 phút",
        ]
    elif value <= 120:
        candidates = [
            "Ra ngoài vào muộn nhỏ hơn hoặc bằng 120 phút",
            "Ra ngoài vào muộn dưới 120 phút",
        ]
    else:
        candidates = [
            "Ra ngoài vào muộn trên 120 phút",
            "Ra ngoài vào muộn từ 120 phút trở lên",
        ]
    for name in candidates:
        item = ts._catalog_item(catalog, name)
        if item:
            return item
    return _ORIGINAL_OUTSIDE_REASON(value, catalog)


ts._outside_reason = _outside_reason_v39
ts.OUTSIDE_LATE_EXCLUDED.update({
    ts._norm("Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút"),
    ts._norm("Ra ngoài vào muộn nhỏ hơn hoặc bằng 60 phút"),
    ts._norm("Ra ngoài vào muộn nhỏ hơn hoặc bằng 120 phút"),
    ts._norm("Ra ngoài vào muộn trên 120 phút"),
})


def _process_timesoft_v39(client, cfg, employee_map, catalog, supports, checkin_df):
    daily._log(
        "V3.9 TIMESOFT DELEGATED: phạt đi trễ đã được ghi trực tiếp vào "
        "PostgreSQL bởi job đồng bộ thường xuyên; bỏ qua writer Sheet 20:00."
    )
    return {
        "eligible": 0,
        "added": 0,
        "skipped": 0,
        "errors": 0,
        "support_skipped": 0,
        "delegated_to_postgres_sync": True,
    }, []


daily.process_timesoft_today = _process_timesoft_v39


_ORIGINAL_PROCESS_TOUR = daily.process_tour_today


def _process_tour_v39(client, cfg, employee_map, catalog):
    cfg_v39 = dict(cfg or {})
    threshold = _configured_threshold(cfg_v39)
    cfg_v39["threshold_minutes"] = threshold
    ts.AUTO_PENALTY_MINUTES = threshold
    return _ORIGINAL_PROCESS_TOUR(client, cfg_v39, employee_map, catalog)


daily.process_tour_today = _process_tour_v39


if __name__ == "__main__":
    sys.exit(base._run_daily_with_persistent_log())

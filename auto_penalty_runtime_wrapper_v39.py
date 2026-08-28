"""VERA Auto Update V3.9 policy wrapper.

Keeps the hardened V93.4 runtime/login/run-log wrapper and changes business
policy only:
- Auto late threshold is exactly 5 minutes.
- Registered Đi trễ phát sinh / CÓ phép / KHÔNG phép uses 17:00:00 as the
  standard check-in for that employee/date.
- Support reasons retain their legacy grace allowances (120/180/60 minutes),
  but are evaluated by the same five-minute engine.
- Bảng tour uses the current LoaiNghi names <=30/<=60/<=120/>120.
"""
from __future__ import annotations

import sys
from datetime import datetime

import auto_penalty_runtime_wrapper as base


ts = base.ts
daily = base.daily

AUTO_THRESHOLD_MINUTES = 5
STANDARD_1700_REASONS = {
    ts._reason_key("Đi trễ phát sinh"),
    ts._reason_key("Đi trễ CÓ phép"),
    ts._reason_key("Đi trễ KHÔNG phép"),
}

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


def _date_employee_1700_index(client):
    index = set()
    try:
        rows = daily._load_all_leave_rows_new(client)
    except Exception as exc:
        daily._log(f"V3.9 STANDARD 17:00 WARN: không đọc được lịch nghỉ: {type(exc).__name__}: {exc}")
        return index
    for row in rows or []:
        reason = ts._reason_key(row.get("Lý do nghỉ", ""))
        if reason not in STANDARD_1700_REASONS:
            continue
        dkey = ts._date_key(row.get("Ngày"))
        ekey = ts._employee_key(row.get("Tên nhân viên"))
        if dkey and ekey:
            index.add((dkey, ekey))
    return index


_ORIGINAL_PROCESS_TIMESOFT = daily.process_timesoft_today


def _process_timesoft_v39(client, cfg, employee_map, catalog, supports, checkin_df):
    # A configured value above 5 must not silently move the business threshold.
    cfg_v39 = dict(cfg or {})
    cfg_v39["threshold_minutes"] = AUTO_THRESHOLD_MINUTES
    ts.AUTO_PENALTY_MINUTES = AUTO_THRESHOLD_MINUTES

    if checkin_df is None or getattr(checkin_df, "empty", True):
        return _ORIGINAL_PROCESS_TIMESOFT(client, cfg_v39, employee_map, catalog, supports, checkin_df)

    adjusted = checkin_df.copy()
    standard_index = _date_employee_1700_index(client)
    today = datetime.now(ts.VN_TZ).date()
    adjusted_count = 0

    for idx, row in adjusted.iterrows():
        raw_name = ts._timesoft_row_value(row, [
            "employeeInfo.Name", "EmployeeName", "employeeName", "Name", "FullName",
        ])
        employee = ts.canonical_employee(raw_name, employee_map)
        if not employee:
            continue
        raw_date = ts._timesoft_row_value(row, [
            "WorkDateStr", "WorkDate", "CreateDateStr", "CreateDate",
        ])
        work_date = ts._parse_date(raw_date) or today
        key = (work_date.strftime("%d/%m/%Y"), ts._employee_key(employee))
        if key not in standard_index:
            continue
        adjusted.at[idx, "StartWorkTime"] = "17:00:00"
        # If alternative start columns already exist, keep every parser aligned.
        for column in ("WorkTimeStart", "ShiftStartTime"):
            if column in adjusted.columns:
                adjusted.at[idx, column] = "17:00:00"
        adjusted_count += 1

    if adjusted_count:
        daily._log(
            f"V3.9 STANDARD 17:00: áp dụng {adjusted_count} dòng TimeSoft có "
            "Đi trễ phát sinh/CÓ phép/KHÔNG phép."
        )
    return _ORIGINAL_PROCESS_TIMESOFT(client, cfg_v39, employee_map, catalog, supports, adjusted)


daily.process_timesoft_today = _process_timesoft_v39


_ORIGINAL_PROCESS_TOUR = daily.process_tour_today


def _process_tour_v39(client, cfg, employee_map, catalog):
    cfg_v39 = dict(cfg or {})
    cfg_v39["threshold_minutes"] = AUTO_THRESHOLD_MINUTES
    ts.AUTO_PENALTY_MINUTES = AUTO_THRESHOLD_MINUTES
    return _ORIGINAL_PROCESS_TOUR(client, cfg_v39, employee_map, catalog)


daily.process_tour_today = _process_tour_v39


if __name__ == "__main__":
    sys.exit(base._run_daily_with_persistent_log())

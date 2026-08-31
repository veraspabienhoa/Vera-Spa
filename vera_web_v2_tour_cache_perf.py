"""PostgreSQL-only TourVera reader for Web V2 attendance requests.

Background jobs download TourVera and persist `tourvera_input_today`. Web V2
must never download/parse the XLSM while a user is opening Chấm công, Đăng ký
nghỉ, or while the global break-alert poll is running.

Admin can pause only the frequent Google Drive -> PostgreSQL refresh. Break
alerts continue. While refresh is paused, Web V2 may use the last cached
TourVera payload from the same Vietnam business day even after its normal TTL
expires. TimeSoft remains authoritative whenever it already contains a break
start/return, so this cache is only a fallback source.
"""
from __future__ import annotations

from datetime import time, timedelta
from typing import Any

from sqlalchemy import text

import vera_tour_cache_control as cache_control
import vera_web_v2_attendance_break_alerts as alerts


RELEASE = "tourvera-web-postgres-cache-2026-08-31-v3-alerts-continue"
DATASET_KEY = cache_control.DATASET_KEY


def tour_records(conn) -> list[dict[str, Any]]:
    """Return PostgreSQL-cached TourVera without ever touching Google Drive.

    Normal mode requires the short-lived fresh cache. When Admin pauses the
    cache-only refresh, the last cache written today remains readable so break
    alerts do not disappear merely because Google Drive refresh is paused.
    Yesterday's payload is never reused on a new business day.
    """
    paused = cache_control.disabled(conn)
    if paused:
        row = conn.execute(text("""
            SELECT payload
            FROM vera_dataset_cache
            WHERE dataset_key=:key
              AND (updated_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                  = (NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            LIMIT 1
        """), {"key": DATASET_KEY}).scalar_one_or_none()
    else:
        row = conn.execute(text("""
            SELECT payload
            FROM vera_dataset_cache
            WHERE dataset_key=:key
              AND (expires_at IS NULL OR expires_at > NOW())
            LIMIT 1
        """), {"key": DATASET_KEY}).scalar_one_or_none()
    if not isinstance(row, list):
        return []
    return [dict(item) for item in row if isinstance(item, dict)]


def _columns(records: list[dict[str, Any]]) -> tuple[str, str, str, str]:
    if not records:
        return "", "", "", ""
    keys: list[str] = []
    seen = set()
    for row in records[:20]:
        for key in row.keys():
            label = str(key or "").strip()
            if label and label not in seen:
                seen.add(label)
                keys.append(label)
    name_column = alerts.people._find_column(keys, "Tên nhân viên")
    break_column = alerts.people._find_column(keys, "Break") or alerts.people._find_column(keys, "Breaktime")
    break_out_column = alerts.people._find_column(keys, "Giờ ra")
    break_in_column = alerts.people._find_column(keys, "Giờ vào")
    return name_column, break_column, break_out_column, break_in_column


def active_break_map(conn, work_day) -> dict[str, dict[str, Any]]:
    records = tour_records(conn)
    name_column, break_column, break_out_column, break_in_column = _columns(records)
    if not all((name_column, break_column, break_out_column, break_in_column)):
        return {}

    aliases = alerts._employee_aliases(conn)
    output: dict[str, dict[str, Any]] = {}
    for row in records:
        if alerts._norm(row.get(break_column)) != "break":
            continue
        username = aliases.get(alerts._norm(row.get(name_column)))
        if not username:
            continue
        break_out = alerts._parse_clock(row.get(break_out_column), work_day)
        break_in = alerts._parse_clock(row.get(break_in_column), work_day)
        if break_out is None or break_out.time() < time(15, 0):
            continue
        if break_in is not None and break_in < break_out:
            break_in += timedelta(days=1)
        output[alerts._norm(username)] = {
            "break_out": break_out,
            "break_in": break_in,
            "break_flag": str(row.get(break_column) or ""),
        }
    return output


def completed_pairs(conn, work_day) -> dict[str, dict[str, Any]]:
    records = tour_records(conn)
    name_column, break_column, break_out_column, break_in_column = _columns(records)
    if not all((name_column, break_out_column, break_in_column)):
        return {}

    aliases = alerts._employee_aliases(conn)
    output: dict[str, dict[str, Any]] = {}
    for row in records:
        username = aliases.get(alerts._norm(row.get(name_column)))
        if not username:
            continue
        break_out = alerts._parse_clock(row.get(break_out_column), work_day)
        break_in = alerts._parse_clock(row.get(break_in_column), work_day)
        if break_out is None or break_in is None or break_out.time() < time(15, 0):
            continue
        if break_in < break_out:
            break_in += timedelta(days=1)
        # TourVera often stores clock-only values. _parse_clock attaches work_day.
        if break_out.date() != work_day:
            continue
        output[alerts._norm(username)] = {
            "break_out": break_out,
            "break_in": break_in,
            "break_flag": str(row.get(break_column) or "") if break_column else "",
            "completed_pair": True,
        }
    return output


def install() -> None:
    if getattr(alerts, "_tour_cache_perf_release", "") == RELEASE:
        return
    alerts._tour_break_map = active_break_map
    alerts._tour_cache_perf_release = RELEASE

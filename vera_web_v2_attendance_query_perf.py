"""Fast PostgreSQL reader for Web V2 attendance.

The original 4.2 reader selected every `timesoft_employee_checkin_20%` payload
and then discarded out-of-range dates in Python.  Attendance is opened often
and is also reused by break-alert polling, so that pattern repeatedly decoded
all historical JSON.  This patch keeps the exact 4.2 business logic but asks
PostgreSQL only for the selected date keys (plus today's alias/raw snapshot).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text

import vera_web_v2_attendance_v42 as v42
import vera_web_v2_snapshot as snapshot
from vera_attendance_rules import apply_break_restriction


RELEASE = "attendance-date-key-query-2026-08-31-v1"


def _keys_for_range(start: date, end: date) -> list[str]:
    keys: list[str] = []
    day = start
    while day <= end:
        stamp = day.strftime("%Y%m%d")
        keys.append(f"timesoft_employee_checkin_{stamp}")
        keys.append(f"timesoft_employee_checkin_{stamp}_raw")
        day += timedelta(days=1)
    today = datetime.now().date()
    if start <= today <= end:
        keys.insert(0, "timesoft_employee_checkin_today")
    return list(dict.fromkeys(keys))


def _datasets(conn, start: date, end: date):
    keys = _keys_for_range(start, end)
    if not keys:
        return []
    params = {f"k{index}": key for index, key in enumerate(keys)}
    placeholders = ",".join(f":k{index}" for index in range(len(keys)))
    sql = text(f"""
        SELECT dataset_key, payload
        FROM vera_dataset_cache
        WHERE dataset_key IN ({placeholders})
        ORDER BY CASE WHEN dataset_key='timesoft_employee_checkin_today' THEN 0
                      WHEN dataset_key LIKE '%_raw' THEN 1 ELSE 2 END,
                 dataset_key DESC
    """)
    return conn.execute(sql, params).mappings().all()


def _records_v42_fast(conn, start: date, end: date) -> list[dict[str, Any]]:
    definitions, break_config = snapshot._shift_break_settings(conn)
    aliases, roles = v42._eligible_aliases(conn)
    datasets = _datasets(conn, start, end)

    grouped: dict[tuple[date, str], dict[str, Any]] = defaultdict(
        lambda: {"rows": [], "punches": []}
    )
    for dataset in datasets:
        payload = dataset.get("payload") or []
        if not isinstance(payload, list):
            continue
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            employee = v42._canonical_employee(raw, aliases)
            if not employee:
                continue
            explicit_day = v42._explicit_work_day(raw)
            punches = v42._row_punches(raw, explicit_day)
            work_day = explicit_day or v42._work_day_for_row(raw, punches)
            if not work_day or not start <= work_day <= end:
                continue
            bucket = grouped[(work_day, employee)]
            bucket["rows"].append(raw)
            bucket["punches"].extend(punches)

    output: list[dict[str, Any]] = []
    for (work_day, employee), bucket in grouped.items():
        rows = bucket["rows"]
        if not rows:
            continue
        representative = max(rows, key=v42._representative_score)
        cfg = snapshot._shift_config(representative, definitions, break_config)
        arrival_status = v42._norm(representative.get("GoWorkTypeName"))
        departure_status = v42._norm(representative.get("LastCheckInTypeName"))
        restricted_reasons = []
        if "di tre" in arrival_status:
            restricted_reasons.append("đi trễ")
        if "ve som" in departure_status and v42._departure_status_is_final(
            bucket["punches"],
            work_day=work_day,
            representative=representative,
            cluster_minutes=int(cfg.get("faceid_cluster_minutes") or 10),
        ):
            restricted_reasons.append("về sớm")
        cfg = apply_break_restriction(cfg, restricted_reasons)
        faceid = v42._break_from_punches(
            bucket["punches"],
            work_day=work_day,
            representative=representative,
            cfg=cfg,
        )
        base = snapshot._record(representative, definitions, break_config)
        base.update(faceid)
        base["date"] = work_day.strftime("%d/%m/%Y")
        base["employee_name"] = employee
        base["employee_role"] = roles.get(v42._norm(employee), "")
        raw_code = v42._first(representative, v42.CODE_ALIASES)
        if raw_code:
            base["employee_code"] = str(raw_code).strip()
        if not str(base.get("check_in") or "").strip() and faceid.get("faceid_check_in"):
            base["check_in"] = faceid["faceid_check_in"]
        base["check_out"] = faceid.get("faceid_check_out") or ""
        base["faceid_last"] = faceid.get("faceid_last") or ""
        base["attendance_source"] = (
            "TimeSoft FaceID chi tiết"
            if faceid.get("raw_faceid_count", 0) >= 2
            else "TimeSoft"
        )
        output.append(base)

    return sorted(
        output,
        key=lambda item: (
            datetime.strptime(item["date"], "%d/%m/%Y"),
            v42._norm(item.get("employee_name")),
        ),
    )


def install() -> None:
    if getattr(v42, "_attendance_query_perf_release", "") == RELEASE:
        return
    # install_attendance_v42() later assigns snapshot._records from this symbol.
    v42._records_v42 = _records_v42_fast
    v42._attendance_query_perf_release = RELEASE

"""Fast PostgreSQL reader for Web V2 attendance.

The original 4.2 reader selected every `timesoft_employee_checkin_20%` payload
and then discarded out-of-range dates in Python. Attendance is opened often
and is also reused by break-alert polling, so this reader asks PostgreSQL only
for the selected date keys (plus the rolling today alias/raw snapshot).

The CHAM CONG screen must be roster-complete: every employee whose employment
status is `Dang lam viec`, across every VERA department, is returned even when
TimeSoft has not produced a FaceID row yet. TimeSoft remains authoritative for
actual punches; PostgreSQL `employees` is authoritative for who must appear.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import re
from typing import Any

from sqlalchemy import text

import vera_web_v2_attendance_v42 as v42
import vera_web_v2_snapshot as snapshot
from vera_attendance_rules import apply_break_restriction


RELEASE = "attendance-date-key-query-2026-09-07-v3-active-roster"

ROLE_DEPARTMENT = {
    "nhanvien": "Nhân viên + Leader",
    "leader": "Nhân viên + Leader",
    "quanly": "Quản lý",
    "letan": "Lễ tân",
    "locker": "Locker",
    "tapvu": "Tạp vụ",
    "admin": "Admin",
}


def _keys_for_range(start: date, end: date) -> list[str]:
    # Always read the small rolling alias. Around 00:00-07:00 Vietnam time,
    # ``datetime.now().date()`` on the UTC API host can still point at yesterday.
    keys: list[str] = ["timesoft_employee_checkin_today"]
    day = start
    while day <= end:
        stamp = day.strftime("%Y%m%d")
        keys.append(f"timesoft_employee_checkin_{stamp}")
        keys.append(f"timesoft_employee_checkin_{stamp}_raw")
        day += timedelta(days=1)
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


def _active_roster(conn) -> list[dict[str, Any]]:
    """Return every active employee, independent of whether TimeSoft saw them."""
    rows = conn.execute(text("""
        SELECT username,
               COALESCE(full_name,'') AS full_name,
               lower(COALESCE(role,'nhanvien')) AS role,
               COALESCE(work_shift,'') AS work_shift,
               COALESCE(employment_start_date,'') AS employment_start_date,
               COALESCE(payload,'{}'::jsonb) AS payload
        FROM employees
        WHERE lower(COALESCE(role,'')) IN ('admin','quanly','nhanvien','leader','locker','letan','tapvu')
          AND COALESCE(payload->>'__deleted','false') <> 'true'
          AND lower(COALESCE(
                NULLIF(payload->>'Trạng thái làm việc',''),
                NULLIF(payload->>'employment_status',''),
                'Đang làm việc'
              )) = 'đang làm việc'
        ORDER BY COALESCE(stt,2147483647), username
    """)).mappings().all()
    return [dict(row) for row in rows if str(row.get("username") or "").strip()]


def _schedule_map(conn, start: date, end: date) -> dict[tuple[date, str], dict[str, Any]]:
    """Read daily schedules in one query; no per-employee query fan-out."""
    try:
        rows = conn.execute(text("""
            SELECT ws.work_date,
                   ws.employee_username,
                   ws.employee_name,
                   lower(COALESCE(ws.department,'')) AS department,
                   COALESCE(ws.shift_code,'') AS shift_code,
                   COALESCE(NULLIF(ws.start_time,''), d.start_time, '') AS start_time,
                   COALESCE(NULLIF(ws.end_time,''), d.end_time, '') AS end_time
            FROM vera_work_schedule ws
            LEFT JOIN vera_work_shift_definition d
              ON d.department=ws.department AND lower(d.shift_code)=lower(ws.shift_code)
            WHERE ws.work_date BETWEEN :start_date AND :end_date
        """), {"start_date": start, "end_date": end}).mappings().all()
    except Exception:
        return {}
    output: dict[tuple[date, str], dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        work_day = item.get("work_date")
        if not isinstance(work_day, date):
            continue
        for value in (item.get("employee_username"), item.get("employee_name")):
            key = v42._norm(value)
            if key:
                output[(work_day, key)] = item
    return output


def _parse_employee_shift(value: Any) -> tuple[str, str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", "", ""
    match = re.match(
        r"^(.*?)\s*\(\s*(\d{1,2}:\d{2})(?::\d{2})?\s*[-–→]\s*(\d{1,2}:\d{2})(?::\d{2})?\s*\)\s*$",
        raw,
    )
    if match:
        return match.group(1).strip(), match.group(2), match.group(3)
    return raw, "", ""


def _definition_for_shift(
    shift_name: str,
    definitions: list[dict[str, Any]],
    role: str,
) -> dict[str, Any]:
    wanted = v42._norm(shift_name)
    department = ROLE_DEPARTMENT.get(role, "")
    candidates = []
    for item in definitions:
        name = str(item.get("Tên ca") or "").strip()
        if not name or str(item.get("Trạng thái") or "").strip().casefold() == "đã xóa":
            continue
        item_department = str(item.get("Bộ phận") or "").strip()
        score = 0
        if v42._norm(name) == wanted:
            score += 100
        elif wanted and (v42._norm(name) in wanted or wanted in v42._norm(name)):
            score += 50
        if department and item_department == department:
            score += 10
        if score:
            candidates.append((score, item))
    return max(candidates, key=lambda value: value[0])[1] if candidates else {}


def _placeholder_record(
    roster: dict[str, Any],
    work_day: date,
    definitions: list[dict[str, Any]],
    break_config: dict[str, Any],
    schedule: dict[str, Any] | None,
) -> dict[str, Any]:
    username = str(roster.get("username") or "").strip()
    role = str(roster.get("role") or "").strip().lower()
    department = ROLE_DEPARTMENT.get(role, role or "Khác")
    work_shift = str(roster.get("work_shift") or "").strip()
    shift_name, shift_start, shift_end = _parse_employee_shift(work_shift)
    attendance_expected = True
    attendance_note = "Chưa có dữ liệu FaceID từ TimeSoft"

    if schedule:
        scheduled_shift = str(schedule.get("shift_code") or "").strip()
        scheduled_department = str(schedule.get("department") or "").strip().lower()
        if scheduled_shift:
            shift_name = scheduled_shift
        shift_start = str(schedule.get("start_time") or shift_start or "").strip()
        shift_end = str(schedule.get("end_time") or shift_end or "").strip()
        if scheduled_department:
            department = ROLE_DEPARTMENT.get(scheduled_department, {
                "quanly": "Quản lý", "letan": "Lễ tân", "locker": "Locker", "tapvu": "Tạp vụ",
            }.get(scheduled_department, department))
        if v42._norm(scheduled_shift) == "nghi":
            attendance_expected = False
            attendance_note = "Nghỉ theo Lịch làm việc"
    elif role in {"quanly", "letan", "locker", "tapvu"}:
        attendance_expected = False
        attendance_note = "Chưa xếp Lịch làm việc trong ngày"
    elif not shift_name:
        attendance_expected = False
        attendance_note = "Chưa phân ca làm việc"

    definition = _definition_for_shift(shift_name, definitions, role)
    if definition:
        shift_name = str(definition.get("Tên ca") or shift_name).strip()
        shift_start = str(definition.get("Giờ bắt đầu") or shift_start).strip()
        shift_end = str(definition.get("Giờ kết thúc") or shift_end).strip()

    representative = {
        "WorkDateStr": work_day.strftime("%d/%m/%Y"),
        "WorkTimeName": shift_name,
        "StartWorkTime": shift_start,
        "EndWorkTime": shift_end,
        "employeeInfo.Name": username,
        "EmployeeName": username,
    }
    cfg = snapshot._shift_config(representative, definitions, break_config)
    if role in {"quanly", "letan", "locker", "tapvu", "admin"}:
        cfg = {
            **cfg,
            "break_enabled": False,
            "break_planned_minutes": 0,
            "break_department": department,
        }
    else:
        cfg["break_department"] = department

    return {
        "date": work_day.strftime("%d/%m/%Y"),
        "employee_code": "",
        "employee_name": username,
        "employee_full_name": str(roster.get("full_name") or "").strip(),
        "employee_role": role,
        "shift": shift_name,
        "shift_start": shift_start,
        "shift_end": shift_end,
        "check_in": "",
        "check_out": "",
        "arrival_status": "",
        "departure_status": "",
        "late_minutes": 0,
        "early_minutes": 0,
        "total_minutes": 0,
        "punch_count": 0,
        **cfg,
        "break_actual_minutes": 0,
        "break_over_minutes": 0,
        "break_count": 0,
        "break_detail": "",
        "break_out": "",
        "break_in": "",
        "break_source": "",
        "break_method": "Chưa có FaceID",
        "break_status": "Chưa ghi nhận FaceID" if attendance_expected else attendance_note,
        "punch_times": [],
        "raw_faceid_count": 0,
        "faceid_check_in": "",
        "faceid_check_out": "",
        "faceid_last": "",
        "attendance_source": "Danh sách nhân viên PostgreSQL",
        "attendance_expected": attendance_expected,
        "attendance_roster_only": True,
        "attendance_note": attendance_note,
    }


def _append_missing_active_employees(
    conn,
    output: list[dict[str, Any]],
    start: date,
    end: date,
    definitions: list[dict[str, Any]],
    break_config: dict[str, Any],
) -> list[dict[str, Any]]:
    roster = _active_roster(conn)
    schedules = _schedule_map(conn, start, end)
    present = {
        (datetime.strptime(str(item.get("date") or ""), "%d/%m/%Y").date(), v42._norm(item.get("employee_name")))
        for item in output
        if str(item.get("date") or "").strip() and str(item.get("employee_name") or "").strip()
    }
    day = start
    while day <= end:
        for employee in roster:
            username = str(employee.get("username") or "").strip()
            key = (day, v42._norm(username))
            if not username or key in present:
                continue
            schedule = schedules.get(key)
            if schedule is None:
                full_name = v42._norm(employee.get("full_name"))
                if full_name:
                    schedule = schedules.get((day, full_name))
            output.append(_placeholder_record(employee, day, definitions, break_config, schedule))
            present.add(key)
        day += timedelta(days=1)
    return output


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
        if not str(base.get("break_department") or "").strip():
            base["break_department"] = ROLE_DEPARTMENT.get(base["employee_role"], base["employee_role"] or "Khác")
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
        base["attendance_expected"] = True
        base["attendance_roster_only"] = False
        output.append(base)

    _append_missing_active_employees(conn, output, start, end, definitions, break_config)
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
    # api_v38 imports attendance_policy_patch before install_attendance_v42(),
    # so install_attendance_v42 captures this roster-complete function.
    v42._records_v42 = _records_v42_fast
    v42._attendance_query_perf_release = RELEASE

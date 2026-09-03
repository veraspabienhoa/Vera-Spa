"""Attendance 4.2: optimized legacy Auto Check / raw FaceID reconstruction.

The old Streamlit system preferred detailed TimeSoft FaceID punches when
calculating a mid-shift break.  Web V2 previously looked only at sequential
summary fields on each cached row, which loses raw history such as repeated
12:45 / 18:29 / 19:52 scans.

This patch keeps PostgreSQL as the only screen data source, but reconstructs one
attendance row per employee/workday from every cached TimeSoft check-in row.
Repeated FaceID scans are clustered and detailed punches win over summary fields.
Locker/Lễ tân are included only when their Web V2 daily work schedule enables
attendance; their shift never comes from TimeSoft and they have no break policy.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import re
import unicodedata
from typing import Any, Callable

from sqlalchemy import text

from vera_attendance_rules import apply_break_restriction, departure_status_is_final
import vera_web_v2_snapshot as snapshot
import vera_web_v2_department_attendance as department_attendance


RELEASE = "4.2.2-locker-letan-work-schedule"
ALLOWED_ROLES = {"nhanvien", "leader", "locker", "letan"}
RAW_TIME_ALIASES = {
    "thoi gian", "thoigian", "time", "timestr", "datetime", "datetimestr",
    "checktime", "checktimestr", "checkindatetime", "checkindatetimestr",
    "checkintime", "checkintimestr", "machinetime", "machinetimestr",
    "createdate", "createdatestr", "createtime", "createtimestr",
}
NAME_ALIASES = (
    "employeeInfo.Name", "EmployeeName", "employeeName", "Name", "FullName",
    "Tên nhân viên", "TenNhanVien", "Employee.Name",
)
CODE_ALIASES = (
    "employeeInfo.EmployeeCode", "EmployeeCode", "EnrollNumber", "Mã chấm công",
    "MaChamCong", "UserCode",
)
WORK_DATE_ALIASES = (
    "WorkDateStr", "WorkDate", "WorkingDateStr", "WorkingDate",
)


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").strip().lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    raw = raw.replace("đ", "d")
    return " ".join(raw.split())


def _first(item: dict[str, Any], names) -> Any:
    for name in names:
        value = item.get(name)
        if value is not None and str(value).strip().lower() not in {"", "nan", "none", "nat"}:
            return value
    by_norm = {_norm(key).replace(" ", ""): value for key, value in item.items()}
    for name in names:
        value = by_norm.get(_norm(name).replace(" ", ""))
        if value is not None and str(value).strip().lower() not in {"", "nan", "none", "nat"}:
            return value
    return ""


def _parse_datetime(value: Any, work_day: date | None = None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidates = [raw]
    if work_day and re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", raw):
        candidates.insert(0, f"{work_day.strftime('%d/%m/%Y')} {raw}")
    formats = (
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
        "%H:%M:%S", "%H:%M",
    )
    for candidate in candidates:
        for fmt in formats:
            try:
                parsed = datetime.strptime(candidate[:26], fmt)
                if parsed.year == 1900 and work_day:
                    parsed = parsed.replace(year=work_day.year, month=work_day.month, day=work_day.day)
                return parsed
            except ValueError:
                continue
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    dt = _parse_datetime(raw)
    return dt.date() if dt else None


def _eligible_aliases(conn) -> tuple[dict[str, str], dict[str, str]]:
    rows = conn.execute(text("""
        SELECT username, COALESCE(full_name,'') AS full_name, lower(COALESCE(role,'')) AS role
        FROM employees
        WHERE lower(COALESCE(role,'')) IN ('nhanvien','leader','locker','letan')
          AND COALESCE(payload->>'__deleted','false') <> 'true'
          AND lower(COALESCE(payload->>'Trạng thái làm việc','đang làm việc')) = 'đang làm việc'
    """)).mappings().all()
    aliases: dict[str, str] = {}
    roles: dict[str, str] = {}
    for row in rows:
        username = str(row.get("username") or "").strip()
        role = str(row.get("role") or "").strip().lower()
        if not username or role not in ALLOWED_ROLES:
            continue
        roles[_norm(username)] = role
        for value in (username, row.get("full_name")):
            key = _norm(value)
            if key:
                aliases[key] = username
    return aliases, roles


def _canonical_employee(item: dict[str, Any], aliases: dict[str, str]) -> str:
    raw = _first(item, NAME_ALIASES)
    return aliases.get(_norm(raw), "")


def _explicit_work_day(item: dict[str, Any]) -> date | None:
    return _parse_date(_first(item, WORK_DATE_ALIASES))


def _sequential_punches(item: dict[str, Any], work_day: date | None) -> list[datetime]:
    values = []
    for prefix in ("MachineTimeCheckIn", "LocalTimeCheckIn"):
        first = item.get(f"{prefix}Str")
        if first:
            values.append(first)
        for index in range(2, 21):
            value = item.get(f"{prefix}{index}Str")
            if value:
                values.append(value)
    for name in ("MachineTimeCheckOutStr", "LocalTimeCheckOutStr"):
        if item.get(name):
            values.append(item.get(name))
    return [dt for value in values if (dt := _parse_datetime(value, work_day)) is not None]


def _generic_raw_punch(item: dict[str, Any], work_day: date | None) -> list[datetime]:
    # Raw `lich-su-checkin` rows normally have exactly one event time.  Use this
    # fallback only when the row does not expose TimeSoft sequential punch fields,
    # preventing CreateDate metadata from polluting aggregate attendance rows.
    for key, value in item.items():
        key_norm = _norm(key).replace("_", " ").replace("-", " ")
        key_compact = key_norm.replace(" ", "")
        if key_norm in RAW_TIME_ALIASES or key_compact in {item.replace(" ", "") for item in RAW_TIME_ALIASES}:
            parsed = _parse_datetime(value, work_day)
            if parsed:
                return [parsed]
    return []


def _row_punches(item: dict[str, Any], work_day: date | None) -> list[datetime]:
    sequential = _sequential_punches(item, work_day)
    return sequential if sequential else _generic_raw_punch(item, work_day)


def _work_day_for_row(item: dict[str, Any], punches: list[datetime]) -> date | None:
    explicit = _explicit_work_day(item)
    if explicit:
        return explicit
    if not punches:
        return None
    first = min(punches)
    # Legacy Auto Check convention: 00:00–01:59 belongs to the previous
    # operational workday (late final checkout after midnight).
    return first.date() - timedelta(days=1) if first.hour < 2 else first.date()


def _cluster_punches(values: list[datetime], minutes: int) -> list[datetime]:
    ordered = sorted(set(values))
    if not ordered:
        return []
    result = [ordered[0]]
    threshold = max(1, int(minutes or 10))
    for current in ordered[1:]:
        if (current - result[-1]).total_seconds() / 60 <= threshold:
            continue
        result.append(current)
    return result


def _clock(value: Any) -> time | None:
    raw = str(value or "").strip()
    match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
    if not match:
        return None
    try:
        return time(int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))
    except ValueError:
        return None


def _expected_end(work_day: date, item: dict[str, Any]) -> datetime | None:
    end_clock = _clock(item.get("EndWorkTime") or item.get("ShiftEndTime"))
    if not end_clock:
        return None
    end_dt = datetime.combine(work_day, end_clock)
    start_clock = _clock(item.get("StartWorkTime") or item.get("ShiftStartTime"))
    if start_clock and end_clock <= start_clock:
        end_dt += timedelta(days=1)
    return end_dt


def _looks_like_final_checkout(value: datetime, work_day: date, item: dict[str, Any], punch_count: int) -> bool:
    # Preserve old-system hard boundary: 23:00 of the workday through 02:59 the
    # next day is final checkout and must never become a break edge.
    if (value.date() == work_day and value.hour >= 23) or (
        value.date() == work_day + timedelta(days=1) and value.hour < 3
    ):
        return True
    return False


def _departure_status_is_final(
    punches: list[datetime],
    *,
    work_day: date,
    representative: dict[str, Any],
    cluster_minutes: int,
    now: datetime | None = None,
) -> bool:
    """Không suy luận Về sớm từ nhãn tổng hợp của TimeSoft.

    Ca làm bình thường của Vera không FaceID khi hết ca.
    Về sớm thật được xác định từ leave_records.
    """
    return False

def _pick_break_pair(values: list[datetime], planned: int, cluster_minutes: int):
    """Choose a 15:00–21:00 break pair after the first (shift check-in) event.

    The first FaceID is always the work check-in, including employees whose
    permitted/unpermitted late arrival is 17:00.  It must never become a break
    edge merely because it falls inside the normal mid-shift-break window.
    """
    if len(values) < 2:
        return None
    if len(values) == 2 and 15 <= values[0].hour <= 21:
        return values[0], values[1], "Cụm 2 → 3"
    minimum = max(int(cluster_minutes or 10) + 1, min(30, max(15, round(max(1, planned) * .25))))
    candidates = []
    for index, (start, end) in enumerate(zip(values, values[1:])):
        if not 15 <= start.hour <= 21:
            continue
        gap = round((end - start).total_seconds() / 60)
        if gap < 0:
            continue
        penalty = 10000 if gap < minimum else 0
        candidates.append((abs(gap - max(1, planned)) + penalty, abs(gap - max(1, planned)), index, start, end))
    if not candidates:
        return None
    _, _, index, start, end = min(candidates)
    return start, end, f"Tự chọn cụm {index + 2} → {index + 3} gần {planned} phút nhất"


def _break_from_punches(
    punches: list[datetime],
    *,
    work_day: date,
    representative: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    clustered = _cluster_punches(punches, int(cfg.get("faceid_cluster_minutes") or 10))
    planned = int(cfg.get("break_planned_minutes") or 0)
    enabled = bool(cfg.get("break_enabled"))
    restricted_reason = str(cfg.get("break_restricted_reason") or "").strip()
    restricted = bool(restricted_reason)
    if not clustered:
        return {
            **cfg,
            "break_actual_minutes": 0,
            "break_count": 0,
            "break_detail": "",
            "break_status": (f"Không được phép nghỉ giữa ca do {restricted_reason}" if restricted else
                             "Chưa ghi nhận FaceID nghỉ" if enabled else "Không áp dụng"),
            "punch_times": [],
            "raw_faceid_count": 0,
        }

    # First clustered event is shift check-in.  Only remove the last event when
    # it is demonstrably final checkout.  Therefore the real Thiên Kim sequence
    # 12:45 / 18:29 / 19:52 becomes the break pair 18:29 → 19:52 (83 minutes).
    middle = list(clustered[1:])
    final_checkout = None
    if middle and _looks_like_final_checkout(middle[-1], work_day, representative, len(clustered)):
        final_checkout = middle.pop()

    chosen = _pick_break_pair(middle, planned, int(cfg.get("faceid_cluster_minutes") or 10))
    break_out, break_in, method = chosen if chosen else (None, None, "Chưa đủ FaceID")
    actual = int(round((break_in - break_out).total_seconds() / 60)) if break_out and break_in else 0
    details = [f"{break_out.strftime('%H:%M')} → {break_in.strftime('%H:%M')}"] if break_out else []
    if not chosen and middle:
        details.append(f"{middle[0].strftime('%H:%M')} → chưa chấm vào lại")

    if restricted and chosen:
        status = f"Vi phạm: {restricted_reason} không được nghỉ giữa ca ({actual} phút)"
    elif restricted:
        status = f"Không được phép nghỉ giữa ca do {restricted_reason}"
    elif not enabled:
        status = "Không áp dụng"
    elif chosen:
        over = actual - planned
        status = f"Quá {over} phút" if planned > 0 and over > 0 else "Trong giới hạn"
    elif middle:
        status = "Chưa đủ cặp chấm công"
    else:
        status = "Chưa ghi nhận FaceID nghỉ"

    return {
        **cfg,
        "break_actual_minutes": actual,
        "break_over_minutes": max(0, actual - planned),
        "break_count": 1 if chosen else 0,
        "break_detail": "; ".join(details),
        "break_out": break_out.strftime("%H:%M:%S") if break_out else "",
        "break_in": break_in.strftime("%H:%M:%S") if break_in else "",
        "break_source": "TimeSoft FaceID" if chosen else "",
        "break_method": method,
        "break_status": status,
        "punch_times": [value.strftime("%H:%M:%S") for value in clustered],
        "raw_faceid_count": len(clustered),
        "faceid_check_in": clustered[0].strftime("%H:%M:%S"),
        "faceid_check_out": final_checkout.strftime("%H:%M:%S") if final_checkout else "",
        "faceid_last": clustered[-1].strftime("%H:%M:%S"),
    }


def _representative_score(item: dict[str, Any]) -> int:
    fields = (
        "WorkDateStr", "WorkTimeName", "StartWorkTime", "EndWorkTime",
        "MachineTimeCheckInStr", "MachineTimeCheckOutStr",
        "GoWorkTypeName", "LastCheckInTypeName",
    )
    return sum(1 for field in fields if str(item.get(field) or "").strip())


def _records_v42(conn, start: date, end: date) -> list[dict[str, Any]]:
    definitions, break_config = snapshot._shift_break_settings(conn)
    aliases, roles = _eligible_aliases(conn)
    datasets = conn.execute(text("""
        SELECT dataset_key, payload
        FROM vera_dataset_cache
        WHERE dataset_key='timesoft_employee_checkin_today'
           OR dataset_key LIKE 'timesoft_employee_checkin_20%'
        ORDER BY CASE WHEN dataset_key='timesoft_employee_checkin_today' THEN 0 ELSE 1 END,
                 dataset_key DESC
    """)).mappings().all()

    grouped: dict[tuple[date, str], dict[str, Any]] = defaultdict(lambda: {"rows": [], "punches": []})
    for dataset in datasets:
        for raw in dataset.get("payload") or []:
            if not isinstance(raw, dict):
                continue
            employee = _canonical_employee(raw, aliases)
            if not employee:
                continue
            explicit_day = _explicit_work_day(raw)
            punches = _row_punches(raw, explicit_day)
            work_day = explicit_day or _work_day_for_row(raw, punches)
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
        representative = max(rows, key=_representative_score)
        cfg = snapshot._shift_config(representative, definitions, break_config)
        arrival_status = _norm(representative.get("GoWorkTypeName"))
        departure_status = _norm(representative.get("LastCheckInTypeName"))
        restricted_reasons = []
        if "di tre" in arrival_status:
            restricted_reasons.append("đi trễ")
        if "ve som" in departure_status and _departure_status_is_final(
            bucket["punches"],
            work_day=work_day,
            representative=representative,
            cluster_minutes=int(cfg.get("faceid_cluster_minutes") or 10),
        ):
            restricted_reasons.append("về sớm")
        cfg = apply_break_restriction(cfg, restricted_reasons)
        faceid = _break_from_punches(
            bucket["punches"],
            work_day=work_day,
            representative=representative,
            cfg=cfg,
        )
        base = snapshot._record(representative, definitions, break_config)
        base.update(faceid)
        base["date"] = work_day.strftime("%d/%m/%Y")
        base["employee_name"] = employee
        base["employee_role"] = roles.get(_norm(employee), "")
        raw_code = _first(representative, CODE_ALIASES)
        if raw_code:
            base["employee_code"] = str(raw_code).strip()
        if not str(base.get("check_in") or "").strip() and faceid.get("faceid_check_in"):
            base["check_in"] = faceid["faceid_check_in"]
        # MachineTimeCheckOutStr is the last FaceID, not always the shift exit.
        base["check_out"] = faceid.get("faceid_check_out") or ""
        base["faceid_last"] = faceid.get("faceid_last") or ""
        base["attendance_source"] = "TimeSoft FaceID chi tiết" if faceid.get("raw_faceid_count", 0) >= 2 else "TimeSoft"
        base = department_attendance.apply_schedule_to_record(
            conn, base, work_day, employee, base["employee_role"],
        )
        if base is None:
            continue
        output.append(base)

    return sorted(output, key=lambda item: (
        datetime.strptime(item["date"], "%d/%m/%Y"),
        _norm(item.get("employee_name")),
    ))


def install_attendance_v42(app, *, engine_instance: Callable[[], Any]) -> None:
    if getattr(app.state, "attendance_v42_installed", False):
        return

    # Operations 4.1 resolves snapshot._records at request time.  Replacing the
    # one data builder here upgrades screen + filters + Excel without duplicating
    # route code.
    snapshot._records = _records_v42

    @app.get("/v2/attendance-v42/health")
    def attendance_v42_health():
        return {
            "ok": True,
            "release": RELEASE,
            "allowed_roles": sorted(ALLOWED_ROLES),
            "legacy_auto_check": True,
            "raw_faceid_clustering": True,
            "cross_midnight_checkout": True,
            "screen_break_column": True,
            "locker_letan_schedule_attendance": True,
            "locker_letan_midshift_break": False,
        }

    app.state.attendance_v42_installed = True
    app.state.attendance_v42_release = RELEASE

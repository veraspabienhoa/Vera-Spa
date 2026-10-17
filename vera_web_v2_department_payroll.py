"""Editable monthly payroll for Quản lý, Locker, Lễ tân, Support and Tạp vụ."""
from __future__ import annotations
from vera_employee_names import canonical_username, load_identity_index

import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from fractions import Fraction
from io import BytesIO
import os
import smtplib
from typing import Any, Callable
import re
import uuid
import vera_web_v2_hr as hr

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel, Field
from sqlalchemy import text

import vera_web_v2_payroll as payroll
import vera_web_v2_snapshot as attendance
import vera_web_v2_work_schedule as work_schedule
import vera_attendance_participation as participation
import vera_department_probation as probation


RELEASE = "department-payroll-employee-source-2026-10-11-v14"
HC_PAYROLL_CONTRACT = 1
SALARY_SOURCES = {"schedule": "Thống kê", "attendance": "Chấm công"}
EMPLOYEE_CONFIG_KEY = "department_employee_salary_configs"
EMPLOYEE_SOURCE_KEY = "department_employee_salary_sources"
TIME_FIELDS = ("work_days", "hours_ca1", "hours_ca2_before_22", "hours_ca2_after_22")
RATE_KEYS = ("rate_ca1", "rate_ca2_before_22", "rate_ca2_after_22", "default_base_salary")
EMAIL_TEMPLATE_RELEASE = "department-payroll-email-eleven-items-2026-10-06.1"
COMBO_COMMISSION = 100_000
PAYROLL_EXCLUDED_SQL = "lower(btrim(COALESCE(payload->>'Không tính lương','false'))) IN ('1','true','yes','y','có','x','ẩn')"
DEPARTMENTS = {
    "quanly": "Quản lý",
    "locker": "Locker",
    "letan": "Lễ tân",
    "support": "Support",
    "tapvu": "Tạp vụ",
}
CALCULATION_MODES = {
    "quanly": "hourly",
    "locker": "hourly",
    "letan": "hourly",
    "support": "hourly",
    "tapvu": "monthly",
}
VN_TZ = timezone(timedelta(hours=7))

DEFAULT_CONFIG = {
    "quanly": {
        "calculation_mode": "hourly",
        "rate_ca1": 0,
        "rate_ca2_before_22": 0,
        "rate_ca2_after_22": 0,
        "standard_day_hours": 8,
        "standard_month_days": 26,
        "full_day_hours": 12,
        "full_day_allowance": 0,
        "default_base_salary": 0,
        "default_attendance_bonus": 0,
        "default_responsibility": 0,
        "default_seniority": 0,
        "default_combo_sales": 0,
    },
    "locker": {
        "calculation_mode": "hourly",
        "rate_ca1": 27000,
        "rate_ca2_before_22": 27000,
        "rate_ca2_after_22": 30000,
        "standard_day_hours": 8,
        "standard_month_days": 26,
        "full_day_hours": 12,
        "full_day_allowance": 30000,
        "default_base_salary": 0,
        "default_attendance_bonus": 0,
        "default_responsibility": 0,
        "default_seniority": 0,
        "default_combo_sales": 0,
    },
    "letan": {
        "calculation_mode": "hourly",
        "rate_ca1": 27000,
        "rate_ca2_before_22": 30000,
        "rate_ca2_after_22": 33000,
        "standard_day_hours": 8,
        "standard_month_days": 26,
        "full_day_hours": 12,
        "full_day_allowance": 30000,
        "default_base_salary": 0,
        "default_attendance_bonus": 500000,
        "default_responsibility": 0,
        "default_seniority": 0,
        "default_combo_sales": 0,
    },
    "support": {
        "calculation_mode": "hourly",
        "rate_ca1": 0,
        "rate_ca2_before_22": 0,
        "rate_ca2_after_22": 0,
        "standard_day_hours": 8,
        "standard_month_days": 26,
        "full_day_hours": 12,
        "full_day_allowance": 0,
        "default_base_salary": 0,
        "default_attendance_bonus": 0,
        "default_responsibility": 0,
        "default_seniority": 0,
        "default_combo_sales": 0,
    },
    "tapvu": {
        "calculation_mode": "monthly",
        "rate_ca1": 0,
        "rate_ca2_before_22": 0,
        "rate_ca2_after_22": 0,
        "standard_day_hours": 8,
        "standard_month_days": 26,
        "full_day_hours": 12,
        "full_day_allowance": 0,
        "default_base_salary": 0,
        "default_attendance_bonus": 0,
        "default_responsibility": 0,
        "default_seniority": 0,
        "default_combo_sales": 0,
    },
}

DEFAULT_EMAIL_TEMPLATE = {
    "subject": "Bảng lương {bo_phan} tháng {thang} - {ten_nhan_vien}",
    "body": (
        "Chào {ten_nhan_vien},\n\n"
        "VERA SPA gửi bảng lương {bo_phan} tháng {thang}.\n\n"
        "{bang_chi_tiet}\n\n"
        "Tổng lương: {tong_luong}\n"
        "Tổng phạt: {tong_phat}\n"
        "Số tiền thực nhận: {thuc_nhan}\n\n"
        "Vui lòng kiểm tra và phản hồi nếu có sai sót.\n\nTrân trọng,\nVERA SPA"
    ),
}

ROW_MONEY_FIELDS = (
    "base_salary", "salary", "full_allowance", "attendance_bonus", "responsibility",
    "seniority", "combo_sales", "total_salary",
    "violation_penalty", "late_penalty", "advance", "net_salary",
)

EXCEL_COLUMNS = (
    ("tt", "TT"), ("employee_name", "Họ tên"), ("department_label", "Bộ phận"),
    ("base_salary", "Lương cơ bản"), ("work_days", "Số ngày đi làm"),
    ("hours_ca1", "Giờ Ca 1"), ("hours_ca2_before_22", "Giờ Ca 2 trước 22h"),
    ("hours_ca2_after_22", "Giờ Ca 2 sau 22h"), ("salary", "Tiền lương"),
    ("full_allowance", "Phụ cấp Full"), ("attendance_bonus", "Tiền chuyên cần"),
    ("responsibility", "Tiền trách nhiệm"), ("seniority", "Phụ cấp thâm niên"),
    ("combo_sales", "Bán combo"), ("total_salary", "Tổng lương"),
    ("advance", "Ứng lương"), ("violation_penalty", "Tiền phạt vi phạm"), ("effective_late_penalty", "Phạt đi trễ trừ thêm"),
    ("net_salary", "Số tiền thực nhận"),
)

EMAIL_SUMMARY_COLUMNS = (
    ("salary", "Tiền Lương"), ("full_allowance", "Phụ cấp Full ca"),
    ("attendance_bonus", "Chuyên cần"), ("responsibility", "Trách nhiệm"),
    ("seniority", "Thâm niên"), ("combo_sales", "Bán combo"),
    ("advance", "Tiền ứng lương"), ("violation_penalty", "Phạt vi phạm"),
    ("effective_late_penalty", "Phạt đi trễ"), ("total_salary", "Tổng lương"),
    ("net_salary", "Thực nhận"),
)


class PenaltyRule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=80)
    name: str = Field(min_length=1, max_length=300)
    amount: float = Field(default=0, ge=0, le=1_000_000_000)
    note: str = Field(default="", max_length=1000)
    enabled: bool = True


class DepartmentSettingsUpdate(BaseModel):
    expected_revision: int | None = Field(default=None, ge=0)
    config: dict[str, Any]
    penalty_rules: list[PenaltyRule] = Field(default_factory=list, max_length=300)
    email_template: dict[str, str]


class DepartmentDraft(BaseModel):
    history_id: str = Field(default="", max_length=100)
    expected_revision: int | None = Field(default=None, ge=0)
    expected_history_revision: int | None = Field(default=None, ge=0)
    department: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=300)


class DepartmentEmail(DepartmentDraft):
    employees: list[str] = Field(default_factory=list, max_length=300)


class CombinedPayrollDraft(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=1200)
    history_id: str = Field(default="", max_length=100)
    expected_revision: int | None = Field(default=None, ge=0)
    expected_history_revision: int | None = Field(default=None, ge=0)


class EmployeeSalaryConfigUpdate(BaseModel):
    salary_sources: list[dict[str, Any]] = Field(default_factory=list, max_length=1200)
    expected_revision: int | None = Field(default=None, ge=0)
    rows: list[dict[str, Any]] | None = Field(default=None, max_length=300)


def _number(value: Any) -> int:
    return max(0, payroll._number(value))


def _month_range(month: str) -> tuple[date, date, str]:
    try:
        year, month_number = (int(part) for part in month.split("-", 1))
        if year < 2020 or year > 2100 or month_number < 1 or month_number > 12:
            raise ValueError
    except Exception as exc:
        raise HTTPException(400, "Tháng lương không hợp lệ.") from exc
    return (
        date(year, month_number, 1),
        date(year, month_number, calendar.monthrange(year, month_number)[1]),
        f"{month_number:02d}/{year}",
    )


def _draft_month_range(month: str, today: date | None = None) -> tuple[date, date, str]:
    """Return the payable draft period, capped at today for the current month."""
    start, month_end, label = _month_range(month)
    current_day = today or datetime.now(VN_TZ).date()
    end = current_day if start <= current_day <= month_end else month_end
    return start, end, label


def _setting_key(department: str, suffix: str) -> str:
    return f"department_{department}_{suffix}"


def _clean_config(department: str, raw: Any, mode: str | None = None) -> dict[str, Any]:
    defaults = DEFAULT_CONFIG.get(department, DEFAULT_CONFIG["support"])
    source = raw if isinstance(raw, dict) else {}
    result = {"calculation_mode": mode or CALCULATION_MODES.get(department, "hourly")}
    for key, value in defaults.items():
        if key == "calculation_mode":
            continue
        result[key] = _number(source.get(key, value))
    result["standard_day_hours"] = max(1, result["standard_day_hours"])
    result["standard_month_days"] = max(1, result["standard_month_days"])
    result["full_day_hours"] = max(1, result["full_day_hours"])
    if result["calculation_mode"] == "monthly":
        result["standard_month_days"] = 26
    return result


def _salary_source(config: Any) -> str:
    """Only absent legacy values default; invalid choices must never bypass evidence."""
    raw = config if isinstance(config, dict) else {}
    source = raw.get("salary_source", "schedule")
    if not isinstance(source, str) or source not in SALARY_SOURCES:
        raise HTTPException(400, "Nguồn lương phải là Thống kê hoặc Chấm công.")
    return source


def _configured_rates(department, raw):
    saved = raw if isinstance(raw, dict) else {}
    defaults = DEFAULT_CONFIG.get(department, DEFAULT_CONFIG["support"])
    return [key for key in RATE_KEYS if (key in saved and saved[key] is not None
            and str(saved[key]).strip() != "") or defaults.get(key, 0) > 0]


def _setting_snapshot(conn, key, default):
    row = conn.execute(text("""SELECT value_json,COALESCE(revision,0) AS revision FROM vera_app_setting
        WHERE category='payroll' AND setting_key=:key"""), {"key": key}).mappings().first()
    return (row["value_json"], int(row["revision"])) if row else (default, 0)


def _employee_numeric_update(department, supplied, previous, department_config):
    """A source-only save must not freeze currently inherited rates/defaults."""
    cleaned = _clean_config(department, supplied, department_config["calculation_mode"])
    if not isinstance(previous, dict):
        return cleaned  # A deliberately added numeric configuration row.
    current = _clean_config(department, {**department_config, **previous}, department_config["calculation_mode"])
    result = dict(previous)
    result.pop("salary_source", None)
    explicitly_set = set(supplied.get("explicit_rate_fields") or [])
    for key, value in cleaned.items():
        if key in supplied and (key in previous or value != current.get(key) or key in explicitly_set):
            result[key] = value
    return result


def _employee_settings_snapshot(conn):
    rows = conn.execute(text("""SELECT setting_key,value_json,COALESCE(revision,0) AS revision
        FROM vera_app_setting WHERE category='payroll' AND setting_key IN (:config,:source)"""),
        {"config": EMPLOYEE_CONFIG_KEY, "source": EMPLOYEE_SOURCE_KEY}).mappings().all()
    by_key = {row["setting_key"]: row for row in rows}
    configs = by_key.get(EMPLOYEE_CONFIG_KEY, {})
    sources = by_key.get(EMPLOYEE_SOURCE_KEY, {})
    return configs.get("value_json") or {}, sources.get("value_json") or {}, int(configs.get("revision") or 0)


def _saved_employee_source(username, sources, configs):
    key = str(username).strip().casefold()
    by_name = {str(name).strip().casefold(): value for name, value in sources.items()} if isinstance(sources, dict) else {}
    legacy = {str(name).strip().casefold(): value for name, value in configs.items()} if isinstance(configs, dict) else {}
    return _salary_source({"salary_source": by_name[key]}) if key in by_name else _salary_source(legacy.get(key))


def _employee_config_revision(conn):
    return _setting_snapshot(conn, EMPLOYEE_CONFIG_KEY, {})[1]


def _draft_key(month):
    return f"department_payroll_combined_draft_{month}"


def _require_setting_revision(conn, key, expected):
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"vera:payroll-setting:{key}"})
    value, revision = _setting_snapshot(conn, key, [])
    if expected is None or expected != revision:
        raise HTTPException(409, "Bảng lương đã thay đổi hoặc thiếu phiên bản. Hãy tải lại trước khi lưu.")
    return value, revision


def _require_draft_revision(conn, month, expected):
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"vera:hc-payroll-draft:{month}"})
    rows, revision = _setting_snapshot(conn, _draft_key(month), [])
    if expected is None or expected != revision:
        raise HTTPException(409, "Bảng nháp đã thay đổi hoặc thiếu phiên bản. Hãy mở lại trước khi lưu/chốt/xóa.")
    return rows, revision


def _settings(conn, department: str, *, include_revision: bool = False) -> dict[str, Any]:
    definition = hr.admin_departments(conn).get(department)
    if not definition:
        raise HTTPException(400, "Bộ phận không thuộc Lương hành chánh: loại trừ Leader, nhanvien, admin; hình thức Tip dùng Lương KTV.")
    if include_revision:
        raw_config, config_revision = _setting_snapshot(conn, _setting_key(department, "config"), {})
    else:
        raw_config = payroll._setting(conn, _setting_key(department, "config"), {})
    config = _clean_config(department, raw_config, definition["salary_mode"])
    config["configured_rate_keys"] = _configured_rates(department, raw_config)
    rules = payroll._setting(conn, _setting_key(department, "penalty_rules"), [])
    template = payroll._setting(conn, _setting_key(department, "email_template"), DEFAULT_EMAIL_TEMPLATE)
    if not isinstance(rules, list):
        rules = []
    if not isinstance(template, dict):
        template = DEFAULT_EMAIL_TEMPLATE
    return {
        "department": department,
        "department_label": definition["name"],
        **({"config_revision": config_revision} if include_revision else {}),
        "config": config,
        "penalty_rules": [dict(item) for item in rules if isinstance(item, dict)],
        "email_template": {
            "subject": str((template or {}).get("subject") or DEFAULT_EMAIL_TEMPLATE["subject"]),
            "body": str((template or {}).get("body") or DEFAULT_EMAIL_TEMPLATE["body"]),
        },
    }


def _salary_employee_catalog(conn, sources=None, configs=None) -> list[dict[str, Any]]:
    if sources is None or configs is None:
        configs, sources, _ = _employee_settings_snapshot(conn)
    definitions = hr.admin_departments(conn)
    employees = conn.execute(text(f"""
        SELECT username,COALESCE(full_name,'') AS full_name,{hr.DEPARTMENT_SQL} AS role
        FROM employees
        WHERE {hr.ADMIN_PAY_SQL}
          AND NOT ({PAYROLL_EXCLUDED_SQL})
          AND COALESCE(payload->>'__deleted','false') <> 'true'
          AND lower(COALESCE(payload->>'Trạng thái làm việc',payload->>'employment_status','đang làm việc')) IN ('đang làm việc','thử việc')
        ORDER BY CASE lower(COALESCE(role,''))
          WHEN 'quanly' THEN 0 WHEN 'letan' THEN 1 WHEN 'locker' THEN 2
          WHEN 'support' THEN 3 ELSE 4 END,
          COALESCE(stt,2147483647),username
    """)).mappings().all()
    return [{
        "employee_username": str(employee.get("username") or "").strip(),
        "salary_source": _saved_employee_source(employee.get("username"), sources, configs),
        "employee_name": str(employee.get("full_name") or employee.get("username") or "").strip(),
        "department": str(employee.get("role") or "").strip().lower(),
        "department_label": definitions[str(employee.get("role") or "").strip().lower()]["name"],
    } for employee in employees]


def _employee_config_rows(conn, stored=None, sources=None) -> list[dict[str, Any]]:
    if stored is None or sources is None:
        stored, sources, _ = _employee_settings_snapshot(conn)
    stored = stored if isinstance(stored, dict) else {}
    catalog = _salary_employee_catalog(conn, sources, stored)
    definitions = hr.admin_departments(conn)
    rows = []
    for employee in catalog:
        username = employee["employee_username"]
        role = employee["department"]
        saved = stored.get(username)
        if not isinstance(saved, dict):
            saved = stored.get(username.casefold())
        if not isinstance(saved, dict):
            continue
        inherited = _settings(conn, role)["config"]
        config = _clean_config(role, {**inherited, **saved}, definitions[role]["salary_mode"])
        config["salary_source"] = employee["salary_source"]
        config["configured_rate_keys"] = sorted(set(inherited.get("configured_rate_keys", [])) | set(_configured_rates(role, saved)))
        rows.append({
            "employee_username": username,
            "employee_name": employee["employee_name"],
            "department": role,
            "department_label": employee["department_label"],
            **config,
        })
    return rows


def _employee_config_map(conn) -> dict[str, dict[str, Any]]:
    stored, sources, _ = _employee_settings_snapshot(conn)
    rows = {str(row["employee_username"]).casefold(): row for row in _employee_config_rows(conn, stored, sources)}
    inherited = {}
    for employee in _salary_employee_catalog(conn, sources, stored):
        key, department = employee["employee_username"].casefold(), employee["department"]
        if key not in rows:
            if department not in inherited:
                inherited[department] = _settings(conn, department)["config"]
            rows[key] = {**inherited[department], "salary_source": employee["salary_source"]}
    return rows


def _salary_config_tables(conn, stored=None, sources=None) -> dict[str, list[dict[str, Any]]]:
    rows = _employee_config_rows(conn, stored, sources)
    return {
        "operations": [row for row in rows if row["calculation_mode"] == "hourly"],
        "tapvu": [row for row in rows if row["calculation_mode"] == "monthly"],
    }


def _parse_clock(value: Any, work_day: date) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", raw):
        try:
            parts = [int(part) for part in raw.split(":")]
            return datetime(work_day.year, work_day.month, work_day.day, *parts)
        except ValueError:
            return None
    for candidate in (raw, f"{work_day.strftime('%d/%m/%Y')} {raw}"):
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.strptime(candidate, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=work_day.year, month=work_day.month, day=work_day.day)
                return parsed
            except ValueError:
                continue
    return None


def _interval_minutes(item: dict[str, Any], work_day: date) -> tuple[int, datetime | None, datetime | None]:
    start = _parse_clock(item.get("check_in"), work_day)
    end = _parse_clock(item.get("check_out"), work_day)
    if start and end:
        if end < start:
            end += timedelta(days=1)
        return max(0, int((end - start).total_seconds() // 60)), start, end
    return max(0, payroll._number(item.get("total_minutes"))), start, end


def _hc_payroll_window(item, work_day, periods):
    """Payroll-only fallback; never overwrite raw FaceGate checkout evidence."""
    _, start, end = _interval_minutes(item, work_day)
    blocking_reasons = set(item.get('attendance_pending_reasons') or []) - {'missing_check_out', 'shift_still_open', 'incomplete_archive'}
    if not start or not periods or item.get('attendance_evidence_issues') or blocking_reasons or item.get('identity_verified') is False:
        return start, end, False
    left = min(p[0] for p in periods)
    right = max(p[1] for p in periods)
    if start < left and left.hour >= 12 and start.hour < 12 and (end is None or end <= left):
        start += timedelta(days=1)
        if end:
            end += timedelta(days=1)
    inferred = end is None
    if inferred:
        if datetime.now(VN_TZ).replace(tzinfo=None) < right:
            return start, None, False
        end = right
    return start, end, inferred


def _attendance_totals(records: list[dict[str, Any]], employee: str, norm: Callable[[Any], str], cfg: dict[str, Any],
                       *, schedule_records=None, definitions=None, department="") -> dict[str, Any]:
    totals = {"minutes_ca1": 0, "minutes_ca2_before_22": 0, "minutes_ca2_after_22": 0,
              "full_days": 0, "incomplete_days": 0, "pending_dates": [], "configuration_issues": []}
    schedules = {item.get("work_date"): item for item in (schedule_records or [])
                 if norm(item.get("employee_username")) == norm(employee) and item.get("shift_code") != "Nghỉ"}
    seen_dates = set()
    for item in records:
        if norm(item.get("employee_name")) != norm(employee):
            continue
        try:
            work_day = datetime.strptime(str(item.get("date") or ""), "%d/%m/%Y").date()
        except ValueError:
            continue
        seen_dates.add(work_day)
        schedule = schedules.get(work_day)
        periods = _planned_intervals(schedule, work_day, department, definitions or {}, norm) if schedule else []
        if schedule and not periods:
            totals["configuration_issues"].append(f"{work_day.isoformat()}:missing_shift_times")
            totals["pending_dates"].append(work_day.isoformat())
            totals["incomplete_days"] += 1
            continue
        minutes, start, end = _interval_minutes(item, work_day)
        inferred = False
        if periods:
            start, end, inferred = _hc_payroll_window(item, work_day, periods)
        expected = work_day in schedules or bool(item.get("attendance_expected"))
        if item.get('attendance_evidence_issues') or (item.get("attendance_pending") and not inferred) or (schedule_records is not None and expected and (not start or not end)):
            totals["pending_dates"].append(work_day.isoformat())
            totals["incomplete_days"] += 1
            continue
        if start and end:
            minutes = (end-start).total_seconds()/60
        if minutes <= 0:
            totals["incomplete_days"] += 1
            if expected:
                totals["pending_dates"].append(work_day.isoformat())
            continue
        if periods:
            edges = sorted({start, end, *(max(start, min(end, value)) for period in periods for value in period[:2])})
            paid_minutes = 0
            for left, right in zip(edges, edges[1:]):
                bucket = next((bucket for a, b, bucket in periods if a <= left and right <= b), None)
                if bucket:
                    paid_minutes += _add_interval(totals, left, right, work_day, bucket)
            if paid_minutes >= cfg["full_day_hours"] * 60:
                totals["full_days"] += 1
            continue
        if minutes >= cfg["full_day_hours"] * 60:
            totals["full_days"] += 1
        shift = norm(item.get("shift"))
        default_bucket = "ca2" if "ca 2" in shift else "ca1"
        if not start or not end:
            totals["minutes_ca2_before_22" if default_bucket == "ca2" else "minutes_ca1"] += minutes
            continue
        if periods:
            # Clock-only 00:xx check-ins belong to the following calendar date
            # when all scheduled work starts in the previous evening.
            if start < min(period[0] for period in periods) and end <= min(period[0] for period in periods):
                start += timedelta(days=1); end += timedelta(days=1)
            default_bucket = periods[0][2]
        edges = sorted({start, end, *(max(start, min(end, value)) for period in periods for value in period[:2])})
        for left, right in zip(edges, edges[1:]):
            bucket = next((bucket for a, b, bucket in periods if a <= left and right <= b), default_bucket)
            # Preserve existing first-to-last paid span (including gaps/breaks).
            # This change fixes the rate allocation, not the paid-time policy.
            _add_interval(totals, left, right, work_day, bucket)
    for work_day in schedules.keys() - seen_dates:
        if isinstance(work_day, date):
            totals["pending_dates"].append(work_day.isoformat())
            totals["incomplete_days"] += 1
    totals["pending_dates"] = sorted(set(totals["pending_dates"]))
    for key in ("minutes_ca1", "minutes_ca2_before_22", "minutes_ca2_after_22"):
        totals[key] = float(totals[key])
    return totals


def _probation_policies(conn, month, *, usernames=None, department=None):
    return probation.policies(conn, month, parse_date=payroll._parse_date,
        records=attendance._records, minutes=_interval_minutes,
        period_end=datetime.now(VN_TZ).date(), usernames=usernames, department=department)


def _recalculate(row: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in row.items() if key not in {"other_income_1", "other_income_2"}}
    for field in ROW_MONEY_FIELDS:
        result[field] = _number(result.get(field))
    exact = {}
    basis = result.get("payroll_time_basis") or {}
    for field in TIME_FIELDS:
        try:
            value = Decimal(str(basis.get(field, result.get(field)) or 0))
            exact[field] = max(Decimal(0), value) if value.is_finite() else Decimal(0)
        except (TypeError, ValueError, InvalidOperation):
            exact[field] = Decimal(0)
        result[field] = float(exact[field].quantize(Decimal(".01"), rounding=ROUND_HALF_UP))
    # Server-created time strings may contain repeating decimal hours. Recover
    # their exact microsecond duration before money multiplication, or consume
    # the explicit duration carried by current snapshots. Never price rounded
    # display hours/days (125s at27000/h is937.5, rounded938).
    def duration(field, multiplier, key):
        value = Decimal(str(basis[key])) if key in basis else exact[field] * multiplier
        return Fraction(str(value.quantize(Decimal(".000001"), rounding=ROUND_HALF_UP)))
    if cfg["calculation_mode"] == "monthly":
        seconds = duration("work_days", cfg["standard_day_hours"] * 3600, "work_day_seconds")
        amount = Fraction(result["base_salary"]) * seconds / (cfg["standard_month_days"] * cfg["standard_day_hours"] * 3600)
    else:
        amount = sum(duration(hours, 3600, hours.replace("hours_", "seconds_")) * cfg[rate] / 3600 for hours, rate in (
            ("hours_ca1", "rate_ca1"), ("hours_ca2_before_22", "rate_ca2_before_22"),
            ("hours_ca2_after_22", "rate_ca2_after_22"))) * (Fraction(3, 4) if result.get("probation_rate") == .75 else 1)
    rounded = (2 * amount.numerator + amount.denominator) // (2 * amount.denominator)
    result["salary"] = max(0, rounded - int(result.get("late_wage_rounding_adjustment") or 0))
    result["total_salary"] = sum(result[field] for field in (
        "salary", "full_allowance", "attendance_bonus", "responsibility", "seniority",
        "combo_sales",
    ))
    original_hc = _number(result.get("hc_late_original_penalty"))
    additional_hc = _number(result.get("hc_late_additional_penalty"))
    result["late_penalty_credit"] = min(result["late_penalty"], max(0, original_hc - additional_hc))
    result["late_penalty_surcharge"] = max(0, additional_hc - original_hc)
    result["effective_late_penalty"] = max(0, result["late_penalty"] - original_hc) + additional_hc
    result["net_salary"] = result["total_salary"] - sum(
        result[field] for field in ("violation_penalty", "effective_late_penalty", "advance")
    )
    issues = list(result.get("configuration_issues") or [])
    if "configured_rate_keys" in cfg:
        configured = set(cfg["configured_rate_keys"])
        needed = ["default_base_salary"] if cfg["calculation_mode"] == "monthly" and result["work_days"] else [
            rate for hours, rate in (("hours_ca1", "rate_ca1"), ("hours_ca2_before_22", "rate_ca2_before_22"),
                                     ("hours_ca2_after_22", "rate_ca2_after_22")) if result[hours] > 0]
        issues.extend(f"missing_rate:{key}" for key in needed if key not in configured)
    result["configuration_issues"] = sorted(set(issues))
    result["configuration_pending"] = bool(issues)
    if result.get('attendance_pending') or result["configuration_pending"]:
        result.update(salary=None, total_salary=None, net_salary=None)
    return result


def _employees(conn, department: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text(f"""
        SELECT username,COALESCE(full_name,'') AS full_name,COALESCE(email,'') AS email
        FROM employees
        WHERE {hr.DEPARTMENT_SQL}=:department
          AND {hr.PAYROLL_ACCOUNT_SQL}
          AND NOT ({PAYROLL_EXCLUDED_SQL})
          AND COALESCE(payload->>'__deleted','false') <> 'true'
          AND lower(COALESCE(payload->>'Trạng thái làm việc',payload->>'employment_status','đang làm việc')) IN ('đang làm việc','thử việc')
        ORDER BY COALESCE(stt,2147483647),username
    """), {"department": department}).mappings().all()]


def _penalty_maps(conn, start: date, end: date, norm: Callable[[Any], str]) -> tuple[dict[str, int], dict[str, int]]:
    rows = conn.execute(text("""
        SELECT employee_name,leave_reason,COALESCE(penalty,0) AS penalty
        FROM leave_records WHERE leave_date BETWEEN :start AND :end AND COALESCE(penalty,0)>0
    """), {"start": start, "end": end}).mappings().all()
    late: dict[str, int] = {}
    other: dict[str, int] = {}
    for item in rows:
        key = norm(item.get("employee_name"))
        reason = norm(item.get("leave_reason"))
        target = late if ("di tre" in reason or "ra ngoai vao muon" in reason or "vao lai tre" in reason) else other
        target[key] = target.get(key, 0) + _number(item.get("penalty"))
    return other, late


def _hc_late_events(conn, start, end, norm):
    """Read only canonical linked HC events; unrelated/manual fines get no offset."""
    if not conn.execute(text("SELECT to_regclass('vera_hc_penalty_event')")).scalar():
        return {}
    from vera_hc_late_approval import metadata, payload_dict, price_basis
    records = conn.execute(text("""SELECT l.*, e.id AS hc_event_id, e.work_date AS hc_event_date,
        e.employee_name AS hc_event_employee, e.amount AS hc_event_amount, e.basis AS hc_event_basis
        FROM leave_records l JOIN vera_hc_penalty_event e ON e.leave_record_uid=l.record_uid
        WHERE l.leave_date BETWEEN :start AND :end AND l.source_sheet_id='postgres:hc_rules'
          AND e.kind='late' AND (COALESCE(l.penalty,0)>0 OR l.payload->'hc_late_approval'->>'approved'='true')
          AND COALESCE(l.payload->>'__schedule_violation_deleted','false') <> 'true' ORDER BY l.leave_date,e.id"""), {"start": start, "end": end}).mappings().all()
    result = {}
    for raw in records:
        row = dict(raw)
        basis = payload_dict(row.get("hc_event_basis"))
        rule = basis.get("rule") or {"mode": "multiplier", "value": 2}
        if rule.get("mode") != "multiplier" or str(rule.get("value")) not in {"2", "2.0"}:
            continue  # Existing fixed/custom rules remain a separate policy.
        info = metadata(row)
        event = {"event_id": str(row["hc_event_id"]), "day": row["leave_date"].isoformat(),
                 "basis": basis, "amount": _number(row["penalty"]), "approved": info.get("hc_late_approved", False)}
        approval = payload_dict(row.get("payload")).get("hc_late_approval")
        try:
            prices = price_basis(basis, row["leave_date"])
            if (row["leave_date"] != row["hc_event_date"]
                    or norm(row["employee_name"]) != norm(row["hc_event_employee"])
                    or basis != payload_dict(row.get("payload")).get("hc_basis")
                    or (approval and str(approval.get("event_id")) != str(row["hc_event_id"]))
                    or _number(row["hc_event_amount"]) != prices[False]):
                raise ValueError("mismatched_late_event")
            if not info.get("hc_late_approval_eligible"):
                if _number(row["penalty"]) != prices[event["approved"]]:
                    continue  # Preserve explicitly customized financial amount.
                raise ValueError("invalid_late_approval")
        except (KeyError, TypeError, ValueError, ArithmeticError):
            event["issue"] = f"unverified_late_event:{event['event_id']}"
        result.setdefault(norm(row["employee_name"]), []).append(event)
    return result


def _late_event_key(events):
    # Include the original evidence and current approved amount. No client copy
    # of this field is authority for granting a credit or choosing a source.
    return [{"event_id": e["event_id"], "day": e["day"], "amount": e["amount"],
             "approved": e["approved"], "basis": e["basis"], "issue": e.get("issue")} for e in sorted(events, key=lambda item: (item["day"], str(item["event_id"])))]


def _schedule_late_wage_events(row, events, records, schedules, definitions, norm):
    """Calculation-only wage exclusions; never create or alter penalty records."""
    covered = {event['day'] for event in events}
    planned = {item['work_date']: item for item in schedules}
    output = []
    for actual in records:
        if norm(actual.get('employee_name')) != norm(row.get('employee_username')):
            continue
        try:
            day = datetime.strptime(str(actual.get('date') or ''), '%d/%m/%Y').date()
        except ValueError:
            continue
        if day.isoformat() in covered or day not in planned:
            continue
        periods = _planned_intervals(planned[day], day, row['department'], definitions, norm)
        _, arrival, departure = _interval_minutes(actual, day)
        if not periods or not arrival:
            continue  # Schedule pay does not require a scan or a checkout.
        start = min(p[0] for p in periods)
        if arrival < start and start.hour >= 12 and arrival.hour < 12 and (departure is None or departure <= start):
            arrival += timedelta(days=1)
        if arrival <= start:
            continue
        # Union scheduled intervals so overlapping overtime cannot be deducted twice.
        edges = sorted({t for a, b, _ in periods for t in (a, b)} | {arrival})
        segments = []
        for a, b in zip(edges, edges[1:]):
            if b <= arrival and any(left <= a and b <= right for left, right, _ in periods):
                segments.append({'start': a.replace(tzinfo=VN_TZ).isoformat(),
                                 'end': b.replace(tzinfo=VN_TZ).isoformat()})
        if not segments:
            continue
        event_id = 'schedule-arrival-' + day.isoformat()
        event = {'event_id': event_id, 'day': day.isoformat(), 'amount': 0,
                 'approved': True, 'wage_only': True,
                 'basis': {'start': start.replace(tzinfo=VN_TZ).isoformat(),
                           'end': arrival.replace(tzinfo=VN_TZ).isoformat(),
                           'wage_segments': segments}}
        pending_reasons = actual.get('attendance_pending_reasons')
        # Historical payroll needs complete archived evidence, not the live
        # five-minute freshness requirement used for issuing a new fine.
        if (actual.get('identity_verified') is not True
                or not isinstance(pending_reasons, list)
                or set(pending_reasons) - {'missing_check_out', 'shift_still_open'}
                or actual.get('attendance_evidence_issues')):
            event['issue'] = f'unverified_late_event:{event_id}'
        output.append(event)
        covered.add(day.isoformat())
    return output


def _late_payroll_adjustment(row, cfg, source, events, records, schedules, definitions, norm):
    """Lateness stays unpaid; offset only that same verified event's wage loss."""
    result = dict(row)
    if source == 'schedule':
        events = [*events, *_schedule_late_wage_events(row, events, records, schedules, definitions, norm)]
    result["unadjusted_time"] = {key: row.get(key, 0) for key in TIME_FIELDS}
    result["unadjusted_time_basis"] = dict(row.get("payroll_time_basis") or {key: str(row.get(key) or 0) for key in TIME_FIELDS})
    result.update(late_penalty_credit=0, late_penalty_surcharge=0, hc_late_original_penalty=0,
                  hc_late_additional_penalty=0, unpaid_late_wage=0, unpaid_late_minutes=0,
                  late_wage_rounding_adjustment=0, late_penalty_adjustments=[])
    record_map = {}
    for item in records:
        try:
            record_map[datetime.strptime(str(item.get("date") or ""), "%d/%m/%Y").date()] = item
        except ValueError:
            continue
    schedule_map = {item.get("work_date"): item for item in schedules}
    attendance_counterfactual = dict(result)
    for event in sorted(events, key=lambda item: (item["day"], str(item["event_id"]))):
        if event.get("issue"):
            result["configuration_issues"] = list(result.get("configuration_issues") or []) + [event["issue"]]
            continue
        day = date.fromisoformat(event["day"])
        schedule = schedule_map.get(day)
        if not schedule:
            result["configuration_issues"] = list(result.get("configuration_issues") or []) + [f"late_event_schedule_changed:{event['event_id']}"]
            continue
        periods = _planned_intervals(schedule, day, row["department"], definitions, norm)
        if not periods:
            result["configuration_issues"] = list(result.get("configuration_issues") or []) + [f"late_event_schedule_changed:{event['event_id']}"]
            continue
        actual = record_map.get(day)
        if not actual:
            result["configuration_issues"] = list(result.get("configuration_issues") or []) + [f"late_event_evidence_changed:{event['event_id']}"]
            continue
        _, arrival, departure = _interval_minutes(actual, day)
        if arrival and arrival < min(p[0] for p in periods) and (departure is None or departure <= min(p[0] for p in periods)):
            arrival += timedelta(days=1)
        original_start = datetime.fromisoformat(event["basis"]["start"]).astimezone(VN_TZ).replace(tzinfo=None)
        original_end = datetime.fromisoformat(event["basis"]["end"]).astimezone(VN_TZ).replace(tzinfo=None)
        if (arrival != original_end or min(period[0] for period in periods) != original_start
                or actual.get("attendance_evidence_issues")):
            result["configuration_issues"] = list(result.get("configuration_issues") or []) + [f"late_event_evidence_changed:{event['event_id']}"]
            continue
        if source == "attendance":
            _, departure, inferred = _hc_payroll_window(actual, day, periods)
            if not departure or (actual.get("attendance_pending") and not inferred):
                continue
        missed = {key: Decimal(0) for key in ("minutes_ca1", "minutes_ca2_before_22", "minutes_ca2_after_22")}
        segments = []
        expected_seconds = Decimal(0)
        covered_seconds = Decimal(0)
        actual_wage = Fraction(0)
        entitlement = {**cfg, "default_base_salary": result.get("base_salary", cfg.get("default_base_salary", 0))}
        for segment in event["basis"]["wage_segments"]:
            a, b = [datetime.fromisoformat(segment[key]).astimezone(VN_TZ).replace(tzinfo=None)
                    for key in ("start", "end")]
            expected_seconds += Decimal(str((b-a).total_seconds()))
            if arrival is not None:
                b = min(b, arrival)
            edges = sorted({a, max(a, b), *(max(a, min(b, t)) for period in periods for t in period[:2])})
            for left, right in zip(edges, edges[1:]):
                bucket = next((bucket for x, y, bucket in periods if x <= left and right <= y), None)
                if bucket and right > left:
                    _add_interval(missed, left, right, day, bucket)
                    covered_seconds += Decimal(str((right-left).total_seconds()))
                    if cfg["calculation_mode"] == "monthly":
                        interval_wage = Fraction(str(entitlement["default_base_salary"])) * Fraction(str((right-left).total_seconds())) / (cfg["standard_month_days"] * cfg["standard_day_hours"] * 3600)
                    else:
                        seconds = Fraction(str((right-left).total_seconds()))
                        if bucket == "ca1":
                            interval_wage = seconds * cfg["rate_ca1"] / 3600
                        else:
                            cutoff = datetime.combine(day, datetime.strptime("22:00", "%H:%M").time())
                            before = max(Fraction(0), min(seconds, Fraction(str((min(right, cutoff)-left).total_seconds()))))
                            interval_wage = (before * cfg["rate_ca2_before_22"] + (seconds-before) * cfg["rate_ca2_after_22"]) / 3600
                        interval_wage *= Fraction(3, 4) if result.get("probation_rate") == .75 else 1
                    actual_wage += interval_wage
                    segments.append({"start": left.isoformat(), "end": right.isoformat(), "bucket": bucket})
        minutes = sum(missed.values())
        if covered_seconds != expected_seconds:
            result["configuration_issues"] = list(result.get("configuration_issues") or []) + [f"late_event_evidence_changed:{event['event_id']}"]
            continue
        if not minutes:
            continue
        prior_time = result if source == "schedule" else attendance_counterfactual
        prior = _recalculate(prior_time, cfg)
        changed = dict(prior_time)
        direction = -1 if source == "schedule" else 1
        precise = prior_time.get("payroll_time_basis") or {key: str(prior_time.get(key) or 0) for key in TIME_FIELDS}
        changed["payroll_time_basis"] = dict(precise)
        for field in ("ca1", "ca2_before_22", "ca2_after_22"):
            changed["payroll_time_basis"][f"hours_{field}"] = str(max(Decimal(0), Decimal(precise[f"hours_{field}"])
                + direction * missed[f"minutes_{field}"] / 60))
        changed["payroll_time_basis"]["work_days"] = str(max(Decimal(0), Decimal(precise["work_days"])
            + direction * minutes / 60 / cfg["standard_day_hours"]))
        for field in ("ca1", "ca2_before_22", "ca2_after_22"):
            before_seconds = Decimal(precise.get(f"seconds_{field}", str(Decimal(precise[f"hours_{field}"]) * 3600)))
            changed["payroll_time_basis"][f"seconds_{field}"] = str(max(Decimal(0), before_seconds + direction * missed[f"minutes_{field}"] * 60).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP))
        before_day_seconds = Decimal(precise.get("work_day_seconds", str(Decimal(precise["work_days"]) * cfg["standard_day_hours"] * 3600)))
        changed["payroll_time_basis"]["work_day_seconds"] = str(max(Decimal(0), before_day_seconds + direction * covered_seconds).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP))
        recalculated = _recalculate(changed, cfg)
        raw_loss = max(0, direction * ((recalculated.get("salary") or 0) - (prior.get("salary") or 0)))
        unpaid = (2 * actual_wage.numerator + actual_wage.denominator) // (2 * actual_wage.denominator)
        if ((source == "schedule" and cfg["calculation_mode"] == "monthly"
             and actual_wage > Decimal(str(result["base_salary"])) / cfg["standard_month_days"])
                or abs(unpaid - raw_loss) > 1):
            result["configuration_issues"] = list(result.get("configuration_issues") or []) + [f"late_payable_basis_mismatch:{event['event_id']}"]
            continue
        if source == "schedule":
            result = recalculated
        else:
            attendance_counterfactual = changed
        # Round the unpaid component once, separately from the payable salary.
        # This avoids a positive1đ extra fine on excused fractional-second lateness.
        correction = unpaid - raw_loss
        result["late_wage_rounding_adjustment"] += correction
        result["hc_late_original_penalty"] += event["amount"]
        additional = 0 if event["approved"] else unpaid
        result["hc_late_additional_penalty"] += additional
        result["unpaid_late_wage"] += unpaid
        result["unpaid_late_minutes"] += float(minutes)
        result["late_penalty_adjustments"].append({"event_id": event["event_id"], "date": event["day"],
            "approved": event["approved"], "original_penalty": event["amount"],
            "unpaid_wage": unpaid, "additional_penalty": additional, "rounding_adjustment": correction,
            "credit": max(0, event["amount"] - additional), "segments": segments,
            "wage_basis": {key: entitlement.get(key) for key in ("calculation_mode", *RATE_KEYS, "standard_month_days", "standard_day_hours")},
            "probation_rate": result.get("probation_rate", 1),
            "unpaid_hours": str(minutes / 60), "unpaid_seconds": str(covered_seconds),
            "paid_work_day_seconds": (changed if source == "schedule" else prior).get("payroll_time_basis", {}).get("work_day_seconds"),
            "including_late_work_day_seconds": (prior if source == "schedule" else changed).get("payroll_time_basis", {}).get("work_day_seconds"),
            "paid_work_days": (changed if source == "schedule" else prior).get("payroll_time_basis", {}).get("work_days", str(prior["work_days"])),
            "including_late_work_days": (prior if source == "schedule" else changed).get("payroll_time_basis", {}).get("work_days", str(changed["work_days"]))})
    return _recalculate(result, cfg)


def _combo_sale_counts(conn, start: date, end: date) -> dict[str, int]:
    # The employee-specific combo ledger is authoritative. Do not add the old
    # schedule checkbox or a default allowance, which can count the same sale twice.
    if not conn.execute(text("SELECT to_regclass('vera_work_schedule_combo_sale')")).scalar():
        return {}
    rows = conn.execute(text("""
        SELECT lower(btrim(employee_username)) AS employee, COUNT(*) AS count
        FROM vera_work_schedule_combo_sale
        WHERE department IN ('quanly','letan') AND sale_date BETWEEN :start AND :end
        GROUP BY lower(btrim(employee_username))
    """), {"start": start, "end": end}).mappings().all()
    identities = load_identity_index(conn)
    totals = {}
    for row in rows:
        employee = canonical_username(identities, row["employee"]).casefold()
        totals[employee] = totals.get(employee, 0) + int(row["count"])
    return totals


def _visible_payroll_rows(conn, rows, *, month=None):
    """Filter a saved view without rewriting completed payroll or source money."""
    if not isinstance(rows, list) or not rows:
        return []
    excluded = {str(row["username"]).strip().casefold() for row in conn.execute(
        text(f"SELECT username FROM employees WHERE {PAYROLL_EXCLUDED_SQL}")
    ).mappings().all()}
    visible = [dict(row) for row in rows if isinstance(row, dict)
               and str(row.get("employee_username") or "").strip().casefold() not in excluded]
    if month:
        start, end, _ = _draft_month_range(month)
        visible = participation.eligible(visible, start, end, key='employee_username', administrative_payroll=True)
    return [dict(row, tt=index) for index, row in enumerate(visible, 1)]


def _group_payroll_records(records, field, norm):
    grouped = {}
    for row in records:
        grouped.setdefault(norm(row.get(field)), []).append(row)
    return grouped


def _calculation_inputs(conn, start, end, norm, source, context):
    # This context belongs to one calculation on one caller-owned transaction.
    # Do not cache across requests, periods, users or payroll writes.
    if "employee_configs" not in context:
        context["employee_configs"] = _employee_config_map(conn)
    if "penalties" not in context:
        context["penalties"] = _penalty_maps(conn, start, end, norm)
    if "late_events" not in context:
        context["late_events"] = _hc_late_events(conn, start, end, norm)
    sources = context.setdefault("records_by_source", {})
    if source not in sources:
        if source == "schedule":
            work_schedule._ensure_schema(conn)
            records = [dict(item) for item in conn.execute(text("""
                SELECT work_date,employee_username,department AS schedule_department,shift_code,overtime_shift,start_time,end_time,
                       overtime_start_time,overtime_end_time
                FROM vera_work_schedule WHERE work_date BETWEEN :start AND :end
                ORDER BY work_date,employee_username
            """), {"start": start, "end": end}).mappings().all()]
            definitions = {}
            for item in conn.execute(text("""
                SELECT department,shift_code,start_time,end_time FROM vera_work_shift_definition
                WHERE department IS NOT NULL
            """)).mappings().all():
                definitions.setdefault(str(item["department"]), {})[str(item["shift_code"])] = {
                    "start": str(item.get("start_time") or "")[:5],
                    "end": str(item.get("end_time") or "")[:5],
                }
            context["definitions"] = definitions
            field = "employee_username"
        else:
            records = attendance._records(conn, start, end)
            field = "employee_name"
        # Group with exactly the same identity normalization as the old scan.
        # Historical schedule departments remain on each row after reassignment.
        sources[source] = _group_payroll_records(records, field, norm)
    context["records"] = sources[source]
    return context


def _payroll_time_basis(totals, cfg, source):
    hours = {f"hours_{key}": Decimal(str(totals[f"minutes_{key}"])) / 60
             for key in ("ca1", "ca2_before_22", "ca2_after_22")}
    days = Decimal(str(totals["work_days"])) if source == "schedule" else sum(hours.values()) / cfg["standard_day_hours"]
    return {**{key: str(value) for key, value in hours.items()}, "work_days": str(days),
            **{key.replace("hours_", "seconds_"): str((value * 3600).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP)) for key, value in hours.items()},
            "work_day_seconds": str((days * cfg["standard_day_hours"] * 3600).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP))}


def _calculation(conn, department: str, month: str, norm: Callable[[Any], str], *, combo_counts=None, probation_policies=None, context=None, employees=None) -> dict[str, Any]:
    start, end, label = _draft_month_range(month)
    if probation_policies is None:
        probation_policies = _probation_policies(conn, month, department=department)
    if combo_counts is None:
        combo_counts = _combo_sale_counts(conn, start, end)
    settings = _settings(conn, department)
    cfg = settings["config"]
    context = _calculation_inputs(conn, start, end, norm, "schedule", {} if context is None else context)
    context = _calculation_inputs(conn, start, end, norm, "attendance", context)
    employee_configs = context["employee_configs"]
    employees = participation.eligible(_employees(conn, department) if employees is None else employees, start, end, key='username', administrative_payroll=True)
    violation_map, late_map = context["penalties"]
    rows = []
    for index, employee in enumerate(employees, start=1):
        username = str(employee.get("username") or "").strip()
        employee_cfg = employee_configs.get(username.casefold(), cfg)
        totals = _attendance_totals(context["records"].get(norm(username), []), username, norm, employee_cfg,
            schedule_records=context["records_by_source"]["schedule"].get(norm(username), []),
            definitions=context["definitions"], department=department)
        hours_ca1 = float(round(totals["minutes_ca1"] / 60, 2))
        hours_before = float(round(totals["minutes_ca2_before_22"] / 60, 2))
        hours_after = float(round(totals["minutes_ca2_after_22"] / 60, 2))
        total_hours = hours_ca1 + hours_before + hours_after
        row = {
            "tt": index, "employee_username": username,
            "employee_name": str(employee.get("full_name") or username),
            "email": str(employee.get("email") or ""), "department": department,
            "department_label": settings["department_label"], "base_salary": employee_cfg["default_base_salary"],
            "hours_ca1": hours_ca1, "hours_ca2_before_22": hours_before,
            "hours_ca2_after_22": hours_after,
            "work_days": round(total_hours / employee_cfg["standard_day_hours"], 2),
            "full_days": totals["full_days"],
            "full_allowance": totals["full_days"] * employee_cfg["full_day_allowance"],
            "attendance_bonus": employee_cfg["default_attendance_bonus"],
            "responsibility": employee_cfg["default_responsibility"], "seniority": employee_cfg["default_seniority"],
            "combo_count": combo_counts.get(username.casefold(), 0),
            "combo_sales": combo_counts.get(username.casefold(), 0) * COMBO_COMMISSION,
            "violation_penalty": violation_map.get(norm(username), 0),
            "late_penalty": late_map.get(norm(username), 0), "advance": 0,
            "incomplete_days": totals["incomplete_days"],
            "attendance_pending": bool(totals['pending_dates']),
            "pending_dates": totals['pending_dates'],
            "configuration_issues": totals["configuration_issues"],
            "payroll_time_basis": _payroll_time_basis(totals, employee_cfg, "attendance"),
            "calculation_source": "attendance", "calculation_config": employee_cfg,
        }
        row = probation.apply(row, probation_policies.get(username.casefold()))
        row = _late_payroll_adjustment(row, employee_cfg, row["calculation_source"],
            context["late_events"].get(norm(username), []),
            context["records_by_source"].get("attendance", {}).get(norm(username), []),
            context["records_by_source"]["schedule"].get(norm(username), []), context["definitions"], norm)
        rows.append(row)
    return {**settings, "month": month, "month_label": label, "start": start.isoformat(), "end": end.isoformat(), "rows": rows}


def _minutes_between(start_time: Any, end_time: Any, work_day: date) -> tuple[int, datetime | None, datetime | None]:
    start = _parse_clock(start_time, work_day)
    end = _parse_clock(end_time, work_day)
    if not start or not end or start == end:
        return 0, start, end
    if end < start:
        end += timedelta(days=1)
    return max(0, int((end - start).total_seconds() // 60)), start, end


def _add_interval(totals, start, end, work_day, bucket):
    minutes = max(Decimal(0), Decimal(str((end - start).total_seconds())) / 60)
    if bucket == "ca1":
        totals["minutes_ca1"] += minutes
    else:
        cutoff = datetime.combine(work_day, datetime.strptime("22:00", "%H:%M").time())
        before = min(minutes, max(Decimal(0), Decimal(str((min(end, cutoff) - start).total_seconds())) / 60))
        totals["minutes_ca2_before_22"] += before
        totals["minutes_ca2_after_22"] += minutes - before
    return minutes


def _add_planned_interval(totals, start_time, end_time, work_day, bucket=""):
    minutes, start, end = _minutes_between(start_time, end_time, work_day)
    if not minutes:
        return 0
    return _add_interval(totals, start, end, work_day, bucket or ("ca1" if start.hour < 12 else "ca2"))


def _planned_intervals(item, work_day, department, definitions, norm):
    from vera_schedule_attendance_window import scheduled_periods
    dep = item.get("schedule_department") or department
    shift = str(item.get("shift_code") or "")
    spec = (definitions.get(dep) or {}).get(shift) or {}
    overtime = str(item.get("overtime_shift") or "")
    ot = (definitions.get(dep) or {}).get(overtime.replace("TC ", "", 1)) or {} if overtime in {"TC Ca 1", "TC Ca 2"} else {}
    return scheduled_periods({**item,
        "start_time": item.get("start_time") or spec.get("start"),
        "end_time": item.get("end_time") or spec.get("end"),
        "overtime_start_time": item.get("overtime_start_time") or ot.get("start"),
        "overtime_end_time": item.get("overtime_end_time") or ot.get("end")}, work_day)


def _schedule_totals(records, employee, department, definitions, cfg, norm):
    totals = {"minutes_ca1": 0, "minutes_ca2_before_22": 0, "minutes_ca2_after_22": 0,
              "work_days": 0, "full_days": 0, "configuration_issues": []}
    for item in records:
        if norm(item.get("employee_username")) != norm(employee) or item.get("shift_code") == "Nghỉ":
            continue
        work_day = item.get("work_date")
        if isinstance(work_day, datetime):
            work_day = work_day.date()
        if not isinstance(work_day, date):
            continue
        periods = _planned_intervals(item, work_day, department, definitions, norm)
        if not periods:
            totals["configuration_issues"].append(f"{work_day.isoformat()}:missing_shift_times")
            continue
        if item.get("overtime_shift") and len(periods) < 2:
            totals["configuration_issues"].append(f"{work_day.isoformat()}:missing_overtime_times")
        totals["work_days"] += 1
        edges = sorted({t for a, b, _ in periods for t in (a, b)})
        paid_minutes = 0
        for a, b in zip(edges, edges[1:]):
            bucket = next((bucket for left, right, bucket in periods if left <= a and b <= right), None)
            if bucket:
                paid_minutes += _add_interval(totals, a, b, work_day, bucket)
        if paid_minutes >= cfg["full_day_hours"] * 60:
            totals["full_days"] += 1
    return totals


def _schedule_calculation(conn, department: str, month: str, norm: Callable[[Any], str], *, combo_counts=None, probation_policies=None, context=None, employees=None) -> dict[str, Any]:
    start, end, label = _draft_month_range(month)
    if probation_policies is None:
        probation_policies = _probation_policies(conn, month, department=department)
    if combo_counts is None:
        combo_counts = _combo_sale_counts(conn, start, end)
    settings = _settings(conn, department)
    cfg = settings["config"]
    context = _calculation_inputs(conn, start, end, norm, "schedule", {} if context is None else context)
    employee_configs = context["employee_configs"]
    employees = participation.eligible(_employees(conn, department) if employees is None else employees, start, end, key='username', administrative_payroll=True)
    if employees:
        # Verified late arrivals reduce scheduled wages even without a fine.
        # Reuse the request's caller-owned connection and source cache.
        _calculation_inputs(conn, start, end, norm, "attendance", context)
        _calculation_inputs(conn, start, end, norm, "schedule", context)
    definitions = context["definitions"]
    violation_map, late_map = context["penalties"]
    rows = []
    for index, employee in enumerate(employees, start=1):
        username = str(employee.get("username") or "").strip()
        employee_cfg = employee_configs.get(username.casefold(), cfg)
        totals = _schedule_totals(context["records"].get(norm(username), []), username, department, definitions, employee_cfg, norm)
        row = {
            "tt": index, "employee_username": username,
            "employee_name": str(employee.get("full_name") or username),
            "email": str(employee.get("email") or ""), "department": department,
            "department_label": settings["department_label"],
            "base_salary": employee_cfg["default_base_salary"],
            "hours_ca1": float(round(totals["minutes_ca1"] / 60, 2)),
            "hours_ca2_before_22": float(round(totals["minutes_ca2_before_22"] / 60, 2)),
            "hours_ca2_after_22": float(round(totals["minutes_ca2_after_22"] / 60, 2)),
            "work_days": totals["work_days"], "full_days": totals["full_days"],
            "full_allowance": totals["full_days"] * employee_cfg["full_day_allowance"],
            "attendance_bonus": employee_cfg["default_attendance_bonus"],
            "responsibility": employee_cfg["default_responsibility"],
            "seniority": employee_cfg["default_seniority"],
            "combo_count": combo_counts.get(username.casefold(), 0),
            "combo_sales": combo_counts.get(username.casefold(), 0) * COMBO_COMMISSION,
            "violation_penalty": violation_map.get(norm(username), 0),
            "late_penalty": late_map.get(norm(username), 0), "advance": 0,
            "incomplete_days": 0, "calculation_source": "schedule",
            "configuration_issues": totals["configuration_issues"],
            "payroll_time_basis": _payroll_time_basis(totals, employee_cfg, "schedule"),
            "calculation_config": employee_cfg,
        }
        row = probation.apply(row, probation_policies.get(username.casefold()))
        row = _late_payroll_adjustment(row, employee_cfg, row["calculation_source"],
            context["late_events"].get(norm(username), []),
            context["records_by_source"].get("attendance", {}).get(norm(username), []),
            context["records_by_source"]["schedule"].get(norm(username), []), context["definitions"], norm)
        rows.append(row)
    return {**settings, "month": month, "month_label": label, "start": start.isoformat(), "end": end.isoformat(), "rows": rows}


def _calculation_snapshot(row, month, source, cfg, *, start=None, end=None):
    period_start, period_end, _ = _draft_month_range(month)
    return {"version": 1, "month": month, "employee_username": str(row["employee_username"]).strip().casefold(),
            "source": source, "config": dict(cfg),
            "paid_time": {key: row.get(key, 0) for key in TIME_FIELDS},
            "unadjusted_time": row.get("unadjusted_time", {key: row.get(key, 0) for key in TIME_FIELDS}),
            "time_basis": row.get("payroll_time_basis", {}),
            "unadjusted_time_basis": row.get("unadjusted_time_basis", {}),
            "start": start or period_start.isoformat(),
            "end": end or period_end.isoformat()}


def _source_label(rows):
    sources = {row.get("calculation_source") for row in rows}
    return SALARY_SOURCES[next(iter(sources))] if len(sources) == 1 and sources <= SALARY_SOURCES.keys() else "Theo cấu hình từng nhân viên"


def _combined_calculation(conn, month: str, norm: Callable[[Any], str], source: str = "employee", *, context=None) -> dict[str, Any]:
    # Old clients may still send a global source. It is only a compatibility
    # alias; each persisted employee choice remains authoritative.
    if source not in {"employee", "attendance", "schedule"}:
        raise HTTPException(400, "Nguồn tính lương không hợp lệ.")
    probation_policies = _probation_policies(conn, month)
    start, end, label = _draft_month_range(month)
    combo_counts = _combo_sale_counts(conn, start, end)
    rows, settings = [], {}
    employee_configs = _employee_config_map(conn)
    context = {} if context is None else context
    context["employee_configs"] = employee_configs
    for department in hr.admin_departments(conn):
        employees = _employees(conn, department)
        grouped = {key: [employee for employee in employees
                        if _salary_source(employee_configs.get(str(employee["username"]).strip().casefold())) == key]
                   for key in SALARY_SOURCES}
        for selected_source, selected_employees in grouped.items():
            if not selected_employees:
                continue
            calculator = _schedule_calculation if selected_source == "schedule" else _calculation
            result = calculator(conn, department, month, norm, combo_counts=combo_counts,
                probation_policies=probation_policies, context=context, employees=selected_employees)
            settings[department] = {key: value for key, value in result.items() if key != "rows"}
            for row in result["rows"]:
                row["calculation_snapshot"] = _calculation_snapshot(row, month, selected_source, row["calculation_config"])
                row["calculation_source_label"] = SALARY_SOURCES[selected_source]
                row["calculation_snapshot"]["late_events"] = _late_event_key(context["late_events"].get(norm(row["employee_username"]), []))
                rows.append(row)
    saved_rows, draft_revision = _setting_snapshot(conn, _draft_key(month), [])
    saved_advances = {norm(item.get("employee_username")): _number(item.get("advance"))
        for item in saved_rows if isinstance(item, dict)} if isinstance(saved_rows, list) else {}
    for index, row in enumerate(rows, start=1):
        row["tt"] = index
        row["advance"] = saved_advances.get(norm(row.get("employee_username")), _number(row.get("advance")))
        row.update(_recalculate(row, row["calculation_config"]))
    return {"ok": True, "month": month, "month_label": label, "source": "employee",
            "source_label": "Theo cấu hình từng nhân viên", "start": start.isoformat(), "end": end.isoformat(),
            "is_draft": True, "draft_revision": draft_revision,
            "history_revision": _setting_snapshot(conn, "department_payroll_combined_history", [])[1],
            "departments": settings, "rows": rows}


def _combined_employee_catalog(conn) -> dict[str, dict[str, Any]]:
    rows = conn.execute(text(f"""
        SELECT username,COALESCE(full_name,'') AS full_name,COALESCE(email,'') AS email,
               {hr.DEPARTMENT_SQL} AS role
        FROM employees
        WHERE {hr.ADMIN_PAY_SQL}
          AND NOT ({PAYROLL_EXCLUDED_SQL})
          AND COALESCE(payload->>'__deleted','false') <> 'true'
          AND lower(COALESCE(payload->>'Trạng thái làm việc',payload->>'employment_status','đang làm việc')) IN ('đang làm việc','thử việc')
    """)).mappings().all()
    return {str(item["username"]).strip().casefold(): dict(item) for item in rows}


def _clean_combined_rows(conn, rows: list[dict[str, Any]], norm: Callable[[Any], str], *, month=None, history_id="", history_department="") -> list[dict[str, Any]]:
    # Hold the saved source/rate choice stable through the caller-owned save or
    # completion transaction; settings updates and renames take the exclusive lock.
    conn.execute(text("SELECT pg_advisory_xact_lock_shared(hashtext('vera:department-employee-salary'))"))
    catalog = _combined_employee_catalog(conn)
    # Validate membership before any source read (and before trusting a posted
    # source/config). Exports may submit a filtered subset of the roster.
    keys = [str(row.get("employee_username") or "").strip().casefold() for row in rows]
    if not rows or len(set(keys)) != len(keys) or any(not key or key not in catalog for key in keys):
        raise HTTPException(400, "Bảng lương có nhân viên trống, trùng, không thuộc Lương hành chánh hoặc đang đánh dấu Không tính lương. Hãy tải lại bảng.")
    start, end, _ = _draft_month_range(month)
    participation.require_payroll_participants(rows, start, end, key='employee_username', administrative_payroll=True)
    context = {}
    current = _combined_calculation(conn, month, norm, context=context)
    current_rows = {str(row["employee_username"]).strip().casefold(): row for row in current["rows"]}
    saved = payroll._setting(conn, f"department_payroll_combined_draft_{month}", [])
    saved_rows = {str(row.get("employee_username") or "").strip().casefold(): row
                  for row in saved if isinstance(row, dict)} if isinstance(saved, list) else {}
    history_rows = {}
    if history_id:
        entry = _history_entry(conn, history_id, month, history_department)
        history_rows = {str(row.get("employee_username") or "").strip().casefold(): row
                        for row in entry.get("rows", []) if isinstance(row, dict)}
    output = []
    probation_policies = _probation_policies(conn, month, usernames=keys)
    for supplied, key in zip(rows, keys):
        employee = catalog[key]
        latest = current_rows.get(key)
        previous = history_rows.get(key) if saved_rows.get(key, {}).get("_opened_history_id") == history_id else None
        snapshot = supplied.get("calculation_snapshot")
        trusted = None
        if isinstance(snapshot, dict):
            # Only explicitly reopened completed history may retain old source/rates.
            # An editable draft must match a fresh calculation; changing source
            # cannot keep an old schedule draft to escape attendance validation.
            # Matching a server-held snapshot or a fresh server calculation is
            # required. A client cannot mint another employee/month/source/rate.
            for candidate in (latest, previous):
                if candidate and candidate.get("calculation_snapshot") == snapshot:
                    trusted = candidate
                    break
        elif previous and not previous.get("calculation_snapshot"):
            trusted = previous  # Legacy saved money is only adopted from DB.
        elif latest:
            trusted = latest
        if not trusted:
            raise HTTPException(409, "Nguồn hoặc cấu hình lương đã thay đổi. Hãy Tính lại lương trước khi lưu/xuất.")
        source = trusted.get("calculation_source") or _salary_source(context["employee_configs"].get(key))
        cfg = trusted.get("calculation_config") or latest.get("calculation_config")
        if not isinstance(source, str) or source not in SALARY_SOURCES:
            raise HTTPException(409, "Bảng nháp chưa có nguồn lương hợp lệ. Hãy Tính lại lương.")
        if supplied.get("calculation_source", source) != source or (
                isinstance(supplied.get("calculation_config"), dict) and supplied["calculation_config"] != cfg):
            raise HTTPException(409, "Không được đổi nguồn hoặc đơn giá trên bảng lương. Hãy lưu cấu hình và Tính lại lương.")
        events = context["late_events"].get(norm(employee["username"]), [])
        if snapshot and snapshot.get("late_events", []) != _late_event_key(events):
            raise HTTPException(409, "Phạt đi trễ đã thay đổi. Hãy Tính lại lương để tránh trừ trùng hoặc dùng tiền phạt cũ.")
        if _number(supplied.get("late_penalty")) < sum(event["amount"] for event in events):
            raise HTTPException(409, "Phạt đi trễ HC phải giữ nguyên số tiền đã duyệt. Hãy sửa Đi trễ có phép tại Nội quy HC rồi Tính lại lương.")
        row = dict(supplied)
        row.update({"tt": len(output) + 1, "employee_username": employee["username"],
            "employee_name": employee.get("full_name") or employee["username"], "email": employee.get("email") or "",
            "department": str(employee.get("role") or "").lower(), "department_label": trusted.get("department_label", ""),
            "calculation_config": cfg, "calculation_source": source, "calculation_source_label": SALARY_SOURCES[source]})
        for field in TIME_FIELDS:
            if snapshot and float(supplied.get(field) or 0) != float(trusted.get(field) or 0):
                raise HTTPException(409, "Giờ/ngày công không khớp nguồn đã tính. Hãy Tính lại lương.")
            row[field] = trusted.get("unadjusted_time", {}).get(field, trusted.get(field, 0))
        row["payroll_time_basis"] = dict(trusted.get("unadjusted_time_basis") or trusted.get("payroll_time_basis") or {key: str(row[key]) for key in TIME_FIELDS})
        row["configuration_issues"] = list(trusted.get("configuration_issues") or [])
        row = probation.apply(row, probation_policies.get(key), saved=True)
        _calculation_inputs(conn, start, end, norm, "schedule", context)
        if source == "attendance":
            _calculation_inputs(conn, start, end, norm, "attendance", context)
            totals = _attendance_totals(context["records_by_source"]["attendance"].get(norm(employee["username"]), []),
                employee["username"], norm, cfg, schedule_records=context["records_by_source"]["schedule"].get(norm(employee["username"]), []),
                definitions=context["definitions"], department=row["department"])
            row.update(attendance_pending=bool(totals["pending_dates"]), pending_dates=totals["pending_dates"],
                       incomplete_days=totals["incomplete_days"])
        else:
            row.update(attendance_pending=False, pending_dates=[], incomplete_days=0)
        row = _late_payroll_adjustment(row, cfg, source, events,
            context["records_by_source"].get("attendance", {}).get(norm(employee["username"]), []),
            context["records_by_source"]["schedule"].get(norm(employee["username"]), []), context["definitions"], norm)
        row["calculation_snapshot"] = trusted.get("calculation_snapshot") or _calculation_snapshot(row, month, source, cfg)
        row["calculation_snapshot"]["late_events"] = _late_event_key(events)
        if history_id:
            row["_opened_history_id"] = history_id
        else:
            row.pop("_opened_history_id", None)
        output.append(row)
    return output


def _clean_rows(conn, department: str, rows: list[dict[str, Any]], cfg: dict[str, Any], norm, *, month=None, history_id="") -> list[dict[str, Any]]:
    catalog = {norm(item["username"]) for item in _employees(conn, department)}
    if any(norm(row.get("employee_username")) not in catalog for row in rows):
        raise HTTPException(400, "Bảng lương có nhân viên không thuộc đúng bộ phận.")
    return _clean_combined_rows(conn, rows, norm, month=month, history_id=history_id, history_department=department)


def _require_complete_attendance(conn, month, rows, norm):
    if any(row.get("configuration_pending") for row in rows):
        raise HTTPException(409, "Bảng lương thiếu cấu hình giờ ca hoặc đơn giá. Lưu nháp và bổ sung cấu hình trước khi chốt/xuất/gửi.")
    if any(row.get("calculation_source") == "attendance" and row.get("attendance_pending") for row in rows):
        raise HTTPException(409, "Công còn thiếu bằng chứng. Lưu nháp và xác nhận công trước khi chốt/xuất/gửi bảng lương.")
    from vera_attendance_source import effective_date
    cutoff = effective_date()
    start, end, _ = _draft_month_range(month)
    participation.require_payroll_participants(rows, start, end, key='employee_username', administrative_payroll=True)
    if not cutoff or end < cutoff:
        return
    selected = {norm(r.get('employee_username')) for r in rows
                if r.get('calculation_source') != 'schedule'}
    if not selected:
        return
    pending = [r for r in attendance._records(conn, max(start, cutoff), end)
               if norm(r.get('employee_name')) in selected
               and r.get('attendance_pending')]
    if pending:
        raise HTTPException(409, 'Công FaceGate còn thiếu bằng chứng hoặc ca chưa kết thúc. Lưu nháp và xác nhận công trước khi chốt/gửi bảng lương.')


def _history_entry(conn, history_id, month, department=""):
    keys = ["department_payroll_combined_history"]
    if department:
        keys.append(_setting_key(department, "history"))
    for key in keys:
        history, _ = _setting_snapshot(conn, key, [])
        entry = next((item for item in history if isinstance(item, dict) and item.get("id") == history_id), None) if isinstance(history, list) else None
        if entry:
            if entry.get("month") != month:
                raise HTTPException(409, "Lịch sử không khớp tháng lương.")
            return entry
    raise HTTPException(409, "Không tìm thấy lịch sử lương đang dùng.")


def _frozen_export_rows(conn, body):
    if not body.history_id:
        return None
    department = getattr(body, "department", "")
    entry = _history_entry(conn, body.history_id, body.month, department)
    stored = {str(row.get("employee_username") or "").strip().casefold(): row
              for row in _visible_payroll_rows(conn, entry.get("rows", []), month=body.month)}
    def comparable(row):
        return {key: value for key, value in row.items() if key not in {"tt", "_opened_history_id"}}
    result, seen = [], set()
    for row in body.rows:
        key = str(row.get("employee_username") or "").strip().casefold()
        original = stored.get(key)
        if key in seen or not original or (department and original.get("department", department) != department):
            raise HTTPException(400, "Nhân viên xuất không khớp lịch sử lương/bộ phận.")
        seen.add(key)
        if comparable(row) != comparable(original):
            return None  # Edited work must pass current validation explicitly.
        result.append(dict(original, tt=len(result) + 1))
    return result


def _printable_rows(rows):
    result = []
    for row in rows:
        item = dict(row)
        item["effective_late_penalty"] = row.get("effective_late_penalty", row.get("late_penalty", 0))
        if row.get("calculation_source"):
            item["employee_name"] = str(row.get("employee_name") or "") + " · " + SALARY_SOURCES.get(row["calculation_source"], "")
        if row.get("unpaid_late_wage"):
            item["employee_name"] += f" · Lương trễ không tính: {_money(row['unpaid_late_wage'])}"
        result.append(item)
    return result


def _workbook(rows: list[dict[str, Any]], department: str, label: str) -> bytes:
    department_label = str(rows[0].get("department_label") if rows else department)
    wb = Workbook(); ws = wb.active; ws.title = "Lương bộ phận"
    ws.append([f"BẢNG LƯƠNG {department_label.upper()} THÁNG {label}"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(EXCEL_COLUMNS))
    ws["A1"].font = Font(bold=True, size=16, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="1F513F")
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.append([title for _, title in EXCEL_COLUMNS])
    for cell in ws[2]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="A99D97")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in rows:
        ws.append([row.get(key, row.get("late_penalty", 0) if key == "effective_late_penalty" else "") for key, _ in EXCEL_COLUMNS])
    ws.freeze_panes = "A3"; ws.auto_filter.ref = f"A2:{ws.cell(2, len(EXCEL_COLUMNS)).column_letter}{ws.max_row}"
    for index, (key, _) in enumerate(EXCEL_COLUMNS, start=1):
        ws.column_dimensions[ws.cell(2, index).column_letter].width = 24 if key == "employee_name" else 16
        if key in ROW_MONEY_FIELDS or key == "effective_late_penalty":
            for cell in ws.iter_cols(min_col=index, max_col=index, min_row=3):
                for item in cell: item.number_format = '#,##0"đ"'
    from openpyxl.utils import get_column_letter
    total_row = ws.max_row + 1
    ws.cell(total_row, 2, 'TỔNG')
    for column in range(5, 20):
        letter = get_column_letter(column)
        ws.cell(total_row, column, f'=SUM({letter}3:{letter}{total_row - 1})')
    for cell in ws[total_row]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='E5F0E9')
    stream = BytesIO(); wb.save(stream); return stream.getvalue()


def _combined_workbook(rows: list[dict[str, Any]], label: str) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Lương hành chánh"
    worksheet.append([f"BẢNG LƯƠNG HÀNH CHÁNH THÁNG {label}"])
    worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(EXCEL_COLUMNS))
    worksheet["A1"].font = Font(bold=True, size=16, color="FFFFFF")
    worksheet["A1"].fill = PatternFill("solid", fgColor="1F513F")
    worksheet["A1"].alignment = Alignment(horizontal="center")
    worksheet.append([title for _, title in EXCEL_COLUMNS])
    for cell in worksheet[2]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="A99D97")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in rows:
        worksheet.append([row.get(key, row.get("late_penalty", 0) if key == "effective_late_penalty" else "") for key, _ in EXCEL_COLUMNS])
    worksheet.freeze_panes = "A3"
    worksheet.auto_filter.ref = f"A2:{worksheet.cell(2, len(EXCEL_COLUMNS)).column_letter}{worksheet.max_row}"
    for index, (key, _) in enumerate(EXCEL_COLUMNS, start=1):
        worksheet.column_dimensions[worksheet.cell(2, index).column_letter].width = 26 if key == "employee_name" else 17
        if key in ROW_MONEY_FIELDS or key == "effective_late_penalty":
            for column in worksheet.iter_cols(min_col=index, max_col=index, min_row=3):
                for cell in column:
                    cell.number_format = '#,##0"đ"'
    total_row = worksheet.max_row + 1
    worksheet.cell(total_row, 2, 'TỔNG')
    from openpyxl.utils import get_column_letter
    for column in range(5, 20):
        letter = get_column_letter(column)
        worksheet.cell(total_row, column, f'=SUM({letter}3:{letter}{total_row - 1})')
    for cell in worksheet[total_row]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='E5F0E9')
        cell.number_format = '#,##0.##' if cell.column <= 8 else '#,##0"đ"'
    worksheet.sheet_properties.pageSetUpPr.fitToPage = True
    worksheet.page_setup.orientation = 'landscape'
    worksheet.page_setup.paperSize = worksheet.PAPERSIZE_A4
    worksheet.page_setup.fitToWidth = 1
    worksheet.page_setup.fitToHeight = 0
    worksheet.print_title_rows = '1:2'
    worksheet.print_options.horizontalCentered = True
    worksheet.print_area = f'A1:S{total_row}'
    import json
    provenance = workbook.create_sheet("Nguồn và khấu trừ")
    provenance.append(["Nhân viên", "Nguồn lương", "Lương thời gian trễ không tính", "Tổng mức giảm đi trễ", "Phạt trễ trừ thêm", "Căn cứ tính lương"])
    for row in rows:
        provenance.append([row.get("employee_username", ""), row.get("calculation_source_label") or
            {"schedule": "Thống kê", "attendance": "Chấm công"}.get(row.get("calculation_source"), "Bản lưu cũ"),
            row.get("unpaid_late_wage", 0), row.get("late_penalty", 0),
            row.get("effective_late_penalty", row.get("late_penalty", 0)),
            json.dumps(row.get("calculation_snapshot") or {}, ensure_ascii=False)])
    for letter in ("A", "B", "C", "D", "E"):
        provenance.column_dimensions[letter].width = 28
    provenance.column_dimensions["F"].width = 80
    provenance.freeze_panes = "A2"
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _money(value: Any) -> str:
    return f"{payroll._number(value):,}".replace(",", ".") + "đ"


def _detail_text(row: dict[str, Any]) -> str:
    labels = dict(EXCEL_COLUMNS)
    keys = ("work_days", "salary", "full_allowance", "attendance_bonus", "responsibility", "seniority", "combo_sales", "violation_penalty", "effective_late_penalty", "advance")
    row = dict(row, effective_late_penalty=row.get("effective_late_penalty", row.get("late_penalty", 0)))
    return "\n".join(f"{labels[key]}: {_money(row.get(key)) if key != 'work_days' else row.get(key, 0)}" for key in keys)


def _render_template(template: dict[str, str], row: dict[str, Any], month_label: str) -> tuple[str, str, str]:
    values = {
        "ten_nhan_vien": str(row.get("employee_name") or row.get("employee_username") or ""),
        "bo_phan": str(row.get("department_label") or ""), "thang": month_label,
        "tong_luong": _money(row.get("total_salary")),
        "tong_phat": _money(_number(row.get("violation_penalty")) + _number(row.get("effective_late_penalty", row.get("late_penalty", 0)))),
        "thuc_nhan": _money(row.get("net_salary")), "bang_chi_tiet": _detail_text(row),
    }
    subject = str(template.get("subject") or DEFAULT_EMAIL_TEMPLATE["subject"])
    body = str(template.get("body") or DEFAULT_EMAIL_TEMPLATE["body"])
    for key, value in values.items():
        subject = subject.replace("{" + key + "}", value)
        body = body.replace("{" + key + "}", value)
    html = "<br>".join(escape(line) for line in body.splitlines())
    return subject, body, f"<!doctype html><html lang='vi'><body style='font:14px Arial;line-height:1.5;color:#22352d;max-width:720px;padding:24px'>{html}</body></html>"


def _resolve_payroll_email_rows(conn, rows):
    recipients = _combined_employee_catalog(conn)
    result = []
    for row in rows:
        employee = recipients.get(str(row.get("employee_username") or "").strip().casefold())
        if not employee or "@" not in str(employee.get("email") or ""):
            raise HTTPException(409, "Nhân viên không còn trong danh sách nhận lương hoặc chưa có email hiện tại hợp lệ.")
        # A frozen financial snapshot is immutable; recipient routing is resolved
        # separately from today's verified directory, never from posted/history email.
        result.append(dict(row, email=str(employee["email"]).strip()))
    return result


def _email_content(row: dict[str, Any], start: date, end: date, violations: list[dict[str, Any]]) -> tuple[str, str, str]:
    """Render the validated HC amounts without grouping or recalculating them."""
    name = str(row.get("employee_name") or row.get("employee_username") or "")
    summary = [(label, payroll._number(row.get(key, row.get("late_penalty", 0) if key == "effective_late_penalty" else 0))) for key, label in EMAIL_SUMMARY_COLUMNS]
    email_row = {
        "Số tiền thực nhận": row.get("net_salary"),
        "Tiền phạt trong tháng": _number(row.get("violation_penalty")) + _number(row.get("effective_late_penalty", row.get("late_penalty", 0))),
    }
    options = {"summary_rows": summary, "date_format": "%d-%m-%Y"}
    subject = payroll._payroll_email_subject(row.get("employee_username"), start, end, date_format="%d-%m-%Y")
    plain = payroll._payroll_email_text(name, start, end, email_row, violations, **options)
    html = payroll._payroll_email_html(name, start, end, email_row, violations, **options)
    if row.get("calculation_source"):
        # These details come from today's violation ledger, including for a
        # frozen payslip. They are references, not additional payroll debits or
        # evidence that rewrites the frozen financial snapshot. Keep the shared
        # KTV renderer and its default labels unchanged.
        reference_title = "Vi phạm tham chiếu từ bản ghi hiện tại (không cộng thêm vào bảng lương):"
        actual_total = "Tổng phạt thực trừ trong bảng lương:"
        plain = plain.replace("Chi tiết vi phạm trong kỳ:", reference_title, 1).replace("Tổng vi phạm:", actual_total, 1)
        html = html.replace("Chi tiết vi phạm trong kỳ:", reference_title, 1).replace(">Phạt</th>", ">Mức ghi nhận</th>", 1).replace("Tổng vi phạm:", actual_total, 1)
        note = f"Nguồn lương: {SALARY_SOURCES.get(row['calculation_source'], row['calculation_source'])}."
        if row.get("unpaid_late_wage"):
            note += f" Lương thời gian trễ không được tính: {_money(row['unpaid_late_wage'])}; phạt trễ trừ thêm: {_money(row.get('effective_late_penalty', 0))}."
        plain += "\n\n" + note
        html = html.replace("</body>", f"<p>{escape(note)}</p></body>")
    return subject, plain, html


def install_department_payroll_routes(app, *, engine_instance, current_identity, require_feature, identity_type, norm) -> None:
    if getattr(app.state, "department_payroll_installed", False):
        return

    def valid_department(department: str) -> str:
        value = str(department or "").lower().strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", value):
            raise HTTPException(404, "Bộ phận không hỗ trợ bảng lương này.")
        return value

    @app.get("/v2/department-payroll/settings")
    @app.get("/v2/department-payroll-v2/settings")
    def get_settings(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            conn.execute(text("SELECT pg_advisory_xact_lock_shared(hashtext('vera:department-employee-salary'))"))
            employee_configs, employee_sources, employee_revision = _employee_settings_snapshot(conn)
            return {
                "ok": True, "release": RELEASE, "hc_payroll_contract": HC_PAYROLL_CONTRACT,
                "departments": {key: _settings(conn, key, include_revision=True) for key in hr.admin_departments(conn)},
                "salary_config_tables": _salary_config_tables(conn, employee_configs, employee_sources),
                "employee_config_revision": employee_revision,
                "salary_employee_catalog": _salary_employee_catalog(conn, employee_sources, employee_configs),
                "email_layout": payroll.PAYROLL_EMAIL_TEMPLATE_RELEASE,
            }

    @app.put("/v2/department-payroll/settings/employees")
    @app.put("/v2/department-payroll-v2/settings/employees")
    def save_employee_settings(body: EmployeeSalaryConfigUpdate, ident: identity_type = Depends(current_identity)):
        if str(ident.role or "").lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được sửa cấu hình lương theo nhân viên.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_config_edit")
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:department-employee-salary'))"))
            stored, sources, revision = _employee_settings_snapshot(conn)
            if body.expected_revision is None or body.expected_revision != revision:
                raise HTTPException(409, "Cấu hình lương đã thay đổi hoặc thiếu phiên bản. Hãy tải lại trước khi lưu.")
            catalog = {row["employee_username"]: row for row in _salary_employee_catalog(conn, sources, stored)}
            active_names = {name.casefold() for name in catalog}
            supplied = dict(stored) if body.rows is None else {name: config for name, config in stored.items() if name.casefold() not in active_names}
            # Source changes patch only named employees. Persist legacy choices
            # before removing a numeric override, without materializing rates.
            source_values = dict(sources) if isinstance(sources, dict) else {}
            for name in catalog:
                source_values[name] = _saved_employee_source(name, sources, stored)
            source_seen = set()
            for choice in body.salary_sources:
                username = str(choice.get("employee_username") or "").strip()
                if username not in catalog or username.casefold() in source_seen:
                    raise HTTPException(400, "Nguồn lương có nhân viên trống, trùng hoặc không thuộc HC.")
                source_seen.add(username.casefold())
                source_values[username] = _salary_source(choice)
            for row in body.rows or []:
                username = str(row.get("employee_username") or "").strip()
                employee = catalog.get(username)
                if not employee or username in supplied:
                    raise HTTPException(400, "Cấu hình có nhân viên trống, trùng hoặc không thuộc đúng bộ phận.")
                previous = stored.get(username, stored.get(username.casefold()))
                supplied[username] = _employee_numeric_update(employee["department"], row, previous, _settings(conn, employee["department"])["config"])
                if username.casefold() not in source_seen and "salary_source" in row:
                    source_values[username] = _salary_source(row)
            payroll._put_setting(conn, "department_employee_salary_configs", supplied, ident.employee_username)
            payroll._put_setting(conn, EMPLOYEE_SOURCE_KEY, source_values, ident.employee_username)
            tables = _salary_config_tables(conn, supplied, source_values)
            employee_catalog = _salary_employee_catalog(conn, source_values, supplied)
        return {"ok": True, "salary_config_tables": tables, "salary_employee_catalog": employee_catalog, "employee_config_revision": revision + 1, "message": "Đã lưu cấu hình lương theo từng nhân viên."}

    @app.put("/v2/department-payroll/settings/{department}")
    @app.put("/v2/department-payroll-v2/settings/{department}")
    def save_settings(department: str, body: DepartmentSettingsUpdate, ident: identity_type = Depends(current_identity)):
        department = valid_department(department)
        if str(ident.role or "").lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được sửa quy định phạt, công thức lương và mẫu email.")
        template = {
            "subject": str(body.email_template.get("subject") or "")[:500],
            "body": str(body.email_template.get("body") or "")[:10000],
        }
        if not template["subject"] or not template["body"]:
            raise HTTPException(400, "Mẫu email phải có tiêu đề và nội dung.")
        rules = [item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in body.penalty_rules]
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_config_edit")
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:department-employee-salary'))"))
            _, revision = _require_setting_revision(conn, _setting_key(department, "config"), body.expected_revision)
            config = _clean_config(department, body.config, _settings(conn, department)["config"]["calculation_mode"])
            payroll._put_setting(conn, _setting_key(department, "config"), config, ident.employee_username)
            payroll._put_setting(conn, _setting_key(department, "penalty_rules"), rules, ident.employee_username)
            payroll._put_setting(conn, _setting_key(department, "email_template"), template, ident.employee_username)
            saved = _settings(conn, department)
        return {"ok": True, "message": f"Đã lưu cấu hình {department}.", **saved, "config_revision": revision + 1}

    @app.get("/v2/department-payroll/calculate")
    @app.get("/v2/department-payroll-v2/calculate")
    def calculate(department: str = Query(...), month: str = Query(...), ident: identity_type = Depends(current_identity)):
        department = valid_department(department)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            settings = _settings(conn, department)
            calculated = _combined_calculation(conn, month, norm)
            return {**settings, **{key: calculated[key] for key in ("month", "month_label", "start", "end")},
                    "rows": [row for row in calculated["rows"] if row["department"] == department],
                    "draft_revision": _setting_snapshot(conn, _setting_key(department, f"draft_{month}"), [])[1],
                    "history_revision": _setting_snapshot(conn, _setting_key(department, "history"), [])[1]}

    @app.get("/v2/department-payroll/combined/calculate")
    @app.get("/v2/department-payroll-v2/combined/calculate")
    def calculate_combined(
        month: str = Query(...),
        source: str = Query("employee"),
        ident: identity_type = Depends(current_identity),
    ):
        _month_range(month)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            return _combined_calculation(conn, month, norm, source.strip().lower())

    @app.get("/v2/department-payroll/combined/draft")
    @app.get("/v2/department-payroll-v2/combined/draft")
    def get_combined_draft(month: str = Query(...), ident: identity_type = Depends(current_identity)):
        _month_range(month)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            rows, revision = _setting_snapshot(conn, _draft_key(month), [])
            history_revision = _setting_snapshot(conn, "department_payroll_combined_history", [])[1]
            rows = _visible_payroll_rows(conn, rows, month=month)
        return {"ok": True, "month": month, "rows": rows if isinstance(rows, list) else [],
                "draft_revision": revision, "history_revision": history_revision,
                "history_id": next((row.get("_opened_history_id") for row in rows if row.get("_opened_history_id")), "")}

    @app.put("/v2/department-payroll/combined/draft")
    @app.put("/v2/department-payroll-v2/combined/draft")
    def save_combined_draft(body: CombinedPayrollDraft, ident: identity_type = Depends(current_identity)):
        _month_range(body.month)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            _, revision = _require_draft_revision(conn, body.month, body.expected_revision)
            rows = _clean_combined_rows(conn, body.rows, norm, month=body.month, history_id=body.history_id)
            payroll._put_setting(conn, f"department_payroll_combined_draft_{body.month}", rows, ident.employee_username)
        return {"ok": True, "rows": rows, "draft_revision": revision + 1, "message": "Đã lưu nháp bảng Lương hành chánh."}

    @app.delete("/v2/department-payroll/combined/draft")
    @app.delete("/v2/department-payroll-v2/combined/draft")
    def delete_combined_draft(month: str = Query(...), expected_revision: int | None = Query(None, ge=0), ident: identity_type = Depends(current_identity)):
        _month_range(month)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            _, revision = _require_draft_revision(conn, month, expected_revision)
            payroll._put_setting(conn, f"department_payroll_combined_draft_{month}", [], ident.employee_username)
        return {"ok": True, "month": month, "draft_revision": revision + 1, "message": "Đã xóa bảng lương nháp. Lịch sử bảng lương đã hoàn thành được giữ nguyên."}

    @app.get("/v2/department-payroll/combined/history")
    @app.get("/v2/department-payroll-v2/combined/history")
    def get_combined_history(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            history, history_revision = _setting_snapshot(conn, "department_payroll_combined_history", [])
        if not isinstance(history, list):
            history = []
        items = []
        for item in history:
            if not isinstance(item, dict):
                continue
            history_rows = item.get("rows") if isinstance(item.get("rows"), list) else []
            items.append({
                **{key: item.get(key) for key in ("id", "month", "month_label", "saved_at", "saved_by", "source_label")},
                "employee_count": len(history_rows),
                "total_net": sum(_number(row.get("net_salary")) for row in history_rows if isinstance(row, dict)),
            })
        return {"ok": True, "history_revision": history_revision, "items": sorted(items, key=lambda item: str(item.get("saved_at") or ""), reverse=True)}

    @app.post("/v2/department-payroll/combined/history/{history_id}/open")
    @app.post("/v2/department-payroll-v2/combined/history/{history_id}/open")
    def open_combined_history(history_id: str, expected_revision: int | None = Query(None, ge=0), ident: identity_type = Depends(current_identity)):
        wanted = str(history_id or "").strip()
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            history, history_revision = _setting_snapshot(conn, "department_payroll_combined_history", [])
            item = next((entry for entry in history if isinstance(entry, dict) and str(entry.get("id")) == wanted), None) if isinstance(history, list) else None
            if not item:
                raise HTTPException(404, "Không tìm thấy lịch sử bảng Lương hành chánh.")
            _, revision = _require_draft_revision(conn, item["month"], expected_revision)
            rows = item.get("rows") if isinstance(item.get("rows"), list) else []
            rows = _visible_payroll_rows(conn, rows, month=item["month"])
            rows = [dict(row, _opened_history_id=wanted) for row in rows]
            payroll._put_setting(conn, f"department_payroll_combined_draft_{item['month']}", rows, ident.employee_username)
        return {
            "ok": True, "draft_revision": revision + 1, "history_revision": history_revision, "history_id": wanted, "month": item["month"], "rows": rows,
            "message": f"Đã mở bảng lương tháng {item.get('month_label')} để sửa. Bấm Hoàn thành bảng lương để cập nhật lịch sử.",
        }

    @app.post("/v2/department-payroll/combined/complete")
    @app.post("/v2/department-payroll-v2/combined/complete")
    def complete_combined(body: CombinedPayrollDraft, ident: identity_type = Depends(current_identity)):
        _, _, label = _month_range(body.month)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
            _, revision = _require_draft_revision(conn, body.month, body.expected_revision)
            history, history_revision = _setting_snapshot(conn, "department_payroll_combined_history", [])
            if body.expected_history_revision is None or body.expected_history_revision != history_revision:
                raise HTTPException(409, "Lịch sử lương đã thay đổi. Hãy tải lại trước khi hoàn thành.")
            rows = _clean_combined_rows(conn, body.rows, norm, month=body.month, history_id=body.history_id)
            _require_complete_attendance(conn, body.month, rows, norm)
            history = history if isinstance(history, list) else []
            if body.history_id:
                existing = next((item for item in history if isinstance(item, dict) and str(item.get("id")) == body.history_id), None)
                if not existing:
                    raise HTTPException(404, "Không tìm thấy lịch sử bảng Lương hành chánh đang sửa.")
                if existing.get("month") != body.month:
                    raise HTTPException(400, "Không được chuyển lịch sử bảng lương sang tháng khác.")
            else:
                existing = next((item for item in history if isinstance(item, dict) and item.get("month") == body.month), None)
            history_id = str(existing.get("id")) if existing else str(uuid.uuid4())
            start, end, _ = _draft_month_range(body.month)
            preserved = participation.preserved_payroll(
                (existing or {}).get('rows', []), start, end, key='employee_username')
            replaced = {norm(row.get('employee_username')) for row in rows}
            preserved = [row for row in preserved if norm(row.get('employee_username')) not in replaced]
            source_label = _source_label(rows)
            completed = {
                "id": history_id, "month": body.month, "month_label": label,
                "saved_at": datetime.now(VN_TZ).isoformat(), "saved_by": ident.employee_username,
                "source_label": source_label,
                "rows": rows + preserved,
            }
            history = [item for item in history if not (isinstance(item, dict) and (str(item.get("id")) == history_id or item.get("month") == body.month))]
            history.append(completed)
            payroll._put_setting(conn, "department_payroll_combined_history", history[-120:], ident.employee_username)
            payroll._put_setting(conn, f"department_payroll_combined_draft_{body.month}", rows, ident.employee_username)
        return {
            "ok": True, "history_id": history_id, "rows": rows,
            "draft_revision": revision + 1, "history_revision": history_revision + 1,
            "message": f"Đã hoàn thành và lưu bảng Lương hành chánh tháng {label} vào lịch sử.",
        }

    @app.post("/v2/department-payroll/combined/export.xlsx")
    @app.post("/v2/department-payroll-v2/combined/export.xlsx")
    def export_combined_xlsx(body: CombinedPayrollDraft, ident: identity_type = Depends(current_identity)):
        _, _, label = _month_range(body.month)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_export")
            rows = _frozen_export_rows(conn, body)
            if rows is None:
                rows = _clean_combined_rows(conn, body.rows, norm, month=body.month, history_id=body.history_id)
                _require_complete_attendance(conn, body.month, rows, norm)
        content = _combined_workbook(rows, label)
        return StreamingResponse(
            BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Luong_hanh_chanh_{body.month}.xlsx"},
        )

    @app.post("/v2/department-payroll/combined/export.{file_type}")
    @app.post("/v2/department-payroll-v2/combined/export.{file_type}")
    def export_combined_share(file_type: str, body: CombinedPayrollDraft, ident: identity_type = Depends(current_identity)):
        if file_type not in {'png', 'pdf'}:
            raise HTTPException(400, 'Định dạng chia sẻ không hợp lệ.')
        _, _, label = _month_range(body.month)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_export")
            rows = _frozen_export_rows(conn, body)
            if rows is None:
                rows = _clean_combined_rows(conn, body.rows, norm, month=body.month, history_id=body.history_id)
                _require_complete_attendance(conn, body.month, rows, norm)
        from vera_payroll_print import render_payroll
        from vera_department_payroll_share import export_values
        values = export_values(_printable_rows(rows), EXCEL_COLUMNS)[1:]
        printable = [dict(zip([key for key, _ in EXCEL_COLUMNS], row)) for row in values]
        content = render_payroll(printable, EXCEL_COLUMNS, f'BẢNG LƯƠNG HÀNH CHÁNH - {label}', file_type)
        return StreamingResponse(BytesIO(content), media_type='application/pdf' if file_type == 'pdf' else 'image/png',
                                 headers={'Content-Disposition': f'attachment; filename=Luong_hanh_chanh_{body.month}.{file_type}'})

    @app.get("/v2/department-payroll/draft")
    @app.get("/v2/department-payroll-v2/draft")
    def get_draft(department: str = Query(...), month: str = Query(...), ident: identity_type = Depends(current_identity)):
        department = valid_department(department); _month_range(month)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_calculate")
            rows, revision = _setting_snapshot(conn, _setting_key(department, f"draft_{month}"), [])
            return {"rows": _visible_payroll_rows(conn, rows, month=month), "department": department, "month": month,
                    "draft_revision": revision, "history_revision": _setting_snapshot(conn, _setting_key(department, "history"), [])[1]}

    @app.put("/v2/department-payroll/draft")
    @app.put("/v2/department-payroll-v2/draft")
    def save_draft(body: DepartmentDraft, ident: identity_type = Depends(current_identity)):
        department = valid_department(body.department); _month_range(body.month)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            _, revision = _require_setting_revision(conn, _setting_key(department, f"draft_{body.month}"), body.expected_revision)
            cfg = _settings(conn, department)["config"]
            rows = _clean_rows(conn, department, body.rows, cfg, norm, month=body.month, history_id=body.history_id)
            payroll._put_setting(conn, _setting_key(department, f"draft_{body.month}"), rows, ident.employee_username)
        return {"ok": True, "rows": rows, "draft_revision": revision + 1, "message": f"Đã lưu bảng lương nháp {department}."}

    @app.post("/v2/department-payroll/save")
    @app.post("/v2/department-payroll-v2/save")
    def save_official(body: DepartmentDraft, ident: identity_type = Depends(current_identity)):
        department = valid_department(body.department); _, _, label = _month_range(body.month)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "payroll_save")
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
            _, revision = _require_setting_revision(conn, _setting_key(department, f"draft_{body.month}"), body.expected_revision)
            history, history_revision = _require_setting_revision(conn, _setting_key(department, "history"), body.expected_history_revision)
            cfg = _settings(conn, department)["config"]
            rows = _clean_rows(conn, department, body.rows, cfg, norm, month=body.month, history_id=body.history_id)
            _require_complete_attendance(conn, body.month, rows, norm)
            if not isinstance(history, list):
                history = []
            start, end, _ = _draft_month_range(body.month)
            preserved = participation.preserved_payroll(
                [row for item in history if isinstance(item, dict) and item.get('month') == body.month
                 for row in item.get('rows', [])], start, end, key='employee_username')
            replaced = {norm(row.get('employee_username')) for row in rows}
            preserved = [row for row in preserved if norm(row.get('employee_username')) not in replaced]
            history = [item for item in history if not (isinstance(item, dict) and item.get("month") == body.month)]
            history.append({"id": str(uuid.uuid4()), "month": body.month, "month_label": label, "saved_at": datetime.now(VN_TZ).isoformat(), "saved_by": ident.employee_username, "rows": rows + preserved})
            payroll._put_setting(conn, _setting_key(department, "history"), history[-120:], ident.employee_username)
            payroll._put_setting(conn, _setting_key(department, f"draft_{body.month}"), rows, ident.employee_username)
        return {"ok": True, "rows": rows, "draft_revision": revision + 1, "history_revision": history_revision + 1, "message": f"Đã lưu chính thức bảng lương {department} tháng {label}."}

    @app.post("/v2/department-payroll/export.xlsx")
    @app.post("/v2/department-payroll-v2/export.xlsx")
    def export_xlsx(body: DepartmentDraft, ident: identity_type = Depends(current_identity)):
        department = valid_department(body.department); _, _, label = _month_range(body.month)
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_export")
            rows = _frozen_export_rows(conn, body)
            if rows is None:
                rows = _clean_rows(conn, department, body.rows, _settings(conn, department)["config"], norm, month=body.month, history_id=body.history_id)
                _require_complete_attendance(conn, body.month, rows, norm)
        content = _workbook(rows, department, label)
        return StreamingResponse(BytesIO(content), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=Bang_luong_{department}_{body.month}.xlsx"})

    @app.post("/v2/department-payroll/email")
    @app.post("/v2/department-payroll-v2/email")
    def email_payroll(body: DepartmentEmail, ident: identity_type = Depends(current_identity)):
        department = valid_department(body.department); start, end, label = _month_range(body.month)
        sender = str(os.getenv("SMTP_SENDER_EMAIL", "veraspabienhoa@gmail.com") or "").strip()
        password = str(os.getenv("SMTP_APP_PASSWORD", "") or "").strip()
        if not password:
            raise HTTPException(503, "Máy chủ chưa cấu hình mật khẩu gửi email bảng lương.")
        with engine_instance().connect() as conn:
            require_feature(conn, ident, "payroll_email")
            settings = _settings(conn, department)
            rows = _frozen_export_rows(conn, body)
            if rows is None:
                rows = _clean_rows(conn, department, body.rows, settings["config"], norm, month=body.month, history_id=body.history_id)
                _require_complete_attendance(conn, body.month, rows, norm)
            selected = {norm(value) for value in body.employees if norm(value)}
            rows = [row for row in rows if not selected or norm(row.get("employee_username")) in selected]
            rows = _resolve_payroll_email_rows(conn, rows)
            violation_rows = conn.execute(text("""
                SELECT employee_name,leave_date,leave_reason,detail,COALESCE(penalty,0) penalty
                FROM leave_records
                WHERE leave_date BETWEEN :start AND :end AND COALESCE(penalty,0)>0
                ORDER BY leave_date,COALESCE(source_row,0),id
            """), {"start": start, "end": end}).mappings().all()
        violations_by_employee: dict[str, list[dict[str, Any]]] = {}
        for item in violation_rows:
            violations_by_employee.setdefault(norm(item.get("employee_name")), []).append(dict(item))
        selected = {norm(value) for value in body.employees if norm(value)}
        rows = [row for row in rows if not selected or norm(row.get("employee_username")) in selected]
        sent, failed = [], []
        try:
            smtp = payroll._open_payroll_smtp(sender, password)
        except Exception as exc:
            raise HTTPException(
                502,
                f"Không kết nối/xác thực được Gmail để gửi bảng lương: {str(exc)[:240]}",
            ) from exc
        try:
            for row in rows:
                recipient = str(row.get("email") or "").strip()
                if "@" not in recipient:
                    failed.append({"employee": row.get("employee_name"), "error": "Chưa có email hợp lệ"}); continue
                name = str(row.get("employee_name") or row.get("employee_username") or "")
                employee_violations = (
                    violations_by_employee.get(norm(row.get("employee_username")))
                    or violations_by_employee.get(norm(name), [])
                )
                subject, plain, html = _email_content(row, start, end, employee_violations)
                message = EmailMessage(); message["Subject"] = subject
                message["From"] = formataddr(("VERA SPA", sender)); message["To"] = recipient
                message.set_content(plain)
                message.add_alternative(html, subtype="html")
                message.add_attachment(_workbook([row], department, label), maintype="application", subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=f"Bang_luong_{row['employee_username']}_{body.month}.xlsx")
                try:
                    smtp.send_message(message); sent.append(row.get("employee_name"))
                except Exception as exc:
                    failed.append({"employee": row.get("employee_name"), "error": str(exc)[:200]})
        finally:
            try: smtp.quit()
            except Exception: pass
        return {"ok": not failed, "sent": sent, "failed": failed, "message": f"Đã gửi {len(sent)} email; lỗi {len(failed)}."}

    @app.get("/v2/department-payroll/health")
    @app.get("/v2/department-payroll-v2/health")
    def health():
        return {"ok": True, "release": RELEASE, "hc_payroll_contract": HC_PAYROLL_CONTRACT, "departments": DEPARTMENTS, "source": "Web V2 attendance + work schedule", "employee_config_tables": True, "email_layout": EMAIL_TEMPLATE_RELEASE}

    app.state.department_payroll_installed = True

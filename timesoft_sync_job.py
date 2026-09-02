"""V93.6 - Đồng bộ TimeSoft và ghi phạt trực tiếp vào PostgreSQL.

Mỗi lần Cloud Scheduler gọi:
1) Đồng bộ TimeSoft -> PostgreSQL (giữ nguyên chức năng V82/V83).
2) Đọc trạng thái Auto Check và Nội quy từ PostgreSQL.
3) Nếu PAUSED: không ghi phạt.
4) Nếu RUNNING:
   - TimeSoft: Đi trễ không phép khi trễ >= 5 phút.
   - Nghỉ giữa ca: Ra ngoài vào muộn ngay khi có FaceID vào lại trễ.
   - Bảng tour: Ra ngoài vào muộn khi cột Vào trễ >= 5 phút.
   - Cẩm Nhung * được đối chiếu như Cẩm Nhung.
   - Chống trùng Ngày + Nhân viên + Lý do.
   - Ghi trực tiếp `leave_records` và `vera_auto_check_event` trong PostgreSQL.

Job snapshot thường xuyên có thể giới hạn phạm vi chỉ còn TimeSoft; job 20:00
không được ghi lại cùng vi phạm vào Google Sheet.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin

import gspread
import pandas as pd
import requests
from google.auth import default as google_auth_default
from sqlalchemy import text

import vera_postgres as vpg
import vera_auto_check as auto_check
from vera_attendance_rules import supported_late_minutes

VN_TZ = timezone(timedelta(hours=7))

# -------------------- TimeSoft --------------------
BASE_URL = str(os.getenv("TIMESOFT_BASE_URL", "https://vera.timesoft.vn") or "https://vera.timesoft.vn").rstrip("/")
USERNAME = str(os.getenv("TIMESOFT_USERNAME", "") or "").strip()
PASSWORD = str(os.getenv("TIMESOFT_PASSWORD", "") or "")
SYNC_DAYS = max(1, min(7, int(os.getenv("TIMESOFT_SYNC_DAYS", "2") or 2)))
# Payroll reads one immutable invoice snapshot per calendar day.  The normal
# five-minute sync only needs today + yesterday, but a newly-created PostgreSQL
# database may not contain the earlier days of the active payroll period even
# though TimeSoft itself has them.  Backfill only missing invoice snapshots in
# small batches; existing historical rows are never re-fetched by this path.
PAYROLL_BACKFILL_DAYS = max(
    SYNC_DAYS,
    min(120, int(os.getenv("TIMESOFT_PAYROLL_BACKFILL_DAYS", "45") or 45)),
)
PAYROLL_BACKFILL_BATCH_DAYS = max(
    1,
    min(31, int(os.getenv("TIMESOFT_PAYROLL_BACKFILL_BATCH_DAYS", "12") or 12)),
)
CHECKIN_PAGE_SIZE = max(20, min(500, int(os.getenv("TIMESOFT_CHECKIN_PAGE_SIZE", "100") or 100)))
MAX_CHECKIN_PAGES = 500
# V93.3: snapshot theo ngày là dữ liệu lịch sử, không còn TTL 24 giờ.
# Có thể đổi bằng env TIMESOFT_HISTORY_RETENTION_DAYS; mặc định giữ 10 năm.
TIMESOFT_HISTORY_RETENTION_DAYS = max(
    30, min(36500, int(os.getenv("TIMESOFT_HISTORY_RETENTION_DAYS", "3650") or 3650))
)
TIMESOFT_HISTORY_TTL_SECONDS = TIMESOFT_HISTORY_RETENTION_DAYS * 86400
LOCK_NAME = "vera-timesoft-background-sync-v84"

REPORT_SUMMARY_PAGE = "/Report/ReportSummaryInvoice/Index"
REPORT_CHECKIN_PAGE = "/Report/ReportEmployeeCheckin/Index"
API_SUMMARY = "/Report/ReportSummaryInvoice/SearchFullText"
API_CHECKIN = "/Report/ReportEmployeeCheckin/SearchElastic"

# -------------------- Vera / Google --------------------
# The workbook still hosts non-employee operational/audit worksheets.  Sheet1
# employee reads are retired; employee identity comes from PostgreSQL below.
SHEET_MAT_KHAU_ID = "1DGXy3kPyMPwtz-3CnG8i6BiQbXFDApasoXVFzSmUe24"
SHEET_DU_PHONG_ID = "1Kz0aw-JatptAN9G7YSwZ6rJO09urOPaD-rS-18eZSY0"
BANG_TOUR_FILE_ID = "151d1ueCwH2KXX-HPQF1uj340uWSCS2dW"

AUTO_PENALTY_CONFIG_WORKSHEET = "CauHinhAutoPhat"
AUTO_PENALTY_CONFIG_HEADERS = [
    "Key", "Trạng thái", "Ngưỡng phút", "Ngày cập nhật", "Giờ cập nhật", "Người cập nhật"
]
AUTO_PENALTY_CONFIG_KEY = "AUTO_PENALTY"
AUTO_PENALTY_RUNNING = "RUNNING"
AUTO_PENALTY_PAUSED = "PAUSED"
AUTO_PENALTY_MINUTES = 5

# V93.3 - Sheet1 lịch nghỉ: A:M theo HEADER thực tế; không ép vị trí cột.
LEAVE_SHEET_RANGE = "A:M"
LEAVE_HEADER_RANGE = "A1:M1"
LEAVE_DATA_COLUMNS = [
    "Ngày", "Thứ ngày", "Tên nhân viên", "Lý do nghỉ", "Loại nghỉ",
    "Chi tiết", "Số ngày tính", "Số ngày phép cộng dồn", "Phạt vi phạm",
    "Ngày cập nhật", "Giờ cập nhật", "Người cập nhật",
]
LEAVE_REQUIRED_FIELDS = {"Ngày", "Tên nhân viên", "Lý do nghỉ"}
LEAVE_HEADER_ALIASES = {
    "ngay": "Ngày",
    "thu ngay": "Thứ ngày",
    "thu": "Thứ ngày",
    "ten nhan vien": "Tên nhân viên",
    "nhan vien": "Tên nhân viên",
    "ly do nghi": "Lý do nghỉ",
    "loai nghi": "Loại nghỉ",
    "chi tiet": "Chi tiết",
    "so ngay tinh": "Số ngày tính",
    "so ngay phep cong don": "Số ngày phép cộng dồn",
    "so ngay cong don": "Số ngày phép cộng dồn",
    "phat vi pham": "Phạt vi phạm",
    "tien phat": "Phạt vi phạm",
    "ngay cap nhat": "Ngày cập nhật",
    "gio cap nhat": "Giờ cập nhật",
    "nguoi cap nhat": "Người cập nhật",
}

PROGRESSIVE_REASONS = {
    "nghi khong phep": "Nghỉ không phép",
    "di tre khong phep": "Đi trễ không phép",
    "ve som khong phep": "Về sớm không phép",
    "ra som khong phep": "Về sớm không phép",
}

OUTSIDE_LATE_EXCLUDED = {
    "ra ngoai vao muon duoi 30 phut",
    "ra ngoai vao muon duoi 60 phut",
    "ra ngoai vao muon duoi 120 phut",
    "ra ngoai vao muon tu 120 phut tro len",
    "ra ngoai vao muon tren 120 phut",
}


def _log(msg: str) -> None:
    now = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now} +07] {msg}", flush=True)


def _strip_accents(value) -> str:
    text0 = str(value or "")
    text0 = unicodedata.normalize("NFD", text0)
    text0 = "".join(ch for ch in text0 if unicodedata.category(ch) != "Mn")
    return text0.replace("đ", "d").replace("Đ", "D")


def _norm(value) -> str:
    return " ".join(_strip_accents(value).casefold().strip().split())


def _clean_employee_name(value) -> str:
    text0 = " ".join(str(value or "").strip().split())
    text0 = re.sub(r"\s*\*+\s*$", "", text0).strip()
    return " ".join(text0.split())


def _employee_key(value) -> str:
    return _norm(_clean_employee_name(value))


def _clean_reason(value) -> str:
    return " ".join(str(value or "").replace("🔴", "").strip().split())


def _reason_key(value) -> str:
    return _norm(_clean_reason(value))


def _date_key(value) -> str:
    d = _parse_date(value)
    return d.strftime("%d/%m/%Y") if d else ""


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text0 = str(value).strip()
    if not text0 or text0.casefold() in {"nan", "nat", "none"}:
        return None
    try:
        parsed = pd.to_datetime(text0, dayfirst=True, errors="coerce")
        if pd.notna(parsed):
            return parsed.date()
    except Exception:
        pass
    return None


def _number(value, default=0.0, money=False) -> float:
    try:
        if value is None or pd.isna(value):
            return float(default)
    except Exception:
        pass
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return float(value)
        except Exception:
            return float(default)
    text0 = str(value).strip()
    if not text0 or text0.casefold() in {"nan", "none", "nat", "-"}:
        return float(default)
    try:
        if money:
            text0 = (text0.replace(".", "").replace(",", "").replace(" ", "")
                     .replace("đ", "").replace("Đ", "").replace("VNĐ", "").replace("VND", ""))
        else:
            text0 = text0.replace(",", ".")
        return float(text0)
    except Exception:
        return float(default)


# ==========================================================
# GOOGLE AUTH / SHEETS
# ==========================================================
def get_gspread_client() -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds, _ = google_auth_default(scopes=scopes)
    return gspread.authorize(creds)


def _worksheet_or_create(ss, title: str, rows=20, cols=8):
    try:
        return ss.worksheet(title)
    except Exception:
        return ss.add_worksheet(title=title, rows=rows, cols=cols)


def load_auto_penalty_config(client: gspread.Client) -> dict:
    default_cfg = {
        "paused": False,
        "status": AUTO_PENALTY_RUNNING,
        "threshold_minutes": AUTO_PENALTY_MINUTES,
    }
    ss = client.open_by_key(SHEET_DU_PHONG_ID)
    ws = _worksheet_or_create(ss, AUTO_PENALTY_CONFIG_WORKSHEET, rows=20, cols=8)
    vals = ws.get("A1:F2")
    header = vals[0] if vals else []
    if list(header[:6]) != AUTO_PENALTY_CONFIG_HEADERS:
        ws.update(range_name="A1:F1", values=[AUTO_PENALTY_CONFIG_HEADERS], value_input_option="USER_ENTERED")
    row = vals[1] if len(vals) > 1 else []
    if not row or str(row[0]).strip() != AUTO_PENALTY_CONFIG_KEY:
        now = datetime.now(VN_TZ)
        row = [
            AUTO_PENALTY_CONFIG_KEY, AUTO_PENALTY_RUNNING, AUTO_PENALTY_MINUTES,
            now.strftime("%d/%m/%Y"), now.strftime("%H:%M:%S"), "Hệ thống",
        ]
        ws.update(range_name="A2:F2", values=[row], value_input_option="USER_ENTERED")
    row = list(row) + [""] * max(0, 6 - len(row))
    status = str(row[1] or AUTO_PENALTY_RUNNING).strip().upper()
    try:
        threshold = int(float(row[2] or AUTO_PENALTY_MINUTES))
    except Exception:
        threshold = AUTO_PENALTY_MINUTES
    threshold = max(AUTO_PENALTY_MINUTES, threshold)
    return {
        "paused": status == AUTO_PENALTY_PAUSED,
        "status": status,
        "threshold_minutes": threshold,
    }


def _weekday_vi(d: date | None) -> str:
    if not isinstance(d, date):
        return ""
    return {
        0: "Thứ Hai",
        1: "Thứ Ba",
        2: "Thứ Tư",
        3: "Thứ Năm",
        4: "Thứ Sáu",
        5: "Thứ Bảy",
        6: "Chủ Nhật",
    }.get(d.weekday(), "")


def _canonical_leave_field_for_header(header) -> str:
    raw = str(header or "").strip()
    if not raw:
        return ""
    return LEAVE_HEADER_ALIASES.get(_norm(raw), raw)


def _get_leave_headers(ws, strict=True) -> list[str]:
    values = ws.get(LEAVE_HEADER_RANGE)
    headers = list(values[0]) if values else []
    headers = headers[:13] + [""] * max(0, 13 - len(headers))
    if strict:
        mapped = {
            _canonical_leave_field_for_header(h)
            for h in headers
            if str(h or "").strip()
        }
        missing = sorted(LEAVE_REQUIRED_FIELDS - mapped)
        if missing:
            raise RuntimeError("Sheet1 A:M thiếu header bắt buộc: " + ", ".join(missing))
    return headers


def _sheet_row_to_record(row, headers) -> dict:
    vals = list(row[:13]) + [""] * max(0, 13 - len(row))
    out = {}
    for i, header in enumerate(headers[:13]):
        field = _canonical_leave_field_for_header(header)
        if field:
            out[field] = vals[i]
    for field in LEAVE_DATA_COLUMNS:
        out.setdefault(field, "")
    return out


def _record_to_sheet_row(record, headers, existing_values=None) -> list:
    vals = [""] * 13 if existing_values is None else (
        list(existing_values[:13]) + [""] * max(0, 13 - len(existing_values))
    )
    for i, header in enumerate(headers[:13]):
        field = _canonical_leave_field_for_header(header)
        if not field:
            continue
        if field in record:
            vals[i] = record.get(field, "")
        elif str(header).strip() in record:
            vals[i] = record.get(str(header).strip(), "")
    return vals


def _sheet_rows_a_to_m(ws) -> list[dict]:
    headers = _get_leave_headers(ws, strict=True)
    values = ws.get(LEAVE_SHEET_RANGE)
    if not values or len(values) < 2:
        return []
    rows = []
    for sheet_row, row in enumerate(values[1:], start=2):
        vals = list(row[:13]) + [""] * max(0, 13 - len(row))
        if not any(str(v).strip() for v in vals):
            continue
        item = _sheet_row_to_record(vals, headers)
        item["__row"] = sheet_row
        item["__source"] = SHEET_DU_PHONG_ID
        item["__raw_values"] = vals
        rows.append(item)
    return rows


def _ensure_leave_header(ws) -> list[str]:
    """Chỉ validate A1:M1; không tự sửa header."""
    return _get_leave_headers(ws, strict=True)

def _next_data_row(ws) -> int:
    values = ws.get(LEAVE_SHEET_RANGE)
    last = 0
    for idx, row in enumerate(values, start=1):
        vals = list(row[:13]) + [""] * max(0, 13 - len(row))
        if any(str(v).strip() for v in vals):
            last = idx
    return max(2, last + 1)


def load_all_leave_rows(client: gspread.Client) -> list[dict]:
    """V93.3: chỉ đọc Sheet1 của SHEET_DU_PHONG_ID; không còn nguồn lịch thứ hai."""
    try:
        ws = client.open_by_key(SHEET_DU_PHONG_ID).get_worksheet(0)
        rows = _sheet_rows_a_to_m(ws)
    except Exception as exc:
        _log(f"WARN: không đọc được Sheet1 lịch nghỉ chính: {type(exc).__name__}: {exc}")
        return []

    logical: dict[tuple[str, str, str], dict] = {}
    for item in rows:
        key = (
            _date_key(item.get("Ngày")),
            _employee_key(item.get("Tên nhân viên")),
            _reason_key(item.get("Lý do nghỉ")),
        )
        if all(key):
            logical[key] = item
    return list(logical.values())


def load_employee_name_map() -> dict[str, str]:
    """Load canonical employee names from PostgreSQL, never credential Sheet1."""
    with vpg.get_engine().connect() as conn:
        values = conn.execute(text("""
            SELECT username
            FROM employees
            WHERE btrim(COALESCE(username, '')) <> ''
              AND COALESCE(payload->>'__deleted', 'false') <> 'true'
            ORDER BY COALESCE(stt, 2147483647), username
        """)).scalars().all()
    out: dict[str, str] = {}
    for value in values:
        name = str(value or "").strip()
        key = _employee_key(name)
        if key and key not in out:
            out[key] = name
    return out


def canonical_employee(raw_name, employee_map: dict[str, str]) -> str:
    key = _employee_key(raw_name)
    if not key:
        return ""
    return str(employee_map.get(key, "")).strip()


def load_leave_catalog(client: gspread.Client) -> dict[str, dict]:
    ws = client.open_by_key(SHEET_DU_PHONG_ID).worksheet("LoaiNghi")
    rows = ws.get_all_values()
    catalog: dict[str, dict] = {}
    if len(rows) < 2:
        return catalog
    for row in rows[1:]:
        vals = list(row)
        name = str(vals[1]).strip() if len(vals) > 1 else ""
        if not name or _norm(name) in {"loai nghi", "ly do nghi", "nan", "none"}:
            continue
        clean = _clean_reason(name)
        catalog[_reason_key(clean)] = {
            "name": clean,
            "type": str(vals[2] if len(vals) > 2 else "").strip(),
            "days": _number(vals[4] if len(vals) > 4 else 0, 0.0),
            "penalty": _number(vals[5] if len(vals) > 5 else 0, 0.0, money=True),
        }
    return catalog


def _catalog_item(catalog: dict[str, dict], wanted: str) -> dict | None:
    exact = catalog.get(_reason_key(wanted))
    if exact:
        return exact
    target = _norm(wanted)
    for item in catalog.values():
        if _norm(item.get("name", "")) == target:
            return item
    return None


def _outside_reason(minutes: float, catalog: dict[str, dict]) -> dict | None:
    m = float(minutes)
    if m < 30:
        candidates = ["Ra ngoài vào muộn dưới 30 phút"]
    elif m < 60:
        candidates = ["Ra ngoài vào muộn dưới 60 phút"]
    elif m < 120:
        candidates = ["Ra ngoài vào muộn dưới 120 phút"]
    else:
        candidates = [
            "Ra ngoài vào muộn từ 120 phút trở lên",
            "Ra ngoài vào muộn trên 120 phút",
            "Ra ngoài vào muộn dưới 120 phút",
        ]
    for name in candidates:
        item = _catalog_item(catalog, name)
        if item:
            return item
    return None


def _progressive_canonical(reason: str) -> str | None:
    key = _norm(reason)
    if key in OUTSIDE_LATE_EXCLUDED:
        return None
    return PROGRESSIVE_REASONS.get(key)


def _same_leave_exists(rows: list[dict], d: date, employee: str, reason: str) -> bool:
    key = (d.strftime("%d/%m/%Y"), _employee_key(employee), _reason_key(reason))
    for r in rows:
        rkey = (_date_key(r.get("Ngày")), _employee_key(r.get("Tên nhân viên")), _reason_key(r.get("Lý do nghỉ")))
        if rkey == key:
            return True
    return False


def _monthly_accumulated_days(rows: list[dict], d: date, employee: str, new_days: float) -> float:
    total = 0.0
    emp_key = _employee_key(employee)
    for r in rows:
        rd = _parse_date(r.get("Ngày"))
        if not rd or rd.year != d.year or rd.month != d.month:
            continue
        if _employee_key(r.get("Tên nhân viên")) != emp_key:
            continue
        total += _number(r.get("Số ngày tính"), 0.0)
    return total + float(new_days)


def _progressive_ordinal(rows: list[dict], d: date, reason: str) -> int:
    canonical = _progressive_canonical(reason)
    if not canonical:
        return 1
    count = 0
    for r in rows:
        rd = _parse_date(r.get("Ngày"))
        if rd != d:
            continue
        if _progressive_canonical(_clean_reason(r.get("Lý do nghỉ", ""))) == canonical:
            count += 1
    return count + 1


def save_auto_violation(
    client: gspread.Client,
    d: date,
    employee: str,
    reason_item: dict,
    detail: str,
    actor: str,
) -> tuple[bool, str]:
    reason = _clean_reason(reason_item.get("name", ""))
    leave_type = str(reason_item.get("type", "") or "").strip()
    days = float(reason_item.get("days", 0) or 0)
    base_penalty = float(reason_item.get("penalty", 0) or 0)
    if not employee or not reason:
        return False, "Thiếu nhân viên hoặc lý do."

    primary_ws = client.open_by_key(SHEET_DU_PHONG_ID).get_worksheet(0)
    headers = _ensure_leave_header(primary_ws)

    live_rows = load_all_leave_rows(client)
    if _same_leave_exists(live_rows, d, employee, reason):
        return True, "SKIP_DUPLICATE"

    accumulated = _monthly_accumulated_days(live_rows, d, employee, days)
    penalty = base_penalty
    canonical = _progressive_canonical(reason)
    if canonical:
        ordinal = _progressive_ordinal(live_rows, d, reason)
        penalty += max(0, ordinal - 2) * 100000
        prefix = f"Người Thứ {ordinal} {canonical.lower()}"
        detail = f"{prefix} | {detail}" if detail else prefix

    now = datetime.now(VN_TZ)
    record = {
        "Ngày": d.strftime("%d/%m/%Y"),
        "Thứ ngày": _weekday_vi(d),
        "Tên nhân viên": employee,
        "Lý do nghỉ": reason,
        "Loại nghỉ": leave_type,
        "Chi tiết": str(detail or "").strip(),
        "Số ngày tính": days,
        "Số ngày phép cộng dồn": accumulated,
        "Phạt vi phạm": penalty,
        "Ngày cập nhật": now.strftime("%d/%m/%Y"),
        "Giờ cập nhật": now.strftime("%H:%M:%S"),
        "Người cập nhật": actor,
    }
    row = _record_to_sheet_row(record, headers)
    target = _next_data_row(primary_ws)
    primary_ws.update(
        range_name=f"A{target}:M{target}",
        values=[row],
        value_input_option="USER_ENTERED",
    )
    return True, f"ADDED_ROW_{target}"


# ==========================================================
# BẢNG TOUR
# ==========================================================
def _download_bang_tour_bytes() -> bytes:
    # Link usercontent thường trả thẳng binary cho file public/được chia sẻ.
    urls = [
        f"https://drive.usercontent.google.com/download?id={BANG_TOUR_FILE_ID}&export=download&confirm=t",
        f"https://drive.google.com/uc?export=download&id={BANG_TOUR_FILE_ID}&confirm=t",
    ]
    errors = []
    for url in urls:
        try:
            r = requests.get(url, timeout=90, allow_redirects=True)
            r.raise_for_status()
            content = r.content
            if content[:2] == b"PK" and len(content) > 1000:
                return content
            # Google đôi khi trả HTML confirmation; thử lấy confirm token/link.
            text0 = content[:200000].decode("utf-8", errors="ignore")
            m = re.search(r'href="([^"]*download[^"]*)"', text0, flags=re.I)
            if m:
                href = m.group(1).replace("&amp;", "&")
                if href.startswith("/"):
                    href = "https://drive.google.com" + href
                rr = requests.get(href, timeout=90, allow_redirects=True)
                rr.raise_for_status()
                if rr.content[:2] == b"PK" and len(rr.content) > 1000:
                    return rr.content
            errors.append("Google Drive trả HTML thay vì XLSM")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    raise RuntimeError("Không tải được Bảng tour: " + " | ".join(errors[-2:]))


def load_bang_tour_input() -> pd.DataFrame:
    content = _download_bang_tour_bytes()
    bio = io.BytesIO(content)
    if not zipfile.is_zipfile(bio):
        raise RuntimeError("Bảng tour tải về không phải file XLSM hợp lệ.")
    bio.seek(0)
    raw = pd.read_excel(bio, sheet_name="Input", header=None, engine="openpyxl")
    if raw.empty:
        return pd.DataFrame()
    header_idx = 19 if len(raw) > 19 else 0
    max_cols = min(24, raw.shape[1])
    raw = raw.iloc[:, :max_cols]
    header_vals = raw.iloc[header_idx].tolist()
    headers = []
    seen = {}
    for i, v in enumerate(header_vals):
        text0 = "" if pd.isna(v) else str(v).strip()
        if not text0 or text0.casefold() == "nan":
            text0 = f"COL_{i+1}"
        if text0 in seen:
            seen[text0] += 1
            text0 = f"{text0}_{i+1}"
        else:
            seen[text0] = 1
        headers.append(text0)
    df = raw.iloc[header_idx + 1:].copy()
    df.columns = headers
    return df.dropna(how="all").reset_index(drop=True)


def _find_col(df: pd.DataFrame, wanted: str):
    target = _norm(wanted)
    exact = []
    contains = []
    for c in df.columns:
        normc = _norm(c)
        if normc == target:
            exact.append(c)
        elif target in normc:
            contains.append(c)
    return exact[0] if exact else (contains[0] if contains else None)


def _tour_late_minutes(value) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, timedelta):
        return max(0.0, value.total_seconds() / 60.0)
    try:
        if isinstance(value, pd.Timedelta):
            return max(0.0, value.total_seconds() / 60.0)
    except Exception:
        pass
    if hasattr(value, "hour") and hasattr(value, "minute") and not isinstance(value, (int, float)):
        try:
            return max(0.0, float(value.hour * 60 + value.minute + getattr(value, "second", 0) / 60.0))
        except Exception:
            pass
    # Trong file Tour hiện tại Vào trễ thường là số phút. Nếu là serial thời gian Excel < 1,
    # chuyển sang phút (1 ngày = 1440 phút).
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = float(value)
        if 0 < n < 1:
            return max(0.0, n * 1440.0)
        return max(0.0, n)
    text0 = str(value).strip()
    if not text0 or text0.casefold() in {"nan", "none", "nat"}:
        return None
    m = re.search(r"(-?\d+(?:[\.,]\d+)?)\s*(?:phút|phut|min|mins|minute|minutes)?", text0, flags=re.I)
    if m and ":" not in text0:
        try:
            return max(0.0, float(m.group(1).replace(",", ".")))
        except Exception:
            pass
    tm = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text0)
    if tm:
        h, mi, sec = int(tm.group(1)), int(tm.group(2)), int(tm.group(3) or 0)
        return max(0.0, h * 60 + mi + sec / 60.0)
    return None


def process_tour_penalties(engine, cfg: dict, employee_map: dict, catalog: dict) -> dict:
    result = {"eligible": 0, "added": 0, "skipped": 0, "errors": 0}
    try:
        df = load_bang_tour_input()
    except Exception as exc:
        _log(f"AUTO TOUR ERROR: {type(exc).__name__}: {exc}")
        result["errors"] += 1
        return result
    if df.empty:
        return result
    name_col = (
        _find_col(df, "Tên nhân viên")
        or _find_col(df, "Tên Nhân Viên")
        or _find_col(df, "Nhân viên")
        or _find_col(df, "NV")
    )
    late_col = _find_col(df, "Vào trễ")
    out_col = _find_col(df, "Giờ ra")
    in_col = _find_col(df, "Giờ vào")
    if name_col is None or late_col is None:
        _log(f"AUTO TOUR ERROR: thiếu cột Tên nhân viên hoặc Vào trễ. columns={list(df.columns)}")
        result["errors"] += 1
        return result
    threshold = max(AUTO_PENALTY_MINUTES, int(cfg.get("threshold_minutes", AUTO_PENALTY_MINUTES)))
    today = datetime.now(VN_TZ).date()
    for _, row in df.iterrows():
        minutes = _tour_late_minutes(row.get(late_col, ""))
        if minutes is None or minutes < threshold:
            continue
        result["eligible"] += 1
        raw_name = row.get(name_col, "")
        employee = canonical_employee(raw_name, employee_map)
        if not employee:
            _log(f"AUTO TOUR SKIP: không khớp nhân viên '{raw_name}'")
            result["skipped"] += 1
            continue
        reason_item = _outside_reason(minutes, catalog)
        if not reason_item:
            _log(f"AUTO TOUR ERROR: chưa có loại phù hợp trong LoaiNghi cho {minutes:.0f} phút")
            result["errors"] += 1
            continue
        detail_parts = [f"Auto Update Bảng tour · vào muộn {int(round(minutes))} phút"]
        if out_col is not None and str(row.get(out_col, "")).strip():
            detail_parts.append(f"Giờ ra {str(row.get(out_col)).strip()}")
        if in_col is not None and str(row.get(in_col, "")).strip():
            detail_parts.append(f"Giờ vào {str(row.get(in_col)).strip()}")
        with engine.begin() as conn:
            ok, msg = auto_check.save_violation(
                conn, work_date=today, employee=employee, reason_item=reason_item,
                detail=" · ".join(detail_parts), source="AUTO UPDATE 24/7 - BẢNG TOUR", minutes=minutes,
            )
        if ok and msg == "SKIP_DUPLICATE":
            result["skipped"] += 1
        elif ok:
            result["added"] += 1
            _log(f"AUTO TOUR ADDED: {employee} · {reason_item['name']} · {minutes:.0f} phút")
        else:
            result["errors"] += 1
            _log(f"AUTO TOUR ERROR: {employee}: {msg}")
    return result


# ==========================================================
# TIMESOFT LOGIN + API
# ==========================================================
def _date_range_text(start_date: date, end_date: date) -> str:
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"


def _visible_input(page, selectors):
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 12)):
                node = loc.nth(i)
                if node.is_visible():
                    return node
        except Exception:
            continue
    return None


def _login_error_text(page) -> str:
    selectors = [
        ".validation-summary-errors", ".field-validation-error", ".alert-danger",
        ".alert-warning", ".error", ".error-message", ".text-danger", "[role=\"alert\"]",
        ".toast-message", ".notifyjs-bootstrap-error",
    ]
    messages = []
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 8)):
                node = loc.nth(i)
                if not node.is_visible():
                    continue
                txt = re.sub(r"\s+", " ", str(node.inner_text() or "")).strip()
                if txt and txt not in messages:
                    messages.append(txt[:200])
        except Exception:
            continue
    return " | ".join(messages[:3])


def _login_with_playwright(page, verify_url: str) -> tuple[bool, str]:
    password_box = _visible_input(page, [
        'input[type="password"]', 'input[name*="password" i]', 'input[id*="password" i]',
        'input[name*="pass" i]', 'input[id*="pass" i]',
    ])
    if password_box is None:
        return True, "session-existing"
    username_box = _visible_input(page, [
        'input[name="UserName"]', 'input[name="Username"]', 'input[name*="username" i]',
        'input[id*="username" i]', 'input[name*="user" i]', 'input[id*="user" i]',
        'input[name*="account" i]', 'input[id*="account" i]', 'input[name*="login" i]',
        'input[id*="login" i]', 'input[type="email"]', 'input[type="text"]',
    ])
    if username_box is None:
        return False, "Không nhận diện được ô tài khoản TimeSoft."
    try:
        username_box.click()
        username_box.fill(USERNAME)
        password_box.click()
        password_box.fill(PASSWORD)
        try:
            password_box.press("Tab")
        except Exception:
            pass
        page.wait_for_timeout(250)
    except Exception as exc:
        return False, f"Không nhập được form TimeSoft: {type(exc).__name__}"
    submit = None
    for selector in [
        'button[type="submit"]', 'input[type="submit"]',
        'input[type="button"][value*="đăng" i]', 'input[type="button"][value*="login" i]',
        'button:has-text("Đăng nhập")', 'button:has-text("Đăng Nhập")', 'button:has-text("Login")',
        'a:has-text("Đăng nhập")', 'a:has-text("Đăng Nhập")', '[onclick*="login" i]', '[id*="login" i]',
    ]:
        try:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 10)):
                node = loc.nth(i)
                if node.is_visible() and node.is_enabled():
                    submit = node
                    break
            if submit is not None:
                break
        except Exception:
            continue
    try:
        if submit is not None:
            submit.click(timeout=8000)
        else:
            password_box.press("Enter")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        page.goto(verify_url, wait_until="domcontentloaded", timeout=35000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(700)
    except Exception as exc:
        return False, f"Không xác minh được session TimeSoft: {type(exc).__name__}"
    final_url = str(page.url or "")
    still_password = _visible_input(page, ['input[type="password"]', 'input[name*="password" i]'])
    if "/user/login" in final_url.lower() and still_password is not None:
        err = _login_error_text(page)
        return False, "Đăng nhập TimeSoft thất bại" + (f": {err}" if err else ".")
    return True, "login-ok"


def _requests_session_from_browser(cookies, user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.7",
        "User-Agent": str(user_agent or "Mozilla/5.0"),
    })
    for cookie in cookies or []:
        name = str(cookie.get("name", "") or "")
        value = str(cookie.get("value", "") or "")
        if not name:
            continue
        kwargs = {}
        domain = str(cookie.get("domain", "") or "").strip()
        path = str(cookie.get("path", "") or "/").strip() or "/"
        if domain:
            kwargs["domain"] = domain
        if path:
            kwargs["path"] = path
        try:
            session.cookies.set(name, value, **kwargs)
        except Exception:
            session.cookies.set(name, value)
    return session


def create_authenticated_session() -> requests.Session:
    if not USERNAME or not PASSWORD:
        raise RuntimeError("Thiếu TIMESOFT_USERNAME/TIMESOFT_PASSWORD trong Secret Manager.")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Image chưa cài Playwright/Chromium.") from exc
    verify_url = urljoin(BASE_URL + "/", REPORT_SUMMARY_PAGE.lstrip("/"))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        try:
            context = browser.new_context(ignore_https_errors=False, viewport={"width": 1440, "height": 1000}, locale="vi-VN")
            page = context.new_page()
            page.goto(verify_url, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(500)
            ok, msg = _login_with_playwright(page, verify_url)
            if not ok:
                raise RuntimeError(msg)
            cookies = context.cookies()
            try:
                user_agent = str(page.evaluate("navigator.userAgent") or "Mozilla/5.0")
            except Exception:
                user_agent = "Mozilla/5.0"
        finally:
            try:
                context.close()
            except Exception:
                pass
            browser.close()
    return _requests_session_from_browser(cookies, user_agent)


def post_json(session: requests.Session, api_path: str, referer_path: str, payload: dict, timeout: int = 60) -> dict:
    url = urljoin(BASE_URL + "/", api_path.lstrip("/"))
    referer = urljoin(BASE_URL + "/", referer_path.lstrip("/"))
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": referer,
        "Origin": BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = session.post(url, json=payload, headers=headers, timeout=timeout, allow_redirects=True)
    if resp.status_code in {401, 403} or "/user/login" in str(resp.url or "").lower():
        raise RuntimeError("Phiên TimeSoft hết hạn trong lúc gọi API.")
    resp.raise_for_status()
    ctype = str(resp.headers.get("content-type", "") or "").lower()
    if "json" not in ctype:
        raise RuntimeError("TimeSoft API không trả JSON.")
    data = resp.json()
    code = str((data or {}).get("ReturnCode", "") or "")
    if code and code != "000000":
        raise RuntimeError(f"TimeSoft ReturnCode={code}: {(data or {}).get('Message', '')}")
    return data or {}


def fetch_summary(session: requests.Session, target_date: date) -> tuple[pd.DataFrame, dict]:
    payload = {
        "objectSearch": {
            "TypeData": 0,
            "TypeInvoice": 1,
            "TachInvoiceSpa": 0,
            "CreateTimeRange": _date_range_text(target_date, target_date),
        },
        "pageSize": 0,
    }
    data = post_json(session, API_SUMMARY, REPORT_SUMMARY_PAGE, payload)
    rows = data.get("Data") or []
    df = pd.json_normalize(rows, sep=".") if isinstance(rows, list) and rows else pd.DataFrame()
    meta_keys = [
        "Total", "TotalMoney", "TotalDiscount", "TotalQuantity", "TotalInvoice",
        "TotalActualRevenu", "TotalPromotion", "TotalPayment", "TotalActualTerm",
        "TotalDebt", "ReportByYear", "Message",
    ]
    meta = {k: data.get(k) for k in meta_keys if k in data}
    return df, meta


def fetch_checkin(session: requests.Session, target_date: date) -> tuple[pd.DataFrame, dict]:
    all_rows = []
    total_expected = None
    for page_index in range(1, MAX_CHECKIN_PAGES + 1):
        payload = {
            "objectSearch": {"CreateDateRange": _date_range_text(target_date, target_date)},
            "pageIndex": page_index,
            "pageSize": CHECKIN_PAGE_SIZE,
        }
        data = post_json(session, API_CHECKIN, REPORT_CHECKIN_PAGE, payload)
        if total_expected is None:
            try:
                total_expected = int(data.get("Total") or 0)
            except Exception:
                total_expected = 0
        page_rows = data.get("Data") or []
        if not isinstance(page_rows, list) or not page_rows:
            break
        all_rows.extend(page_rows)
        if total_expected and len(all_rows) >= total_expected:
            break
    df = pd.json_normalize(all_rows, sep=".") if all_rows else pd.DataFrame()
    return df, {"Total": total_expected if total_expected is not None else len(all_rows)}


def _timesoft_row_value(row, candidates):
    for c in candidates:
        if c in row.index:
            value = row.get(c)
            if value is not None and str(value).strip().casefold() not in {"", "nan", "none", "nat"}:
                return value
    return ""


def _time_minutes(value) -> float | None:
    text0 = str(value or "").strip()
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text0)
    if not m:
        return None
    h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return h * 60 + mi + sec / 60.0


def _parse_minutes_late(row) -> float | None:
    direct = _timesoft_row_value(row, [
        "TotalMinuteInGoLate", "TotalMinuteGoLate", "MinuteInGoLate", "GoLateMinute", "LateMinute"
    ])
    try:
        if str(direct).strip() != "":
            return max(0.0, float(str(direct).replace(",", ".").strip()))
    except Exception:
        pass
    start = _timesoft_row_value(row, ["StartWorkTime", "WorkTimeStart", "ShiftStartTime"])
    checkin = _timesoft_row_value(row, ["MachineTimeCheckInStr", "CheckInTimeStr", "CheckInTime"])
    sm = _time_minutes(start)
    cm = _time_minutes(checkin)
    if sm is None or cm is None:
        return None
    diff = cm - sm
    if diff < -12 * 60:
        diff += 24 * 60
    return max(0.0, float(diff))


def _confirmed_break_return_records(engine, work_date: date) -> list[dict]:
    """Build today's break facts from the same FaceID rules used by Web V2."""
    import vera_web_v2_attendance_break_window as break_window
    import vera_web_v2_attendance_v42 as attendance
    import vera_web_v2_support_shift_break as support_shift

    original_cluster = attendance._cluster_punches
    original_picker = attendance._pick_break_pair
    original_break = attendance._break_from_punches

    def cluster_in_five_minutes(values, _minutes=break_window.FACEID_GROUP_MINUTES):
        return original_cluster(values, break_window.FACEID_GROUP_MINUTES)

    def break_with_current_window(punches, *, work_day, representative, cfg):
        return break_window._enhance_break_payload(
            original_break,
            punches,
            work_day=work_day,
            representative=representative,
            cfg=cfg,
        )

    # _records_v42 resolves these functions at runtime. Temporarily install the
    # production five-minute grouping/window rules while this background worker
    # reconstructs confirmed break pairs from the just-written snapshot.
    attendance._cluster_punches = cluster_in_five_minutes
    attendance._pick_break_pair = break_window._pick_break_pair
    attendance._break_from_punches = break_with_current_window
    try:
        with engine.connect() as conn:
            records = attendance._records_v42(conn, work_date, work_date)
            support_map = support_shift._support_map(conn, work_date, work_date)
            leave_rows = conn.execute(text("""
                SELECT employee_name, leave_reason
                FROM leave_records
                WHERE leave_date=:work_date
            """), {"work_date": work_date}).mappings().all()
    finally:
        attendance._cluster_punches = original_cluster
        attendance._pick_break_pair = original_picker
        attendance._break_from_punches = original_break

    restricted: dict[str, list[str]] = {}
    for row in leave_rows:
        reason = str(row.get("leave_reason") or "").strip()
        reason_key = _reason_key(reason)
        if reason_key in support_shift.SUPPORT_ALLOWANCES:
            continue
        if not any(token in reason_key for token in ("di tre", "ve som", "ra som")):
            continue
        employee_key = _employee_key(row.get("employee_name"))
        if employee_key:
            restricted.setdefault(employee_key, []).append(reason)

    for item in records:
        employee_key = _employee_key(item.get("employee_name"))
        support = support_map.get((work_date.strftime("%d/%m/%Y"), support_shift._norm(item.get("employee_name"))))
        if support:
            allowance, reason = support
            item["support_shift_reason"] = reason
            item["support_shift_allowance_minutes"] = allowance
            item["support_break_allowed"] = True
            support_shift._remove_late_restriction(item)
        restriction_reasons = list(dict.fromkeys(restricted.get(employee_key, [])))
        if restriction_reasons:
            item["break_restricted_reason"] = " / ".join(restriction_reasons)
    return records


def process_break_return_penalties(engine, catalog: dict) -> dict:
    """Write confirmed mid-shift late-return penalties during TimeSoft sync."""
    from vera_web_v2_break_return_penalty import confirmed_break_return_fact

    result = {"eligible": 0, "added": 0, "skipped": 0, "errors": 0}
    today = datetime.now(VN_TZ).date()
    try:
        records = _confirmed_break_return_records(engine, today)
    except Exception as exc:
        result["errors"] += 1
        _log(f"DIRECT BREAK RETURN ERROR: không dựng được dữ liệu nghỉ giữa ca: {type(exc).__name__}: {exc}")
        return result

    for item in records:
        fact = confirmed_break_return_fact(item, today)
        if fact is None:
            continue
        result["eligible"] += 1
        late_minutes = int(fact["late_minutes"])
        reason_item = auto_check.outside_reason(catalog, late_minutes)
        if not reason_item:
            result["errors"] += 1
            _log(f"DIRECT BREAK RETURN ERROR: Nội quy thiếu mức Ra ngoài vào muộn cho {late_minutes} phút.")
            continue

        employee = str(fact["employee"] or "").strip()
        detail = (
            f"Đồng bộ TimeSoft trực tiếp · nghỉ giữa ca vào lại trễ {late_minutes} phút"
            f" · Giờ ra {fact['break_out'].strftime('%H:%M:%S')}"
            f" · Hạn vào lại {fact['deadline'].strftime('%H:%M:%S')}"
            f" · FaceID vào lại {fact['break_in'].strftime('%H:%M:%S')}"
        )
        try:
            with engine.begin() as conn:
                ok, message = auto_check.save_violation(
                    conn,
                    work_date=fact["work_day"],
                    employee=employee,
                    reason_item=reason_item,
                    detail=detail,
                    source="ĐỒNG BỘ TIMESOFT - NGHỈ GIỮA CA",
                    minutes=late_minutes,
                )
            if ok and message == "SKIP_DUPLICATE":
                result["skipped"] += 1
            elif ok:
                result["added"] += 1
                _log(
                    f"DIRECT BREAK RETURN ADDED: {employee} · {reason_item['name']} · "
                    f"{late_minutes} phút · {fact['work_day']}"
                )
            else:
                result["errors"] += 1
                _log(f"DIRECT BREAK RETURN ERROR: {employee}: {message}")
        except Exception as exc:
            result["errors"] += 1
            _log(f"DIRECT BREAK RETURN ERROR: {employee}: {type(exc).__name__}: {exc}")
    return result


def process_timesoft_penalties(
    engine,
    cfg: dict,
    employee_map: dict,
    catalog: dict,
    checkin_by_date: list[tuple[date, pd.DataFrame]],
) -> dict:
    result = {"eligible": 0, "added": 0, "skipped": 0, "errors": 0}
    reason_item = _catalog_item(catalog, "Đi trễ không phép")
    if not reason_item:
        _log("AUTO TIMESOFT ERROR: LoaiNghi chưa có 'Đi trễ không phép'.")
        result["errors"] += 1
        return result
    threshold = max(AUTO_PENALTY_MINUTES, int(cfg.get("threshold_minutes", AUTO_PENALTY_MINUTES)))
    today = datetime.now(VN_TZ).date()

    for target_date, df in checkin_by_date:
        # V84.1: Auto phạt chỉ xử lý dữ liệu của NGÀY HÔM NAY.
        # PostgreSQL vẫn được phép đồng bộ hôm nay + hôm qua theo SYNC_DAYS.
        if target_date != today:
            continue
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        for _, row in df.iterrows():
            raw_minutes = _parse_minutes_late(row)
            if raw_minutes is None or raw_minutes < threshold:
                continue
            raw_name = _timesoft_row_value(row, [
                "employeeInfo.Name", "EmployeeName", "employeeName", "Name", "FullName"
            ])
            employee = canonical_employee(raw_name, employee_map)
            if not employee:
                _log(f"AUTO TIMESOFT SKIP: không khớp nhân viên '{raw_name}'")
                result["skipped"] += 1
                continue
            raw_date = _timesoft_row_value(row, ["WorkDateStr", "WorkDate", "CreateDateStr", "CreateDate"])
            work_date = _parse_date(raw_date) or target_date
            checkin_time = _timesoft_row_value(row, ["MachineTimeCheckInStr", "CheckInTimeStr", "CheckInTime"])
            minutes = float(raw_minutes)
            registered_reasons: list[str] = []
            registered_reason = ""
            registered_covered = False
            registered_revoked = 0
            with engine.begin() as conn:
                registered_reasons, registered_baseline, registered_reason = auto_check.registered_late_for_day(
                    conn, work_date, employee,
                )
                if registered_reasons:
                    checkin_minutes = _time_minutes(checkin_time)
                    if checkin_minutes is None:
                        # The registration grants a later baseline. Without an
                        # authoritative check-in clock, never guess a violation.
                        registered_covered = True
                    else:
                        minutes = max(0.0, float(checkin_minutes) - float(registered_baseline))
                        registered_covered = minutes < threshold
                    if registered_covered:
                        registered_revoked = auto_check.revoke_auto_late_penalty(
                            conn,
                            work_date=work_date,
                            employee=employee,
                            basis=registered_reason,
                        )

                # A registered late baseline is already the applicable rule;
                # do not stack a separate support allowance on top of 17:00.
                if registered_reasons:
                    support_reasons, allowance, support_reason = [], 0, ""
                else:
                    support_reasons, allowance, support_reason = auto_check.late_support_for_day(
                        conn, work_date, employee,
                    )
                adjusted_minutes = supported_late_minutes(minutes, allowance) if support_reasons else float(minutes)
                covered = bool(support_reasons) and (
                    adjusted_minutes is None or adjusted_minutes < threshold
                )
                if covered:
                    revoked = auto_check.revoke_wrong_late_penalty(
                        conn, work_date=work_date, employee=employee, support_reason=support_reason,
                    )
                elif adjusted_minutes is not None:
                    penalty_minutes = adjusted_minutes
                else:
                    penalty_minutes = float(minutes)
            if registered_covered:
                result["skipped"] += 1
                checkin_text = str(checkin_time or "không xác định")
                _log(
                    f"AUTO TIMESOFT SKIP REGISTERED: {employee} · {registered_reason} · "
                    f"check-in {checkin_text} · chuẩn 17:00/{threshold} phút · revoked={registered_revoked}"
                )
                continue
            if covered:
                result["skipped"] += 1
                allowance_text = "không xác định (ưu tiên không phạt)" if allowance is None else f"{allowance} phút"
                adjusted_text = "không xác định" if adjusted_minutes is None else f"{adjusted_minutes:.0f} phút"
                _log(
                    f"AUTO TIMESOFT SKIP SUPPORT: {employee} · trễ gốc {minutes:.0f} phút · "
                    f"cho phép {allowance_text} · còn {adjusted_text}/{threshold} phút · revoked={revoked}"
                )
                continue
            result["eligible"] += 1
            shift_start = _timesoft_row_value(row, ["StartWorkTime", "WorkTimeStart", "ShiftStartTime"])
            detail = f"Đồng bộ TimeSoft trực tiếp · check-in muộn {int(round(minutes))} phút"
            if registered_reasons:
                detail += f" sau chuẩn 17:00 của {registered_reason}"
            if support_reasons and allowance is not None:
                detail += f" · Hỗ trợ cho phép {allowance} phút nhưng vượt {int(round(penalty_minutes))} phút"
            if shift_start:
                detail += f" · Ca bắt đầu {shift_start}"
            if checkin_time:
                detail += f" · Check-in {checkin_time}"
            with engine.begin() as conn:
                ok, msg = auto_check.save_violation(
                    conn, work_date=work_date, employee=employee, reason_item=reason_item,
                    detail=detail, source="ĐỒNG BỘ TIMESOFT - PHẠT TRỰC TIẾP", minutes=penalty_minutes,
                )
            if ok and msg == "SKIP_DUPLICATE":
                result["skipped"] += 1
            elif ok:
                result["added"] += 1
                _log(f"AUTO TIMESOFT ADDED: {employee} · {minutes:.0f} phút · {work_date}")
            else:
                result["errors"] += 1
                _log(f"AUTO TIMESOFT ERROR: {employee}: {msg}")
    return result


# ==========================================================
# POSTGRES SNAPSHOT
# ==========================================================
def _key(prefix: str, target_date: date) -> str:
    return f"{prefix}_{target_date.strftime('%Y%m%d')}"


def _missing_payroll_invoice_dates(conn, today: date) -> list[date]:
    """Return absent daily invoice snapshots, oldest first.

    ``dataset_key`` is the primary key of ``vera_dataset_cache``.  The bounded
    key range therefore uses the existing primary-key index and avoids scanning
    payload JSON.  An existing zero-row snapshot is complete and must not be
    treated as missing because a day can legitimately have no matching rows.
    """
    first_date = today - timedelta(days=PAYROLL_BACKFILL_DAYS - 1)
    first_key = _key("timesoft_summary_invoice", first_date)
    last_key = _key("timesoft_summary_invoice", today)
    existing = set(conn.execute(text("""
        SELECT dataset_key
        FROM vera_dataset_cache
        WHERE dataset_key BETWEEN :first_key AND :last_key
    """), {"first_key": first_key, "last_key": last_key}).scalars().all())
    return [
        first_date + timedelta(days=index)
        for index in range(PAYROLL_BACKFILL_DAYS)
        if _key("timesoft_summary_invoice", first_date + timedelta(days=index)) not in existing
    ]


def write_invoice_snapshot(target_date: date, invoice_df: pd.DataFrame, invoice_meta: dict) -> None:
    """Persist the invoice datasets consumed by automatic Payroll."""
    source_version = target_date.isoformat()
    vpg.write_dataset(
        _key("timesoft_summary_invoice", target_date),
        invoice_df,
        ttl_seconds=TIMESOFT_HISTORY_TTL_SECONDS,
        source_version=source_version,
    )
    vpg.write_dataset(
        _key("timesoft_summary_totals", target_date),
        pd.DataFrame([invoice_meta]),
        ttl_seconds=TIMESOFT_HISTORY_TTL_SECONDS,
        source_version=source_version,
    )
    if target_date == datetime.now(VN_TZ).date():
        vpg.write_dataset(
            "timesoft_summary_invoice_today",
            invoice_df,
            ttl_seconds=1800,
            source_version=source_version,
        )
        vpg.write_dataset(
            "timesoft_summary_totals_today",
            pd.DataFrame([invoice_meta]),
            ttl_seconds=1800,
            source_version=source_version,
        )


def write_snapshot(target_date: date, invoice_df: pd.DataFrame, invoice_meta: dict,
                   checkin_df: pd.DataFrame, checkin_meta: dict) -> None:
    source_version = target_date.isoformat()
    # Snapshot gắn ngày được giữ dài hạn để Admin xem lịch sử/export.
    write_invoice_snapshot(target_date, invoice_df, invoice_meta)
    vpg.write_dataset(
        _key("timesoft_employee_checkin", target_date),
        checkin_df,
        ttl_seconds=TIMESOFT_HISTORY_TTL_SECONDS,
        source_version=source_version,
    )
    if target_date == datetime.now(VN_TZ).date():
        vpg.write_dataset("timesoft_employee_checkin_today", checkin_df, ttl_seconds=1800, source_version=source_version)


def backfill_missing_payroll_snapshots(session: requests.Session, conn, today: date) -> dict:
    """Fetch only missing historical invoice days, newest first.

    A bounded batch keeps the frequently scheduled job fast.  With the default
    batch of 12, the six missing days of a payroll period are repaired in one
    execution; older gaps continue automatically on later scheduler runs.
    """
    missing = _missing_payroll_invoice_dates(conn, today)
    targets = list(reversed(missing))[:PAYROLL_BACKFILL_BATCH_DAYS]
    result = {
        "missing_before": len(missing),
        "attempted": len(targets),
        "added": 0,
        "errors": 0,
        "dates": [],
    }
    for target_date in targets:
        try:
            invoice_df, invoice_meta = fetch_summary(session, target_date)
            write_invoice_snapshot(target_date, invoice_df, invoice_meta)
            result["added"] += 1
            result["dates"].append(target_date.isoformat())
            _log(f"Payroll backfill {target_date.isoformat()}: invoice_rows={len(invoice_df)}")
        except Exception as exc:
            result["errors"] += 1
            _log(f"PAYROLL BACKFILL ERROR {target_date.isoformat()}: {type(exc).__name__}: {exc}")
    return result


def write_status(status: str, started_at: datetime, details: list[dict], error: str = "",
                 auto_status: str = "", tour_result: dict | None = None, timesoft_result: dict | None = None,
                 break_return_result: dict | None = None, payroll_backfill_result: dict | None = None) -> None:
    now = datetime.now(VN_TZ)
    today_detail = next((x for x in details if x.get("date") == now.date().isoformat()), {})
    tour_result = tour_result or {}
    timesoft_result = timesoft_result or {}
    break_return_result = break_return_result or {}
    payroll_backfill_result = payroll_backfill_result or {}
    row = {
        "status": status,
        "synced_at": now.isoformat(),
        "synced_at_vn": now.strftime("%d/%m/%Y %H:%M:%S"),
        "started_at": started_at.isoformat(),
        "duration_seconds": round((now - started_at).total_seconds(), 3),
        "days_synced": len(details),
        "invoice_rows": int(today_detail.get("invoice_rows", 0) or 0),
        "checkin_rows": int(today_detail.get("checkin_rows", 0) or 0),
        "total_money": float(today_detail.get("total_money", 0) or 0),
        "total_discount": float(today_detail.get("total_discount", 0) or 0),
        "total_actual_revenue": float(today_detail.get("total_actual_revenue", 0) or 0),
        "auto_penalty_status": str(auto_status or ""),
        "auto_tour_added": int(tour_result.get("added", 0) or 0),
        "auto_timesoft_added": int(timesoft_result.get("added", 0) or 0),
        "auto_break_return_added": int(break_return_result.get("added", 0) or 0),
        "auto_tour_errors": int(tour_result.get("errors", 0) or 0),
        "auto_timesoft_errors": int(timesoft_result.get("errors", 0) or 0),
        "auto_break_return_errors": int(break_return_result.get("errors", 0) or 0),
        "payroll_backfill_missing_before": int(payroll_backfill_result.get("missing_before", 0) or 0),
        "payroll_backfill_attempted": int(payroll_backfill_result.get("attempted", 0) or 0),
        "payroll_backfill_added": int(payroll_backfill_result.get("added", 0) or 0),
        "payroll_backfill_errors": int(payroll_backfill_result.get("errors", 0) or 0),
        "error": str(error or "")[:500],
    }
    vpg.write_dataset(
        "timesoft_background_status",
        pd.DataFrame([row]),
        ttl_seconds=1800,
        source_version=now.isoformat(),
    )
    # Ghi lịch sử mỗi lần Job chạy; nếu helper cũ chưa có record_event thì bỏ qua an toàn.
    record_fn = getattr(vpg, "record_event", None)
    if callable(record_fn):
        try:
            record_fn(
                "timesoft_background_status",
                f"job_{str(status or 'unknown').lower()}",
                json.dumps(row, ensure_ascii=False, default=str),
            )
        except Exception:
            pass


# ==========================================================
# MAIN JOB
# ==========================================================
def run_sync() -> int:
    started_at = datetime.now(VN_TZ)
    _log(f"Bắt đầu TimeSoft background sync V93.6; days={SYNC_DAYS}")
    if not vpg.is_enabled():
        _log("ERROR: PostgreSQL chưa được bật.")
        return 2

    engine = vpg.get_engine()
    lock_conn = engine.connect()
    got_lock = False
    details: list[dict] = []
    checkin_by_date: list[tuple[date, pd.DataFrame]] = []
    tour_result = {"eligible": 0, "added": 0, "skipped": 0, "errors": 0}
    timesoft_result = {"eligible": 0, "added": 0, "skipped": 0, "errors": 0}
    break_return_result = {"eligible": 0, "added": 0, "skipped": 0, "errors": 0}
    payroll_backfill_result = {"missing_before": 0, "attempted": 0, "added": 0, "errors": 0}
    auto_status = "UNKNOWN"

    try:
        got_lock = bool(lock_conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": LOCK_NAME}).scalar())
        if not got_lock:
            _log("Một lần đồng bộ TimeSoft khác đang chạy; bỏ qua lần này.")
            return 0

        session = create_authenticated_session()
        today = datetime.now(VN_TZ).date()
        dates = [today - timedelta(days=i) for i in range(SYNC_DAYS)]
        for target_date in dates:
            invoice_df, invoice_meta = fetch_summary(session, target_date)
            checkin_df, checkin_meta = fetch_checkin(session, target_date)
            write_snapshot(target_date, invoice_df, invoice_meta, checkin_df, checkin_meta)
            checkin_by_date.append((target_date, checkin_df))
            detail = {
                "date": target_date.isoformat(),
                "invoice_rows": len(invoice_df),
                "checkin_rows": len(checkin_df),
                "checkin_total": int(checkin_meta.get("Total") or len(checkin_df)),
                "total_money": float(invoice_meta.get("TotalMoney") or 0),
                "total_discount": float(invoice_meta.get("TotalDiscount") or 0),
                "total_actual_revenue": float(invoice_meta.get("TotalActualRevenu") or 0),
            }
            details.append(detail)
            _log(f"Đã đồng bộ {target_date.isoformat()}: invoice_rows={len(invoice_df)}; checkin_rows={len(checkin_df)}")

        # PostgreSQL được tạo sau TimeSoft nên những ngày đầu kỳ lương có thể
        # chưa từng được snapshot.  Chỉ bù các ngày invoice còn thiếu; không tải
        # lại check-in lịch sử và không làm nặng luồng đồng bộ 2 ngày thường lệ.
        payroll_backfill_result = backfill_missing_payroll_snapshots(session, lock_conn, today)
        _log(
            "Payroll backfill: "
            f"missing_before={payroll_backfill_result['missing_before']} "
            f"attempted={payroll_backfill_result['attempted']} "
            f"added={payroll_backfill_result['added']} "
            f"errors={payroll_backfill_result['errors']}"
        )

        # Auto Check PostgreSQL-only: config, policy, history and violations no
        # longer depend on Google Sheets. The Tour workbook remains read-only.
        run_id = None
        try:
            with engine.begin() as conn:
                cfg = auto_check.load_config(conn)
                trigger_type = "manual" if cfg.get("manual_run_requested") else "scheduled"
                run_id = auto_check.start_run(conn, trigger_type)
                if cfg.get("manual_run_requested"):
                    cfg = auto_check.save_config(conn, {"manual_run_requested": False}, "AUTO CHECK JOB")
            auto_status = str(cfg.get("status", "UNKNOWN"))
            _log(f"Auto penalty status={auto_status}; threshold={cfg.get('threshold_minutes', AUTO_PENALTY_MINUTES)} phút")
            if auto_status == AUTO_PENALTY_PAUSED:
                _log("Auto penalty PAUSED bởi Admin -> chỉ đồng bộ snapshot, KHÔNG ghi phạt.")
            else:
                employee_map = load_employee_name_map()
                with engine.connect() as conn:
                    catalog = auto_check.load_catalog(conn)
                _log(f"Đã tải danh mục: employees={len(employee_map)}; leave_types={len(catalog)}")
                timesoft_result = process_timesoft_penalties(engine, cfg, employee_map, catalog, checkin_by_date)
                break_return_result = process_break_return_penalties(engine, catalog)
                tour_result = process_tour_penalties(engine, cfg, employee_map, catalog)
                _log(
                    "Auto penalty hoàn tất: "
                    f"TimeSoft eligible={timesoft_result['eligible']} added={timesoft_result['added']} skipped={timesoft_result['skipped']} errors={timesoft_result['errors']}; "
                    f"Nghỉ giữa ca eligible={break_return_result['eligible']} added={break_return_result['added']} skipped={break_return_result['skipped']} errors={break_return_result['errors']}; "
                    f"Tour eligible={tour_result['eligible']} added={tour_result['added']} skipped={tour_result['skipped']} errors={tour_result['errors']}"
                )
            if run_id is not None:
                with engine.begin() as conn:
                    auto_check.finish_run(conn, run_id, "success", {"timesoft": timesoft_result, "break_return": break_return_result, "tour": tour_result, "auto_status": auto_status})
        except Exception as auto_exc:
            # Do not lose the TimeSoft snapshot if Auto Check alone fails.
            auto_status = "ERROR"
            _log(f"AUTO PENALTY ERROR: {type(auto_exc).__name__}: {auto_exc}")
            tour_result["errors"] = int(tour_result.get("errors", 0)) + 1
            if run_id is not None:
                try:
                    with engine.begin() as conn:
                        auto_check.finish_run(conn, run_id, "error", {"timesoft": timesoft_result, "break_return": break_return_result, "tour": tour_result}, str(auto_exc))
                except Exception:
                    pass

        write_status(
            "success", started_at, details,
            auto_status=auto_status,
            tour_result=tour_result,
            timesoft_result=timesoft_result,
            break_return_result=break_return_result,
            payroll_backfill_result=payroll_backfill_result,
        )
        _log(f"Hoàn tất Job V93.6 trong {(datetime.now(VN_TZ)-started_at).total_seconds():.1f}s")
        return 0
    except Exception as exc:
        safe_error = f"{type(exc).__name__}: {exc}"
        _log(f"ERROR: {safe_error}")
        try:
            write_status(
                "error", started_at, details, safe_error,
                auto_status=auto_status,
                tour_result=tour_result,
                timesoft_result=timesoft_result,
                break_return_result=break_return_result,
                payroll_backfill_result=payroll_backfill_result,
            )
        except Exception as status_exc:
            _log(f"Không ghi được sync status: {type(status_exc).__name__}")
        return 1
    finally:
        if got_lock:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": LOCK_NAME})
            except Exception:
                pass
        try:
            lock_conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(run_sync())

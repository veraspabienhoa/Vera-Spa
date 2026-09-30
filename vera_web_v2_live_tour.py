Warning: truncated output (original token count: 78220)
Total output lines: 5298

"""Independent, transactional Live Tour board for Web V2.

No workbook, filesystem or Google service is used as an operational data source.
Live Tour keeps its own canonical state in ``vera_app_setting`` so a whole
booking/payment operation is committed as one PostgreSQL transaction.
"""
from __future__ import annotations

from vera_web_v2_live_tour_attendance import AttendanceBreakReader, sync_breaks
from vera_web_v2_live_tour_lock import acquire_state_lock, try_state_lock
import vera_live_tour_relational as relational_store
import vera_live_tour_resource_store as resource_store
import vera_live_tour_lists as list_queries
import vera_postgres_job_queue as job_queue
import vera_live_tour_queue_alerts as queue_alerts
from vera_live_tour_timing import ActionTiming
import vera_live_tour_leave_return as leave_return
from vera_live_tour_leave_queue_policy import load_policy as load_leave_queue_policy

import hashlib
import json
import math
import logging
from threading import Event, Thread
import re
import unicodedata
from collections.abc import Callable
from contextlib import asynccontextmanager
from copy import deepcopy
from functools import lru_cache
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import Any
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from sqlalchemy import text
from vera_web_v2_live_tour_payment import default_settings as _default_payment_settings, settings_update as _payment_settings_update, payment_values as _payment_values
from vera_web_v2_live_tour_payment import profile_bank as _profile_bank, selected_bank as _selected_bank
from vera_web_v2_live_tour_payment import service_subtotal as _invoice_service_subtotal
from vera_web_v2_live_tour_daily import sync_daily as _sync_daily
from vera_web_v2_live_tour_checkin import with_checkin as _directory_with_checkin
from vera_web_v2_combo_import import import_terms as _combo_import_terms
from vera_web_v2_live_tour_roster import shift_label as _directory_shift
from vera_web_v2_live_tour_roster import eligible as _roster_eligible, reconcile as _reconcile_roster
from vera_web_v2_service_catalog import catalog_details, component_debits, purchase_terms, require_available
from vera_web_v2_live_tour_permissions import CAPABILITY_FEATURES, EXPORT_FEATURES
from vera_web_v2_live_tour_changes import change_customer
from vera_web_v2_live_tour_invoice import change_paid_invoice

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
STATE_CATEGORY = "live_tour"
STATE_KEY = "state"
STATE_LOCK = "vera:v2:live_tour:state"
STATE_VERSION = 1
PROJECTION_REFRESH_SECONDS = 300
PROJECTION_QUEUE = "live_tour_projection"
PROJECTION_RELEASE = "live-tour-projection-2026-09-28-checkin-signal"
BUSINESS_DAY_CUTOFF = time(11, 10)
MAX_AUDIT = 3000
MAX_BACKUPS = 20
MAX_IDEMPOTENCY = 3000
MAX_MONEY = 10_000_000_000
MAX_SERVICE_DURATION_MINUTES = 1_440
MAX_TICKET_UNITS = 100_000
MAX_PURCHASE_QUANTITY = 1_000
CUSTOMER_PII_KEYS = frozenset({"customer_id", "customer_name", "customer_phone", "phone", "combo_purchase_id", "combo_reserved_units", "combo_reserved_components"})
PROTECTED_IDEMPOTENCY_ACTIONS = frozenset({
    "customer_delete", "customer_combo_update", "customer_combo_delete", "report_invoice_update", "report_invoice_delete",
    "paid_invoice_update", "paid_invoice_delete",
    "pending_update", "pending_delete",
    "checkout", "quick_checkout", "combo_purchase", "combo_sale_decide", "sync_leaves", "finish_to_pending", "start_room", "finish_room", "clear_orphan_pending",
})
BACKDATE_ACTIONS = frozenset({"checkout", "quick_checkout", "combo_purchase"})
CLIENT_FINANCIAL_TIME_FIELDS = frozenset({
    "business_date", "created_at", "effective_at", "recorded_at",
})
IDEMPOTENCY_REQUIRED_ACTIONS = {
    "customer_delete", "customer_combo_update", "customer_combo_delete", "report_invoice_update", "report_invoice_delete",
    "paid_invoice_update", "paid_invoice_delete",
    "pending_update", "pending_delete",
    "booking", "multi_booking", "start", "add_minutes", "complete", "move_pending",
    "checkout", "quick_checkout", "set_work_status", "set_shift", "start_break", "end_break",
    "reorder", "admin_reorder", "sync_daily_status",
    "set_vip", "replace_service", "add_service", "room_upsert", "room_delete", "service_upsert",
    "service_delete", "combo_upsert", "combo_delete", "combo_purchase", "combo_sale_decide", "combo_import", "backup",
    "restore", "clear_expired", "customer_upsert", "service_area_upsert", "service_area_delete", "settings_reorder",
    "update_booking", "cancel_booking", "restart_booking", "change_employee", "update_appointment", "update_started_at", "finish_to_pending", "payment_settings_update", "appearance_settings_update", "start_room", "finish_room", "clear_orphan_pending",
}
BOARD_COLUMNS = [
    "STT", "Tên nhân viên", "Lịch hẹn", "Trạng thái", "Phòng", "TG CÒN LẠI", "Yêu cầu",
    "Dịch vụ", "Đi làm", "Vào ca", "Breaktime", "TG nghỉ còn lại",
    "Giờ ra", "Giờ vào", "Ghi chú", "Thời lượng", "TG bắt đầu thực hiện",
    "TG bắt đầu thực hiện YC", "TT thanh toán", "Kết quả hoàn thành", "SL tua", "SL yêu cầu",
    "Tổng SL", "VIP", "Giờ Booking", "TG khách chờ", "TG Xông Hơi",
]

DEFAULT_ROOM_BEDS = [
    "1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2", "4", "6.1", "6.2", "6.3",
    "8.1", "8.2", "8.3", "8.4", "9.1", "9.2", "10.1", "10.2", "10.3", "10.4",
    "11.1", "11.2", "11.3", "12.1", "12.2", "12.3", "12B", "14.1", "14.2",
    "15.1", "15.2", "16.1", "16.2", "17.1", "17.2", "18.1", "18.2",
    "19.1", "19.2", "19.3", "20.1", "20.2", "21.1", "21.2", "21.3",
]

DEFAULT_SERVICES = [
    {"name": "P.Riêng", "duration": 90, "price": 0, "ticket_units": 1},
    {"name": "Body 90", "duration": 90, "price": 0, "ticket_units": 1},
    {"name": "Body 70", "duration": 70, "price": 0, "ticket_units": 1},
    {"name": "VIP 90 PR", "duration": 90, "price": 0, "ticket_units": 1},
    {"name": "VIP 90", "duration": 90, "price": 0, "ticket_units": 1},
    {"name": "VIP 70 PR", "duration": 70, "price": 0, "ticket_units": 1},
    {"name": "VIP 70", "duration": 70, "price": 0, "ticket_units": 1},
    {"name": "Mua thêm 30", "duration": 30, "price": 0, "ticket_units": 0},
    {"name": "Xông hơi", "duration": None, "price": 0, "ticket_units": 0},
]

DEFAULT_COMBOS = [
    {"name": "Combo 13", "tickets": 13, "price": 2_500_000},
    {"name": "Combo 14", "tickets": 14, "price": 2_500_000},
    {"name": "Combo VIP 90", "tickets": 13, "price": 3_000_000},
    {"name": "Combo VIP PR", "tickets": 13, "price": 3_500_000},
]


class LiveTourAction(BaseModel):
    response_view: str = "full"
    action: str = Field(min_length=1, max_length=80)
    expected_revision: int | None = Field(default=None, ge=0)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)


def _normalize_text(value: str) -> str:
    raw = unicodedata.normalize("NFD", value.strip().lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn").replace("đ", "d")
    return " ".join(raw.replace("_", " ").split())


_cached_normalize_text = lru_cache(maxsize=4096)(_normalize_text)


def _norm(value: Any) -> str:
    value = str(value or "")
    # Pure text only: no permissions, state or business results are cached.
    # Bound both entry count and input length, including operator-supplied text.
    return _cached_normalize_text(value) if len(value) <= 256 else _normalize_text(value)


class _ResponseState(dict):
    """Indexes owned by one immutable response projection, never persisted."""

    def __init__(self, state):
        super().__init__(state)
        self.room_index = {}
        for room in self["rooms"]:
            self.room_index.setdefault(_norm(room.get("name")), room)
        self.private_services = {}


def _canonical_shift(value: Any, *, allow_blank: bool = False) -> str:
    token = _norm(value).replace(" ", "")
    if allow_blank and not token:
        return ""
    if token in {"ca1", "1", "10", "10h", "10h00"}:
        return "Ca 1"
    if token in {"ca2", "2", "12", "12h", "12h00", "14", "14h", "14h00"}:
        return "Ca 2"
    raise HTTPException(400, "Ca làm việc chỉ nhận Ca 1 hoặc Ca 2.")


def _canonical_work_status(value: Any) -> str:
    token = _norm(value)
    mapping = {
        "di lam": "Đi làm", "dang lam viec": "Đi làm",
        "nghi phep": "Nghỉ phép", "nghi co phep": "Nghỉ phép",
        "nghi": "Nghỉ", "khong di lam": "Nghỉ",
    }
    if token not in mapping:
        raise HTTPException(400, "Trạng thái chỉ nhận Đi làm, Nghỉ phép hoặc Nghỉ.")
    return mapping[token]


def _canonical_payment_method(value: Any, *, quick: bool = False) -> str:
    token = _norm(value)
    if not token and quick:
        token = "tien mat"
    mapping = {
        "tien mat": "TIỀN MẶT", "cash": "TIỀN MẶT",
        "chuyen khoan": "CHUYỂN KHOẢN", "transfer": "CHUYỂN KHOẢN",
        "bank transfer": "CHUYỂN KHOẢN", "the": "THẺ", "card": "THẺ",
        "combo": "COMBO",
    }
    if token not in mapping:
        raise HTTPException(400, "Phương thức thanh toán chỉ nhận TIỀN MẶT, CHUYỂN KHOẢN, THẺ hoặc COMBO.")
    return mapping[token]


def _phone_key(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _redact_customer_pii(value: Any) -> Any:
    """Return a deep redacted copy, including dictionaries nested in lists."""
    if isinstance(value, dict):
        return {
            key: _redact_customer_pii(item)
            for key, item in value.items()
            if str(key).casefold() not in CUSTOMER_PII_KEYS
        }
    if isinstance(value, list):
        return [_redact_customer_pii(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_customer_pii(item) for item in value)
    return deepcopy(value)


def _redact_customer_name_alias(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_customer_name_alias(item)
            for key, item in value.items() if str(key).casefold() != "name"
        }
    if isinstance(value, list):
        return [_redact_customer_name_alias(item) for item in value]
    return deepcopy(value)


def _contains_customer_pii(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in CUSTOMER_PII_KEYS and item not in (None, ""):
                return True
            if _contains_customer_pii(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_customer_pii(item) for item in value)
    return False


def _canonical_payload_hash(action: str, payload: dict[str, Any]) -> str:
    canonical_payload = {
        str(key): value for key, value in payload.items()
        if str(key) != "idempotency_key" and not str(key).startswith("_")
    }
    encoded = json.dumps(
        {"action": str(action or "").strip().lower(), "payload": canonical_payload},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _common_customer_identity(items: list[dict[str, Any]]) -> dict[str, str]:
    identity_tokens: list[set[tuple[str, str]]] = []
    has_anonymous = False
    for item in items:
        tokens = {
            ("customer_id", str(item.get("customer_id") or "").strip()),
            ("customer_phone", _phone_key(item.get("customer_phone"))),
            ("customer_name", _norm(item.get("customer_name"))),
        }
        tokens = {(key, value) for key, value in tokens if value}
        if tokens:
            identity_tokens.append(tokens)
        else:
            has_anonymous = True
    if identity_tokens and has_anonymous:
        raise HTTPException(409, "Không được thanh toán chung dịch vụ có khách và dịch vụ khách vãng lai.")

    ids = {str(item.get("customer_id") or "").strip() for item in items if item.get("customer_id")}
    phones = {_phone_key(item.get("customer_phone")) for item in items if _phone_key(item.get("customer_phone"))}
    names = {_norm(item.get("customer_name")) for item in items if _norm(item.get("customer_name"))}
    if len(ids) > 1 or len(phones) > 1 or len(names) > 1:
        raise HTTPException(409, "Các dịch vụ đã chọn không thuộc cùng một khách hàng.")
    # Sparse rows are accepted only when their identity fields form one
    # connected identity (for example an ID-only row plus an ID/name/phone row).
    if len(identity_tokens) > 1:
        connected = set(identity_tokens[0])
        remaining = identity_tokens[1:]
        while remaining:
            newly_connected = [tokens for tokens in remaining if connected & tokens]
            if not newly_connected:
                raise HTTPException(409, "Thông tin khách hàng giữa các dịch vụ không nhất quán.")
            for tokens in newly_connected:
                connected.update(tokens)
                remaining.remove(tokens)
    first_name = next((str(item.get("customer_name") or "").strip() for item in items if _norm(item.get("customer_name"))), "")
    first_phone = next((str(item.get("customer_phone") or "").strip() for item in items if _phone_key(item.get("customer_phone"))), "")
    return {
        "customer_id": next(iter(ids), ""),
        "customer_phone": first_phone if phones else "",
        "customer_name": first_name if names else "",
    }


def _protect_customer_identity(payload: dict[str, Any], canonical: dict[str, str]) -> dict[str, Any]:
    protected = dict(payload)
    requested_id = str(payload.get("customer_id") or "").strip()
    requested_phone = _phone_key(payload.get("customer_phone") or payload.get("phone"))
    requested_name = _norm(payload.get("customer_name"))
    if canonical.get("customer_id") and requested_id and requested_id != canonical["customer_id"]:
        raise HTTPException(409, "Không được đổi khách hàng của dịch vụ khi thanh toán.")
    if _phone_key(canonical.get("customer_phone")) and requested_phone and requested_phone != _phone_key(canonical["customer_phone"]):
        raise HTTPException(409, "Số điện thoại thanh toán không khớp với khách đã đặt dịch vụ.")
    if canonical.get("customer_name") and requested_name and requested_name != _norm(canonical["customer_name"]):
        raise HTTPException(409, "Tên khách thanh toán không khớp với khách đã đặt dịch vụ.")
    for key in ("customer_id", "customer_name", "customer_phone"):
        if canonical.get(key):
            protected[key] = canonical[key]
    protected.pop("phone", None)
    return protected


def _auto_yc_ca1(now: datetime, employee: dict[str, Any], request: Any, enabled: bool) -> tuple[str, bool]:
    requested = str(request or "").strip()
    if requested and _norm(requested) != "yc":
        raise HTTPException(400, "Yêu cầu chỉ nhận YC hoặc để trống.")
    requested = "YC" if requested else ""
    local_clock = now.astimezone(VN_TZ).time().replace(tzinfo=None)
    in_window = local_clock >= time(23, 0) or local_clock <= time(3, 0)
    auto = bool(enabled) and not requested and _shift_bucket(employee) == "ca1" and in_window
    return ("YC" if auto else requested), auto


def _before_shift_ready(state, employee, now):
    local = now.astimezone(VN_TZ)
    if employee.get("shift_checkin_date") != local.date().isoformat():
        return False
    reason = _norm(employee.get("synced_leave_reason"))
    key = ("support2" if re.search(r"ho tro ca\s*2\b", reason) else
           "support1" if re.search(r"ho tro ca\s*1\b", reason) else
           "shift2" if _norm(employee.get("shift")) == "ca 2" else "")
    if not key or not employee.get("shift"):
        return False
    defaults = {"shift2": "13:00", "support1": "12:00", "support2": "14:00"}
    cutoff = (state.get("payment_settings", {}).get("shift_ready_times") or {}).get(key) or defaults[key]
    return local.strftime("%H:%M") < cutoff


def _combo_extra_subtotal(state, purchase, entries):
    if "component_balances" not in purchase:
        return 0
    covered = {part["service_id"] for part in purchase["component_balances"]}
    for entry in entries:
        if not entry.get("service_items"):
            name = str(entry.get("service") or "")
            exact = next((row for row in state["services"] if _norm(row["name"]) == _norm(name)), None)
            names = [name] if exact else name.split("&")
            resolved = []
            for part in names:
                service = next((row for row in state["services"] if _norm(row["name"]) == _norm(part)), None)
                if not service:
                    raise HTTPException(409, "Không nhận diện được dịch vụ mua thêm để tính tiền.")
                resolved.append({"service_id": service["id"], "name": service["name"], "unit_price": service.get("price", 0), "quantity": 1})
            entry["service_items"] = resolved
        entry["combo_extra_subtotal"] = sum(item["unit_price"] * item["quantity"]
            for item in entry["service_items"] if item["service_id"] not in covered)
    return sum(entry["combo_extra_subtotal"] for entry in entries)


def _number(value: Any, default: float = 0) -> float:
    if value in (None, "") or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(" ", "")
    if "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return default


def _money(value: Any) -> int:
    return int(round(_number(value)))


def _bounded_number(
    value: Any, *, label: str, minimum: float = 0, maximum: float,
    integer: bool = False, allow_blank: bool = False,
) -> float | int | None:
    if value in (None, ""):
        if allow_blank:
            return None
        raise HTTPException(400, f"{label} không được để trống.")
    number = _number(value, math.nan)
    if not math.isfinite(number):
        raise HTTPException(400, f"{label} phải là số hữu hạn hợp lệ.")
    if number < minimum or number > maximum:
        raise HTTPException(400, f"{label} phải từ {minimum:g} đến {maximum:g}.")
    if integer and not float(number).is_integer():
        raise HTTPException(400, f"{label} phải là số nguyên.")
    return int(number) if integer else number


def _bounded_money(value: Any, *, label: str, allow_blank_as_zero: bool = False) -> int:
    normalized = 0 if allow_blank_as_zero and value in (None, "") else value
    number = _bounded_number(
        normalized, label=label, minimum=0, maximum=MAX_MONEY,
    )
    return int(round(float(number)))


def _duration_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = abs(float(value))
        if not math.isfinite(number):
            return None
        return number * 1440 if 0 < number < 1 else number
    raw = str(value).strip()
    match = re.fullmatch(r"(\d{1,3}):(\d{1,2})(?::(\d{1,2}))?", raw)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2)) + int(match.group(3) or 0) / 60
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", raw)
    if not match:
        return None
    number = abs(float(match.group(0).replace(",", ".")))
    return number if math.isfinite(number) else None


def _source_start(value: Any, now: datetime, duration: float | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if 0 <= number < 1:
            seconds = int(round(number * 86400)) % 86400
            parsed = now.replace(hour=seconds // 3600, minute=(seconds % 3600) // 60, second=seconds % 60, microsecond=0)
            if parsed > now and (now - (parsed - timedelta(days=1))).total_seconds() / 60 <= max(float(duration or 0) + 240, 480):
                parsed -= timedelta(days=1)
            return parsed
        if number >= 1:
            return datetime(1899, 12, 30, tzinfo=now.tzinfo) + timedelta(days=number)
    raw = str(value).strip()
    clock = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
    if clock:
        try:
            parsed = now.astimezone(VN_TZ).replace(
                hour=int(clock.group(1)), minute=int(clock.group(2)),
                second=int(clock.group(3) or 0), microsecond=0,
            )
        except ValueError:
            return None
        if parsed > now.astimezone(VN_TZ) + timedelta(hours=3):
            parsed -= timedelta(days=1)
        return parsed
    return _parse_datetime(value)


def _iso(now: datetime) -> str:
    return now.astimezone(VN_TZ).replace(microsecond=0).isoformat()


def _business_date(now: datetime) -> date:
    local = now.astimezone(VN_TZ)
    return local.date() if local.time().replace(tzinfo=None) >= BUSINESS_DAY_CUTOFF else local.date() - timedelta(days=1)


def _counter_business_date(now: datetime) -> date:
    local = now.astimezone(VN_TZ)
    return local.date() - timedelta(days=1) if local.time() < time(10) else local.date()


def _ensure_counter_day(state: dict[str, Any], now: datetime) -> None:
    today = _counter_business_date(now).isoformat()
    prior = state.get("counter_business_date", state.get("business_date", today))
    if str(prior) < today:
        for employee in state["employees"]:
            employee.update({"tour_count": 0, "request_count": 0, "break_count": 0})
    state["counter_business_date"] = max(str(prior), today)


def _backdate_requested(payload: dict[str, Any]) -> bool:
    value = payload.get("backdate_one_day", False)
    if value is True:
        return True
    if value is False or value in (None, ""):
        return False
    raise HTTPException(400, "backdate_one_day chỉ nhận giá trị true hoặc false.")


def _financial_timing(payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Return server-owned recorded/effective timestamps for a payment action."""
    overridden = sorted(
        key for key in CLIENT_FINANCIAL_TIME_FIELDS
        if key in payload and payload.get(key) not in (None, "")
    )
    if overridden:
        raise HTTPException(
            400,
            "Thời điểm giao dịch do máy chủ xác định; không được gửi " + ", ".join(overridden) + ".",
        )
    backdated = _backdate_requested(payload)
    reason = str(payload.get("correction_reason") or "").strip()
    if backdated and len(reason) < 3:
        raise HTTPException(400, "Lùi 1 ngày cần lý do điều chỉnh tối thiểu 3 ký tự.")
    if not backdated and reason:
        raise HTTPException(400, "Lý do điều chỉnh chỉ dùng khi chọn Lùi 1 ngày.")

    recorded = now.astimezone(VN_TZ).replace(microsecond=0)
    effective = recorded
    if backdated:
        # VBA displays the current business date (11:10 cutoff), then its
        # "Lùi 1 ngày" button subtracts one more date and fixes the time at
        # 23:59.  During the overnight window this is two calendar dates
        # behind ``recorded.date()``, by design.
        effective = datetime.combine(
            _business_date(recorded) - timedelta(days=1), time(23, 59), tzinfo=VN_TZ,
        )
    return {
        "backdate_one_day": backdated,
        "correction_reason": reason,
        "recorded_at": _iso(recorded),
        "effective_at": _iso(effective),
        "business_date": _business_date(effective).isoformat(),
        "effective_datetime": effective,
    }


def _booking_timing(entries, now, pending=None):
    pending = pending or {}
    dates = [_parse_datetime(row.get("booked_at")) for row in entries]
    effective = (_parse_datetime(pending.get("effective_at")) or _parse_datetime(pending.get("booked_at"))
                 or min((value for value in dates if value), default=None)
                 or _parse_datetime(pending.get("created_at")) or now.astimezone(VN_TZ))
    return {"recorded_at": _iso(now), "effective_at": _iso(effective),
            "business_date": effective.astimezone(VN_TZ).date().isoformat(),
            "effective_datetime": effective, "backdate_one_day": False, "correction_reason": ""}


def _invoice_date(value):
    parsed = _parse_datetime(value)
    if not isinstance(value, str) or not parsed or not 2000 <= parsed.year <= 2100:
        raise HTTPException(400, "Ngày giờ hóa đơn không hợp lệ (2000–2100).")
    return {"effective_at": _iso(parsed), "business_date": parsed.astimezone(VN_TZ).date().isoformat()}


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed.replace(tzinfo=VN_TZ) if parsed.tzinfo is None else parsed.astimezone(VN_TZ)
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
            if fmt.startswith("%H"):
                today = datetime.now(VN_TZ)
                parsed = parsed.replace(year=today.year, month=today.month, day=today.day)
            return parsed.replace(tzinfo=VN_TZ)
        except ValueError:
            continue
    return None


def _display_datetime(value: Any) -> str:
    parsed = _parse_datetime(value)
    return parsed.strftime("%d/%m/%Y %H:%M:%S") if parsed else str(value or "")


def _room_group(value: Any) -> str:
    room = _norm(value)
    room = re.sub(r"^(phong|vip)\s*", "", room).strip()
    return room.split(".", 1)[0]


def _catalog_room_group(state: dict[str, Any], name: Any) -> str:
    token = _norm(name)
    index = getattr(state, 'room_index', None)
    item = index.get(token, {}) if index is not None else next((row for row in state["rooms"] if _norm(row.get("name")) == token), {})
    return str(item.get("area_name") or _room_group(name))


def _room_action_members(state: dict[str, Any], room: str, action: str) -> list[dict[str, Any]]:
    statuses = {"dang cho"} if action == "start_room" else {"dang thuc hien", "dang su dung"}
    return [employee for employee in state["employees"]
            if employee.get("service") and employee.get("room")
            and _norm(_catalog_room_group(state, employee["room"])) == _norm(room)
            and _norm(employee.get("status")) in statuses]


def _room_action_counts(state: dict[str, Any]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for employee in state["employees"]:
        if not employee.get("service") or not employee.get("room"):
            continue
        room = _catalog_room_group(state, employee["room"])
        bucket = counts.setdefault(room, {"waiting": 0, "doing": 0})
        status = _norm(employee.get("status"))
        if status == "dang cho":
            bucket["waiting"] += 1
        elif status in {"dang thuc hien", "dang su dung"}:
            bucket["doing"] += 1
    return counts


def _service_areas(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Project existing booking places into areas without changing their IDs."""
    areas: dict[str, dict[str, Any]] = {}
    for room in state["rooms"]:
        group = _catalog_room_group(state, room.get("name"))
        area_id = str(room.get("area_id") or f"legacy:{group}")
        area = areas.setdefault(area_id, {
            "id": area_id, "name": group, "kind": room.get("area_kind", "room"), "beds": [],
        })
        area["beds"].append({
            "id": room["id"], "name": room.get("bed_name") or room.get("name", ""),
            "booking_name": room.get("name", ""), "active": room.get("active", True),
        })
    for name in state.get("physical_rooms", []):
        if not any(_norm(area["name"]) == _norm(name) for area in areas.values()):
            areas[f"legacy:{name}"] = {"id": f"legacy:{name}", "name": name, "kind": "room", "beds": []}
    projected = list(areas.values())
    for area in projected:
        # Compare only this area's editable configuration, not the live board.
        area["version"] = hashlib.sha256(json.dumps(area, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    saved_order = state.get("service_area_order")
    if isinstance(saved_order, list):
        positions = {str(area_id): index for index, area_id in enumerate(saved_order)}
        projected.sort(key=lambda area: positions.get(str(area["id"]), len(positions)))
    return projected


def _area_precondition(state: dict[str, Any], action: str, payload: dict[str, Any]) -> bool:
    if action not in {"service_area_upsert", "service_area_delete"} or "expected_area_version" not in payload:
        return False
    area_id = str(payload.get("id") or "").strip()
    if not area_id and action == "service_area_upsert" and payload["expected_area_version"] is None:
        return True
    current = next((area for area in _service_areas(state) if area["id"] == area_id), None)
    if not current or not isinstance(payload["expected_area_version"], str) or payload["expected_area_version"] != current["version"]:
        raise HTTPException(409, detail={
            "code": "LIVE_TOUR_AREA_CHANGED",
            "message": "Khu vực này vừa được người khác sửa hoặc xóa. Nội dung bạn nhập vẫn được giữ; hãy mở bản mới nhất trước khi lưu lại.",
        })
    return True


def _settings_reorder(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    scope = str(payload.get("scope") or "").strip()
    ordered_ids = payload.get("ordered_ids")
    if not isinstance(ordered_ids, list) or not ordered_ids or any(not isinstance(value, str) or not value.strip() for value in ordered_ids):
        raise HTTPException(400, "Thứ tự hiển thị không hợp lệ.")
    if len(set(ordered_ids)) != len(ordered_ids):
        raise HTTPException(400, "Thứ tự hiển thị có mục bị trùng.")
    if scope == "catalog":
        items = [("service", item) for item in state["services"]] + [("combo", item) for item in state["combos"]]
        current_ids = [f"{kind}:{item['id']}" for kind, item in items]
        if set(ordered_ids) != set(current_ids):
            raise HTTPException(409, "Danh sách dịch vụ đã thay đổi; hãy làm mới rồi thử lại.")
        positions = {key: index for index, key in enumerate(ordered_ids)}
        for kind, item in items:
            item["display_order"] = positions[f"{kind}:{item['id']}"]
        return {"ordered_ids": ordered_ids}
    if scope == "service_areas":
        current_ids = [str(area["id"]) for area in _service_areas(state)]
        if set(ordered_ids) != set(current_ids):
            raise HTTPException(409, "Danh sách khu vực đã thay đổi; hãy làm mới rồi thử lại.")
        state["service_area_order"] = ordered_ids
        return {"ordered_ids": ordered_ids}
    raise HTTPException(400, "Loại danh sách cần sắp xếp không hợp lệ.")


def _service_area_change(state: dict[str, Any], payload: dict[str, Any], *, delete: bool = False) -> dict[str, Any]:
    areas = _service_areas(state)
    area_id = str(payload.get("id") or "").strip()
    current = _find_by_id(areas, area_id, "khu vực dịch vụ") if area_id else None
    old_ids = {bed["id"] for bed in (current or {}).get("beds", [])}
    old_rooms = [row for row in state["rooms"] if row["id"] in old_ids]
    referenced = [row for row in old_rooms if _catalog_referenced(state, "rooms", row)]
    if delete:
        if referenced:
            raise HTTPException(409, "Khu vực còn dịch vụ chưa thanh toán; chưa thể xóa khu vực.")
        if current is None:
            raise HTTPException(400, "Thiếu mã khu vực dịch vụ.")
        state["rooms"] = [row for row in state["rooms"] if row["id"] not in old_ids]
        if current and "physical_rooms" in state:
            state["physical_rooms"] = [name for name in state["physical_rooms"] if _norm(name) != _norm(current["name"])]
        return {"deleted_id": area_id}
    name = str(payload.get("name") or "").strip()
    kind = payload.get("kind")
    if not name or len(name) > 100:
        raise HTTPException(400, "Tên khu vực cần từ 1 đến 100 ký tự.")
    if kind not in {"room", "bed", "table"}:
        raise HTTPException(400, "Loại khu vực chỉ nhận Phòng, Giường hoặc Bàn.")
    if any(area["id"] != area_id and _norm(area["name"]) == _norm(name) for area in areas):
        raise HTTPException(409, "Tên khu vực dịch vụ đã tồn tại.")
    beds = payload.get("beds") if kind == "room" else [{"name": name}]
    if not isinstance(beds, list) or not 1 <= len(beds) <= 100:
        raise HTTPException(400, "Mỗi phòng cần từ 1 đến 100 giường.")
    area_id = area_id or str(uuid4())
    remaining = [row for row in state["rooms"] if row["id"] not in old_ids]
    names = {_norm(row["name"]) for row in remaining}
    bed_names: set[str] = set()
    used_ids: set[str] = set()
    replacements = []
    for bed in beds:
        if not isinstance(bed, dict):
            raise HTTPException(400, "Thông tin giường không hợp lệ.")
        bed_name = str(bed.get("name") or "").strip()
        if not bed_name or len(bed_name) > 100 or _norm(bed_name) in bed_names:
            raise HTTPException(400, "Tên giường cần từ 1 đến 100 ký tự và không được trùng trong phòng.")
        bed_names.add(_norm(bed_name))
        bed_id = str(bed.get("id") or "")
        if kind != "room" and current and current["kind"] == kind:
            bed_id = current["beds"][0]["id"]
        if bed_id and (bed_id not in old_ids or bed_id in used_ids):
            raise HTTPException(400, "Mã giường không thuộc khu vực hoặc bị trùng.")
        bed_id = bed_id or str(uuid4())
        used_ids.add(bed_id)
        old = next((row for row in old_rooms if row["id"] == bed_id), {})
        old_bed = next((row for row in (current or {}).get("beds", []) if row["id"] == bed_id), {})
        booking_name = f"{name} · {bed_name}" if kind == "room" else name
        # A no-op edit of a legacy room must keep existing booking names.
        if current and current["name"] == name and current["kind"] == kind and old_bed.get("name") == bed_name:
            booking_name = old["name"]
        if _norm(booking_name) in names:
            raise HTTPException(409, "Tên vị trí phục vụ đã tồn tại.")
        names.add(_norm(booking_name))
        replacements.append({
            **old, "id": bed_id, "name": booking_name, "group": name,
            "area_id": area_id, "area_name": name, "area_kind": kind, "bed_name": bed_name,
            "type": "vip" if kind == "room" and _room_group(name) in {str(n) for n in range(16, 22)} else "standard",
            "active": old.get("active", True),
        })
    replacements_by_id = {row["id"]: row for row in replacements}
    for old in referenced:
        replacement = replacements_by_id.get(old["id"])
        if (not replacement or replacement["name"] != old["name"]
                or name != current["name"] or kind != current["kind"]):
            raise HTTPException(409, "Giường đang có dịch vụ chưa thanh toán; có thể thêm giường mới nhưng chưa thể đổi tên, chuyển loại hoặc xóa giường đang dùng.")
    state["rooms"] = remaining + replacements
    if current and "physical_rooms" in state:
        state["physical_rooms"] = [value for value in state["physical_rooms"] if _norm(value) != _norm(current["name"])]
    return {"service_area": next(area for area in _service_areas(state) if area["id"] == area_id)}


def _is_private_service(value: Any) -> bool:
    token = _norm(value)
    return bool(
        re.search(r"(^|[^a-z0-9])pr($|[^a-z0-9])", token)
        or re.search(r"(^|[^a-z0-9])p\s*\.?\s*rieng($|[^a-z0-9])", token)
    )


def _stable_id(prefix: str, value: Any) -> str:
    return str(uuid5(NAMESPACE_URL, f"vera-live-tour:{prefix}:{_norm(value)}"))


def _catalog_defaults() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rooms = [
        {
            "id": _stable_id("room", name), "name": name, "group": _room_group(name),
            "type": "vip" if _room_group(name).isdigit() and 16 <= int(_room_group(name)) <= 21 else "standard",
            "active": True,
        }
        for name in DEFAULT_ROOM_BEDS
    ]
    services = [
        {
            "id": _stable_id("service", item["name"]), **item,
            "private": _is_private_service(item["name"]), "active": True,
        }
        for item in DEFAULT_SERVICES
    ]
    combos = [
        {"id": _stable_id("combo", item["name"]), **item, "active": True}
        for item in DEFAULT_COMBOS
    ]
    return rooms, services, combos


def _empty_state(now: datetime) -> dict[str, Any]:
    rooms, services, combos = _catalog_defaults()
    return {
        "version": STATE_VERSION,
        "business_date": _business_date(now).isoformat(),
        "counter_business_date": _counter_business_date(now).isoformat(),
        "created_at": _iso(now), "updated_at": _iso(now),
        "employees": [], "rooms": rooms, "services": services, "combos": combos,
        "customers": [], "pending": [], "invoices": [], "reports": [], "combo_usage": [], "combo_sale_requests": [],
        "break_events": [], "payment_settings": _default_payment_settings(), "appearance_settings": {},
        "audit": [], "backups": [], "pending_changes": [], "invoice_changes": [], "customer_changes": [], "bill_counters": {}, "idempotency": {},
    }


def _normalize_state(raw: Any, now: datetime) -> dict[str, Any]:
    state = deepcopy(raw) if isinstance(raw, dict) else _empty_state(now)
    defaults = _empty_state(now)
    if not isinstance(state.get("customer_changes"), list):
        state["customer_changes"] = []
    if not isinstance(state.get("invoice_changes"), list):
        state["invoice_changes"] = []
    for key in ("employees", "rooms", "services", "combos", "customers", "pending", "invoices", "reports", "combo_usage", "combo_sale_requests", "break_events", "audit", "backups", "pending_changes"):
        if not isinstance(state.get(key), list):
            state[key] = deepcopy(defaults[key])
    if state.get("manual_order_active") is False:
        for row in state.get("employees", []):
            row.pop("manual_order", None)
    # An explicitly empty catalog is a saved choice, not an uninitialized state.
    state["version"] = STATE_VERSION
    state.setdefault("payment_settings", _default_payment_settings())
    if not isinstance(state.get("appearance_settings"), dict):
        state["appearance_settings"] = {}
    state.setdefault("business_date", _business_date(now).isoformat())
    state.setdefault("created_at", _iso(now))
    state.setdefault("updated_at", _iso(now))
    if not isinstance(state.get("bill_counters"), dict):
        state["bill_counters"] = {}
    if not isinstance(state.get("idempotency"), dict):
        state["idempotency"] = {}
    for index, employee in enumerate(state["employees"]):
        employee.setdefault("id", str(uuid4()))
        employee.setdefault("sort_index", index)
        employee["hidden"] = False
        employee.setdefault("vip", False)
        employee.setdefault("tour_count", 0)
        employee.setdefault("request_count", 0)
        employee.setdefault("work_status", "Đi làm")
        employee["work_status"] = _source_work_status(employee.get("work_status"))
        employee["shift"] = _source_shift(employee.get("shift"))
    return state


def _source_value(record: dict[str, Any], *names: str) -> Any:
    lookup = {_norm(key): value for key, value in record.items()}
    for name in names:
        if _norm(name) in lookup:
            return lookup[_norm(name)]
    return ""


def _source_work_status(value: Any) -> str:
    if value in (None, ""):
        return "Đi làm"
    try:
        return _canonical_work_status(value)
    except HTTPException:
        # Unknown source states must never silently make somebody available.
        return "Nghỉ"


def _source_shift(value: Any) -> str:
    try:
        return _canonical_shift(value, allow_blank=True)
    except HTTPException:
        return ""


def _source_employee(record: dict[str, Any], index: int, now: datetime) -> dict[str, Any] | None:
    source_name = str(_source_value(record, "Tên nhân viên", "Nhân viên", "Họ tên") or "").strip()
    vip = bool(re.search(r"\*+\s*$", source_name))
    name = re.sub(r"\s*\*+\s*$", "", source_name).strip()
    if not name:
        return None
    stt = str(_source_value(record, "STT", "Số thứ tự") or index + 1).strip()
    duration_raw = _source_value(record, "Thời lượng", "Thời lượng (phút)")
    duration = _duration_value(duration_raw)
    raw_request = str(_source_value(record, "Yêu cầu") or "").strip()
    request = "YC" if _norm(raw_request) == "yc" else ""
    request_source = "tour_import" if not raw_request or request else "tour_import_invalid"
    start_raw = _source_value(
        record,
        "TG bắt đầu thực hiện YC" if _norm(request) == "yc" else "TG bắt đầu thực hiện",
        "Bắt đầu thực hiện YC" if _norm(request) == "yc" else "Bắt đầu thực hiện",
    )
    started = _source_start(start_raw, now, duration) if start_raw else None
    booked_raw = _source_value(record, "Giờ Booking", "TG Booking")
    booked = _source_start(booked_raw, now, None) if booked_raw else None
    break_flag = _source_value(record, "Break", "Breaktime")
    clock_in_raw = _source_value(record, "Giờ vào")
    break_active = (
        bool(str(break_flag or "").strip())
        and _norm(break_flag) not in {"0", "false", "khong", "no"}
        and not str(clock_in_raw or "").strip()
    )
    clock_out_raw = _source_value(record, "Giờ ra")
    break_start_raw = clock_out_raw or (break_flag if not isinstance(break_flag, str) else "")
    break_started = _source_start(break_start_raw, now, None) if break_active and break_start_raw else None
    service = str(_source_value(record, "Dịch vụ") or "").strip()
    column_x_elapsed = _duration_value(_source_value(record, "TG Xông Hơi", "TG Xong Hoi"))
    is_steam_service = _norm(service) in {"xong hoi", "steam"}
    steam_elapsed = column_x_elapsed if is_steam_service else None
    wait_elapsed = None if is_steam_service else column_x_elapsed
    break_remaining = _number(_source_value(record, "Thời gian", "TG Break"), math.nan)
    break_remaining = break_remaining if math.isfinite(break_remaining) else math.nan
    tour_count = _number(_source_value(record, "SL tua"), 0)
    request_count = _number(_source_value(record, "SL yêu cầu"), 0)
    tour_count = tour_count if math.isfinite(tour_count) else 0
    request_count = request_count if math.isfinite(request_count) else 0
    status = str(_source_value(record, "Trạng thái") or "").strip()
    payment_raw = str(_source_value(record, "Chờ thanh toán", "TT thanh toán") or "").strip()
    payment_pending = _norm(payment_raw) in {"cho thanh toan", "chua thanh toan"}
    completion_note = "" if payment_pending else payment_raw
    if payment_pending:
        status = "CHO THANH TOÁN"
        payment_raw = "CHO THANH TOÁN"
    else:
        payment_raw = ""
    return {
        "id": _stable_id("employee", f"{stt}:{name}"), "stt": stt, "name": name,
        "appointment": str(_source_value(record, "Lịch hẹn") or "").strip(),
        "service": service,
        "request": request, "request_source": request_source,
        "room": str(_source_value(record, "Phòng") or "").strip(),
        "status": status,
        "duration": int(round(duration)) if duration is not None else None,
        "service_price": None, "service_price_source": "tour_import",
        "booked_at": _iso(booked) if booked else "", "started_at": _iso(started) if started else "", "completed_at": "",
        "payment_status": payment_raw,
        "completion_note": completion_note,
        "tour_count": int(round(tour_count)),
        "request_count": int(round(request_count)),
        "work_status": _source_work_status(_source_value(record, "Đi làm")),
        "shift": _source_shift(_source_value(record, "Vào ca", "Ca")),
        "break_started_at": _iso(break_started) if break_started else "",
        "clock_out": str(clock_out_raw or "").strip(),
        "clock_in": str(clock_in_raw or "").strip(),
        # Input!T is the VBA break countdown, while Input!X is elapsed steam
        # time.  They intentionally remain distinct from service wait_minutes.
        "break_remaining_minutes": None if math.isnan(break_remaining) else break_remaining,
        "steam_elapsed_minutes": steam_elapsed, "wait_minutes": wait_elapsed, "completion_delta_minutes": None,
        "note": str(_source_value(record, "Ghi chú") or "").strip(),
        "hidden": False, "vip": vip, "sort_index": index,
    }


def _employee_directory(conn, now=None) -> list[dict[str, Any]]:
    rows = [dict(row) for row in conn.execute(text("""
        SELECT username, COALESCE(full_name, '') AS full_name,
               lower(btrim(COALESCE(role,''))) AS role, COALESCE(payload,'{}'::jsonb) AS payload, COALESCE(work_shift,'') AS work_shift,
               shift_start_date, rotation_cycle,
               (SELECT value_json FROM vera_app_setting WHERE category='shift' AND setting_key='shift_definitions' LIMIT 1) AS shift_definitions
        FROM employees
        ORDER BY lower(username)
    """)).mappings().all()]
    return _directory_with_checkin(conn, rows, (now or datetime.now(VN_TZ)).astimezone(VN_TZ))


def _new_directory_employee(row, index):
    return {
        "id": _stable_id("employee", row["username"]),
        "username": row["username"], "name": row["username"], "role": row["role"],
        "stt": str(index + 1), "roster_eligible": True,
        "appointment": "", "service": "", "request": "", "room": "", "status": "",
        "duration": None, "service_price": 0, "booked_at": "", "started_at": "",
        "completed_at": "", "payment_status": "", "wait_minutes": None,
        "completion_delta_minutes": None, "steam_elapsed_minutes": None,
        "tour_count": 0, "request_count": 0, "work_status": "Nghỉ", "shift": _directory_shift(row.get("work_shift"), row.get("shift_definitions")),
        "break_started_at": "", "clock_out": "", "clock_in": "", "note": "",
        "hidden": False, "vip": False, "sort_index": index,
    }


def _database_employees(conn) -> list[dict[str, Any]]:
    return [_new_directory_employee(row, i) for i, row in enumerate(_employee_directory(conn)) if _roster_eligible(row)]


def _bootstrap_state(conn, now: datetime) -> dict[str, Any]:
    state = _empty_state(now)
    _reconcile_roster(
        state, _employee_directory(conn, now), _new_directory_employee,
        today=now.astimezone(VN_TZ).date().isoformat(),
    )
    state["bootstrap_source"] = "employees"
    state["storage_mode"] = "server"
    return state


def _find_by_id(items: list[dict[str, Any]], item_id: Any, label: str) -> dict[str, Any]:
    wanted = str(item_id or "").strip()
    item = next((row for row in items if str(row.get("id") or "") == wanted), None)
    if not item:
        raise HTTPException(404, f"Không tìm thấy {label}.")
    return item


def _employee(state: dict[str, Any], employee_id: Any) -> dict[str, Any]:
    return _find_by_id(state["employees"], employee_id, "nhân viên")


def _catalog_item(state: dict[str, Any], kind: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    items = state[kind]
    singular = {"services": "service", "rooms": "room", "combos": "combo"}[kind]
    item_id = payload.get(f"{singular}_id")
    name = payload.get(singular) or payload.get("name")
    if item_id:
        return _find_by_id(items, item_id, singular)
    if name:
        return next((item for item in items if _norm(item.get("name")) == _norm(name)), None)
    return None


def _active_booking(employee: dict[str, Any]) -> bool:
    # Completion releases the physical room while the row remains available
    # for payment/move-pending bookkeeping.
    return _norm(employee.get("status")) in {"dang cho", "dang thuc hien", "dang su dung"} and bool(employee.get("room"))


def _has_unsettled_work(employee: dict[str, Any]) -> bool:
    return bool(
        employee.get("service") or employee.get("break_started_at")
        or _norm(employee.get("status")) in {"dang cho", "dang thuc hien", "dang su dung", "cho thanh toan"}
        or _norm(employee.get("payment_status")) == "cho thanh toan"
    )


def _catalog_private_service(state: dict[str, Any], service: Any) -> bool:
    name = _norm(service)
    cache = getattr(state, 'private_services', None)
    if cache is not None and name in cache:
        return cache[name]
    result = _is_private_service(service) or any(
        item.get("private") and re.search(r"(?:^|\s*&\s*)" + re.escape(_norm(item.get("name"))) + r"(?:\s*&\s*|$)", name)
        for item in state["services"]
    )
    if cache is not None:
        cache[name] = result
    return result


def _catalog_referenced(state: d…53220 tokens truncated…       metrics = job_queue.health_metrics(engine_instance, PROJECTION_QUEUE)
                queue_alerts.monitor_once(engine_instance, PROJECTION_QUEUE, metrics)
            except Exception:
                logging.getLogger(__name__).exception("Live Tour queue alert monitor failed")
            scheduler_stop.wait(queue_alerts.MONITOR_SECONDS)

    def start_scheduler():
        nonlocal scheduler_thread, worker_thread, alert_thread
        # Fail startup before any background thread can touch a missing queue table.
        job_queue.ensure_schema(engine_instance)
        scheduler_stop.clear()
        scheduler_thread = Thread(target=scheduled_projection, name="live-tour-projection-scheduler", daemon=True)
        worker_thread = Thread(target=projection_worker, name="live-tour-projection-worker", daemon=True)
        alert_thread = Thread(target=queue_alert_monitor, name="live-tour-queue-alert-monitor", daemon=True)
        scheduler_thread.start()
        worker_thread.start()
        alert_thread.start()

    def stop_scheduler():
        scheduler_stop.set()
        for thread in (scheduler_thread, worker_thread, alert_thread):
            if thread:
                thread.join(timeout=2)

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def live_tour_lifespan(application):
        # Preserve the application's existing startup/shutdown and shared state.
        # FastAPI/Starlette no longer expose app.add_event_handler.
        async with previous_lifespan(application) as state:
            start_scheduler()
            try:
                yield state
            finally:
                stop_scheduler()

    app.router.lifespan_context = live_tour_lifespan

    def read_state(conn, now, *, for_update=False, attendance_records=_ATTENDANCE_UNSET, directory_records=None, leave_records=None):
        # Runtime callback uses the same installed policy chain as Chấm công.
        records = attendance_records
        if records is _ATTENDANCE_UNSET:
            records = attendance.read(conn, now.astimezone(timezone).date(), force=for_update) if attendance else None
        state, revision = _read_state(conn, now, for_update=for_update, attendance_records=records, directory_records=directory_records, leave_records=leave_records)
        if records is not None:
            before = deepcopy(state)
            sync_breaks(state, records, now.astimezone(timezone))
            if state != before:
                revision = _write_state_compat(
                    conn, state, revision, "attendance_break_projection", previous_state=before,
                )
        return state, revision

    def read_state_without_projection(conn, now, *, for_update=False):
        """Read the aggregate without attendance/directory/leave projection.

        Catalog, ordering and payment-setting mutations do not depend on a fresh
        attendance projection.  Keeping those SQL reads and possible projection
        writes outside their critical section materially shortens the global
        Live Tour lock while preserving revision/idempotency validation.
        """
        if resource_store.enabled():
            state, revision, _ = resource_store.read(conn)
            return _normalize_state(state, now), revision
        suffix = " FOR UPDATE" if for_update else ""
        row = conn.execute(text(f"""
            SELECT value_json, revision FROM vera_app_setting
            WHERE category=:category AND setting_key=:key{suffix}
        """), {"category": STATE_CATEGORY, "key": STATE_KEY}).mappings().first()
        if row:
            return _normalize_state(row.get("value_json"), now), int(row.get("revision") or 0)
        # Bootstrap is the only case where the full projection path is needed.
        return read_state(conn, now, for_update=for_update)

    def read_board_view(conn, now):
        collections = set(relational_store.RESOURCE_COLLECTIONS) - (_DETAIL_COLLECTIONS - {"pending", "combo_sale_requests"})
        if resource_store.enabled():
            state, revision, _ = resource_store.read(conn, collections=collections)
            return _normalize_state(state, now), revision
        omitted = sorted((_DETAIL_COLLECTIONS - {"pending", "combo_sale_requests"}) | {"idempotency"})
        # Static server-owned keys only; PostgreSQL strips history before sending
        # JSON to the application, avoiding decoding/copying the full ledger.
        keys = ",".join("'" + key + "'" for key in omitted)
        row = conn.execute(text(f"SELECT value_json - ARRAY[{keys}] AS value_json, revision FROM vera_app_setting WHERE category=:category AND setting_key=:key"), {"category":STATE_CATEGORY,"key":STATE_KEY}).mappings().first()
        if row:
            return _normalize_state(row["value_json"], now), int(row["revision"])
        return read_board(conn, now)

    def read_collections_view(conn, now, collections):
        if resource_store.enabled():
            state, revision, _ = resource_store.read(conn, collections=collections)
            return _normalize_state(state, now), revision
        return read_board(conn, now, project=False)

    def read_board(conn, now, *, project=True):
        if resource_store.enabled():
            # This helper is for views, exports and post-commit responses. All
            # business collections remain present; private replay receipts are
            # only needed by the separate locked mutation/projection readers.
            state, revision, _ = resource_store.read(conn, collections=relational_store.RESOURCE_COLLECTIONS)
            return _normalize_state(state, now), revision
        # Request threads only read the last committed board snapshot. Projection is
        # owned by the PostgreSQL queue worker, so GET traffic cannot extend STATE_LOCK.
        row = conn.execute(text("""
            SELECT value_json, revision FROM vera_app_setting
            WHERE category=:category AND setting_key=:key
        """), {"category": STATE_CATEGORY, "key": STATE_KEY}).mappings().first()
        if row:
            return _normalize_state(row.get("value_json"), now), int(row.get("revision") or 0)
        # First bootstrap is the only request-path projection and happens once.
        acquire_state_lock(conn, STATE_LOCK)
        return read_state(conn, now)

    def website_booking_staff():
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            state, _ = read_board(conn, now)
        employees = [
            {"value": str(row.get("username") or row.get("name") or "").strip(),
             "label": str(row.get("name") or row.get("username") or "").strip()}
            for row in state.get("employees", [])
            if row.get("roster_eligible") is not False
            and _norm(row.get("work_status")) == "di lam"
            and (row.get("username") or row.get("name"))
        ]
        employees.sort(key=lambda item: _norm(item["label"]))
        return {"date": now.astimezone(VN_TZ).date().isoformat(), "employees": employees}

    def record_website_booking_appointment(employee_username, appointment_date, appointment_time):
        now = datetime.now(timezone)
        if appointment_date != now.astimezone(VN_TZ).date():
            return {"applied": False, "reason": "not_today"}
        wanted = _norm(employee_username)
        if not wanted:
            return {"applied": False, "reason": "staff_not_selected"}
        with engine_instance().begin() as conn:
            if resource_store.enabled():
                resource_store.lock(conn)
            else:
                acquire_state_lock(conn, STATE_LOCK)
            state, revision = read_state(conn, now, for_update=True)
            employee = next((row for row in state["employees"]
                             if wanted in {_norm(row.get("username")), _norm(row.get("name"))}), None)
            if (not employee or employee.get("roster_eligible") is False
                    or _norm(employee.get("work_status")) != "di lam"):
                return {"applied": False, "reason": "staff_no_longer_working"}

            token = f"YC {appointment_time}"
            day = appointment_date.isoformat()
            previous_day = str(employee.get("_website_booking_appointment_day") or "")
            values = list(employee.get("_website_booking_appointment_values") or []) if previous_day == day else []
            current = str(employee.get("appointment") or "").strip()
            if token not in values:
                addition = f" · {token}" if current else token
                if len(current) + len(addition) > 200:
                    return {"applied": False, "reason": "appointment_field_full"}
                previous = deepcopy(state)
                employee["appointment"] = current + addition
                values.append(token)
                employee["_website_booking_appointment_day"] = day
                employee["_website_booking_appointment_values"] = values
                _audit(state, "website_booking_appointment", {
                    "employee_id": employee["id"], "appointment_date": day,
                    "appointment_time": appointment_time,
                }, "website_booking", now)
                _write_state_compat(conn, state, revision, "website_booking", previous_state=previous)
        return {"applied": True, "employee": str(employee.get("username") or employee.get("name") or "")}

    app.state.website_booking_staff_provider = website_booking_staff
    app.state.website_booking_appointment_writer = record_website_booking_appointment

    def permissions(conn, ident) -> dict[str, bool]:
        viewer_bank = None
        if feature_allowed(conn, ident, "live_tour_payment"):
            bank_row = conn.execute(text("SELECT full_name, bank_name, bank_account FROM employees WHERE username=:username"), {"username": ident.employee_username}).mappings().first()
            viewer_bank = _profile_bank(dict(bank_row)) if bank_row else None
        can_admin = bool(feature_allowed(conn, ident, "live_tour_admin"))
        can_operate = bool(feature_allowed(conn, ident, "live_tour_operate"))
        return {
            "can_appointment_edit": str(getattr(ident, "role", "") or "").strip().lower() in {"admin", "quanly", "letan"} and bool(feature_allowed(conn, ident, "live_tour_view")),
            "viewer_bank": viewer_bank,
            "can_admin": can_admin, "can_operate": can_operate,
            "can_payment": bool(feature_allowed(conn, ident, "live_tour_payment")),
            "can_export": bool(feature_allowed(conn, ident, "live_tour_export")),
            **{f"can_{name}": bool(feature_allowed(conn, ident, feature)) for name, feature in CAPABILITY_FEATURES.items()},
        }

    def action_response(
        *, state: dict[str, Any], revision: int, now: datetime, action: str,
        result: dict[str, Any], grants: dict[str, bool], duplicate: bool = False, response_view: str = "full",
    ) -> dict[str, Any]:
        def readable_result(value):
            if isinstance(value, list):
                return [readable_result(row) for row in value]
            if not isinstance(value, dict):
                return deepcopy(value)
            public = {}
            for key, nested in value.items():
                if key == "invoice":
                    if not grants.get("can_paid_invoice_view"):
                        continue
                    # Never print a superseded/voided receipt on a retry.
                    invoice_id = nested.get("id") if isinstance(nested, dict) else None
                    public[key] = deepcopy(next((row for row in state["invoices"] if row.get("id") == invoice_id), None))
                    if invoice_id and public[key] is None:
                        public["voided"] = True
                elif key == "pending" and isinstance(nested, dict):
                    pending = next((row for row in state["pending"] if row.get("id") == nested.get("id")), None)
                    public[key] = deepcopy(pending) if pending and grants.get("can_invoice_view") and grants.get("can_pending_view") else {"id": nested.get("id")}
                elif key in {"customer", "purchase", "customers", "combo_purchase"} and not grants.get("can_customers_view"):
                    continue
                else:
                    public[key] = readable_result(nested)
            return public
        public_result = readable_result(result)
        if not (grants.get("can_customers_view") or grants.get("can_invoice_view") or grants.get("can_paid_invoice_view")):
            public_result = _redact_customer_pii(public_result)
        if response_view == "receipt":
            # The payment transaction has committed before this response is
            # sent. Board/list reads are independent client requests.
            return {"ok": True, "duplicate": duplicate, "action": action,
                    "revision": revision, "result": public_result, "refresh_board": True,
                    **({"message": str(result["message"])} if result.get("message") else {})}
        return {
            "ok": True, "duplicate": duplicate, "action": action,
            "revision": revision, "result": public_result,
            **({"message": str(result.get("message"))} if result.get("message") else {}),
            **({"capabilities": {name: grants[f"can_{name}"] for name in CAPABILITY_FEATURES}} if action.startswith("report_invoice_") else (_board_response if response_view == "board" else _state_response)(state, revision, now, **grants)),
        }

    @app.get("/v2/live-tour")
    def live_tour(
        refresh: bool = Query(default=False),
        view: str = Query(default="full", pattern="^(full|board)$"),
        known_revision: int | None = Query(default=None, ge=0),
        include_hidden: bool = Query(default=False),
        ident: identity_type = Depends(current_identity),
    ):
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_view")
            # The board polls every few seconds on every open device.  Avoid
            # deserializing, projecting and serializing the complete aggregate
            # when the browser already has the current committed revision.
            if known_revision is not None and not refresh:
                if resource_store.enabled():
                    current_revision = conn.execute(text(f"SELECT aggregate_revision FROM {relational_store.META_TABLE} WHERE singleton=1")).scalar_one_or_none()
                else:
                    current_revision = conn.execute(text("""
                        SELECT revision FROM vera_app_setting
                        WHERE category=:category AND setting_key=:key
                    """), {"category": STATE_CATEGORY, "key": STATE_KEY}).scalar_one_or_none()
                if current_revision is not None and int(current_revision) == known_revision:
                    return {"unchanged": True, "revision": int(current_revision), "countdown_at": _iso(now)}
            # First loads and deliberate refreshes preserve the existing fresh
            # projection behavior. A conditional poll whose revision changed
            # reads the newly committed snapshot; the scheduler already owns
            # routine projection and other devices need not repeat it.
            state, revision = read_board_view(conn, now) if view == "board" else read_board(
                conn, now, project=refresh or known_revision is None,
            )
            grants = permissions(conn, ident)
        return (_board_response if view == "board" else _state_response)(
            state, revision, now, include_hidden=include_hidden,
            **grants,
        )

    @app.get("/v2/live-tour/collections/{panel}")
    def live_tour_collection(
        panel: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
        search: str = Query(default="", max_length=200), customer_id: str = "",
        customer_ids: str = Query(default="", max_length=8000),
        date_from: str = "", date_to: str = "", employee: str = "", customer: str = "", service: str = "", bill_no: str = "",
        ident: identity_type = Depends(current_identity),
    ):
        groups = {"customers": ("customers",), "pending": ("pending",), "invoices": ("invoices",),
                  "reports": ("reports",), "history": ("audit", "break_events", "pending_changes", "invoice_changes", "customer_changes", "backups")}
        features = {"customers":"live_tour_customers_view", "pending":"live_tour_pending_view", "invoices":"live_tour_paid_invoice_view", "reports":"live_tour_reports_view", "history":"live_tour_history_view"}
        if panel not in groups:
            raise HTTPException(404, "Không có danh sách này.")
        selected_customer_ids = {value.strip() for value in customer_ids.split(",") if value.strip()}
        if len(selected_customer_ids) > 50 or any(len(value) > 160 for value in selected_customer_ids):
            raise HTTPException(400, "Chỉ tải tối đa 50 khách hàng đã chọn mỗi lần.")
        bounds = _parse_export_bounds(date_from=date_from,date_to=date_to)
        bounds.update(employee=employee,customer=customer,service=service,bill_no=bill_no,calendar_date=True)
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_view")
            if panel == "history" and feature_allowed(conn, ident, "live_tour_backup"):
                pass
            else:
                require_feature(conn, ident, features[panel])
            if panel == "pending":
                require_feature(conn, ident, "live_tour_invoice_view")
            if resource_store.enabled():
                # Read only this panel and its response dependencies in one MVCC
                # snapshot. In particular, ordinary lists must not fetch backups,
                # unrelated ledgers or the private idempotency response cache.
                collections = set(relational_store.RESOURCE_COLLECTIONS) - _DETAIL_COLLECTIONS
                collections.update(groups[panel])
                if panel == "customers":
                    collections.add("pending")  # All outstanding combo reservations.
                if panel == "reports":
                    collections.add("invoices")  # Receipt and combo-kind lookup.
                state, revision, _ = resource_store.read(conn, collections=collections)
            else:
                state, revision = read_board(conn, now, project=False)
            grants = permissions(conn, ident)
        # Filter/slice detached rows first; normalize only the requested page.
        selected = {**state, **{key: [] for key in _DETAIL_COLLECTIONS}, "idempotency": {}}
        totals = {}
        report_totals = None
        for key in groups[panel]:
            allowed = {"audit": grants.get("can_history_view"), "break_events": grants.get("can_history_view"),
                       "pending_changes": grants.get("can_history_view") and grants.get("can_pending_view") and grants.get("can_invoice_view"),
                       "invoice_changes": grants.get("can_history_view") and grants.get("can_paid_invoice_view"),
                       "customer_changes": grants.get("can_history_view") and grants.get("can_customers_view"), "backups": grants.get("can_backup")}
            values = state.get(key, []) if allowed.get(key, True) else []
            if key == "customers":
                values = [row for row in values if not row.get("deleted_at") and (not customer_id or str(row.get("id")) == customer_id)
                          and (not selected_customer_ids or str(row.get("id")) in selected_customer_ids)
                          and list_queries.customer_matches(row,search)]
            else:
                values = [row for row in values if list_queries.matches(row,date_from=date_from,date_to=date_to,employee=employee,customer=customer,service=service,bill_no=bill_no,history=panel=="history",invoice_dates=panel in {"reports","invoices"})]
            # Preserve source ordering inside each page, newest pages first.
            totals[key] = len(values)
            if key == "reports":
                total = sum(float(row.get("total") or 0) for row in values)
                tip = sum(float(row.get("tip") or 0) for row in values)
                report_totals = {"totalRevenue":total,"tip":tip,"serviceRevenue":total-tip,"invoiceCount":len({row.get("invoice_id") or row.get("bill_no") for row in values if row.get("invoice_id") or row.get("bill_no")})}
            end = max(0, len(values) - (page-1)*page_size)
            selected[key] = values[max(0,end-page_size):end]
        if panel == "customers":
            # Reservation amounts include ALL open assignments, not just a page.
            selected["pending"] = state["pending"]
        if panel == "reports":
            invoice_ids = {row.get("invoice_id") for row in selected["reports"]}
            selected["invoices"] = [row for row in state["invoices"] if row.get("id") in invoice_ids]
        selected = _normalize_state(selected, now)
        public = _state_response(selected, revision, now, **grants)
        fields = {"customers":["customers"], "pending":["pending_payments","pending"], "invoices":[],
                  "reports":["report_rows","reports"], "history":["audit","history","break_events","pending_changes","invoice_changes","customer_changes","backups"]}[panel]
        data = {key:public[key] for key in fields}
        data["state"] = {key:public["state"].get(key,[]) for key in groups[panel] if key in public["state"]}
        if panel == "reports":
            data["state"]["invoices"] = public["state"]["invoices"]
            data["report_totals"] = report_totals
        return {"revision":revision,"data":data,"page":page,"page_size":page_size,"total":sum(totals.values()),
                "pages":max(1,max(((total+page_size-1)//page_size for total in totals.values()),default=1))}

    @app.get("/v2/live-tour/reports")
    def live_tour_reports(ident: identity_type = Depends(current_identity)):
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_reports_view")
            state, revision = read_collections_view(conn, now, {"employees", "rooms", "services", "combos", "pending", "invoices", "reports"})
            grants = permissions(conn, ident)
        public = _state_response(state, revision, now, **grants)
        is_admin = str(getattr(ident, "role", "") or "").strip().lower() == "admin"
        return {"revision": revision, "invoices": public["state"]["invoices"],
                "reports": public["report_rows"], "performance": _service_performance_rows(state) if is_admin else [],
                "capabilities": public["capabilities"], "payment_settings": public["payment_settings"]}

    @app.get("/v2/live-tour/board-history")
    def live_tour_board_history(
        date_from: date | None = Query(default=None), date_to: date | None = Query(default=None),
        employee: str = Query(default="", max_length=200), ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_reports_view")
            rows = _board_history_rows(conn, date_from=date_from, date_to=date_to, employee=employee)
        return {"ok": True, "columns": BOARD_COLUMNS, "rows": rows, "count": len(rows)}

    @app.get("/v2/live-tour/board-history/export.xlsx")
    def live_tour_board_history_export(
        date_from: date | None = Query(default=None), date_to: date | None = Query(default=None),
        employee: str = Query(default="", max_length=200), ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_reports_view")
            require_feature(conn, ident, "live_tour_export")
            rows = _board_history_rows(conn, date_from=date_from, date_to=date_to, employee=employee)
        content = _board_history_excel(rows)
        filename = f"VERA_LichSu_LiveTour_{datetime.now(VN_TZ):%d-%m-%Y}.xlsx"
        return StreamingResponse(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    @app.get("/v2/live-tour/my-tips")
    def live_tour_my_tips(ident: identity_type = Depends(current_identity)):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role not in {"leader", "nhanvien"}:
            raise HTTPException(403, "Chỉ tài khoản Leader và Nhân viên được xem Trà sữa của chính mình.")
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            state, revision = read_collections_view(conn, now, {'reports'})
        rows = _personal_tip_rows(state, str(ident.employee_username or ""))
        return {"revision": revision, "employee_username": ident.employee_username,
                "rows": rows, "total_tip": sum(int(row.get("tip") or 0) for row in rows)}

    @app.get("/v2/live-tour/customers")
    def spa_customers(ident: identity_type = Depends(current_identity)):
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_customers_view")
            state, revision = read_collections_view(conn, now, {'customers', 'combos'})
            can_export = bool(feature_allowed(conn, ident, "live_tour_export"))
        is_admin = str(getattr(ident, "role", "") or "").strip().lower() == "admin"
        return {"revision": revision, "customers": [dict(deepcopy(c), combo_purchases=[deepcopy(p) for p in c.get("combo_purchases", []) if not p.get("deleted_at")]) for c in state["customers"] if not c.get("deleted_at")], "combo_catalog": deepcopy(state["combos"]) if is_admin else [], "can_export": can_export}

    @app.get("/v2/live-tour/settings")
    def spa_settings(ident: identity_type = Depends(current_identity)):
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_admin")
            state, revision = read_collections_view(conn, now, {'rooms', 'services', 'combos'})
        return {"revision": revision, "services": deepcopy(state["services"]), "combos": deepcopy(state["combos"]), "service_areas": _service_areas(state)}

    @app.get("/v2/live-tour/customers/{customer_id}/history")
    def live_tour_customer_history(
        customer_id: str,
        ident: identity_type = Depends(current_identity),
    ):
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_customers_view")
            state, _ = read_board(conn, now, project=False)
            grants = permissions(conn, ident)
        readable = deepcopy(state)
        if not grants["can_paid_invoice_view"]:
            readable["invoices"] = []
        if not (grants["can_pending_view"] and grants["can_invoice_view"]):
            readable["pending"] = []
        if not grants["can_reports_view"]:
            readable["reports"] = []
        history = _customer_history(readable, customer_id)
        if not grants["can_paid_invoice_view"]:
            for key in ("invoice_count", "service_count", "total_revenue", "total_tip"):
                history["summary"].pop(key, None)
        if not (grants["can_pending_view"] and grants["can_invoice_view"]):
            history["summary"].pop("pending_count", None)
        return {**history, "capabilities": {
            name: grants[f"can_{name}"] for name in CAPABILITY_FEATURES
        }}

    @app.post("/v2/live-tour/action")
    def live_tour_action(body: LiveTourAction, ident: identity_type = Depends(current_identity)):
        now = datetime.now(timezone)
        action = body.action.strip().lower()
        timing = ActionTiming(action)
        _reject_external_action(action)
        if action == "set_shift" and str(getattr(ident, "role", "") or "").strip().lower() not in {"admin", "quanly", "letan"}:
            raise HTTPException(403, "Chỉ Admin, Quản lý và Lễ tân được xếp Ca 1/Ca 2 thủ công.")
        if action == "update_appointment" and str(getattr(ident, "role", "") or "").strip().lower() not in {"admin", "quanly", "letan"}:
            raise HTTPException(403, "Chỉ Lễ tân, Quản lý và Admin được sửa lịch hẹn.")
        if action == "update_started_at" and str(getattr(ident, "role", "") or "").strip().lower() not in {"admin", "quanly"}:
            raise HTTPException(403, "Chỉ Admin và Quản lý được nhập TG bắt đầu thực hiện.")
        if action == "combo_sale_decide" and str(getattr(ident, "role", "") or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được duyệt hoặc từ chối yêu cầu bán combo.")
        if action == "customer_combo_update" and str(getattr(ident, "role", "") or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được sửa loại combo và số vé còn lại.")
        payload = deepcopy(body.payload)
        sharing = [payload, *[row for row in (payload.get("bookings") or []) if isinstance(row, dict)]]
        if any(row.get("share_private_room") for row in sharing):
            if action not in {"booking", "multi_booking"} or str(getattr(ident, "role", "") or "").strip().lower() not in {"admin", "quanly", "letan"}:
                raise HTTPException(403, "Chỉ Lễ tân, Quản lý và Admin được chủ động đặt chung phòng PR.")
        actor = str(ident.employee_username or ident.full_name or "web_v2")
        idempotency_key = str(body.idempotency_key or payload.get("idempotency_key") or "").strip()
        if idempotency_key and not 8 <= len(idempotency_key) <= 160:
            raise HTTPException(400, "idempotency_key phải có từ 8 đến 160 ký tự.")
        if action in IDEMPOTENCY_REQUIRED_ACTIONS and not idempotency_key:
            raise HTTPException(400, "Mọi thao tác thay đổi Live Tour cần idempotency_key để chống ghi trùng.")
        payload_hash = _canonical_payload_hash(action, payload)
        with timing.transaction(engine_instance()) as conn:
            manual_break_allowed = action == "end_break" and str(getattr(ident, "role", "") or "").strip().lower() in {"admin", "letan", "quanly"}
            if not manual_break_allowed:
                require_feature(conn, ident, "live_tour_customers_edit" if action == "customer_upsert" and payload.get("customer_id") else _required_action_feature(action))
            if action in {"booking", "multi_booking"}:
                require_feature(conn, ident, "live_tour_view")
            if "quick_booking" in payload:
                if action != "quick_checkout":
                    raise HTTPException(400, "Nhập booking trực tiếp chỉ dùng trong Thanh toán nhanh.")
                require_feature(conn, ident, "live_tour_booking")
                require_feature(conn, ident, "live_tour_view")
                _quick_booking_at(payload["quick_booking"], now)
                entered = _parse_datetime(payload["quick_booking"]["booked_at"])
                if entered.date() < now.astimezone(VN_TZ).date():
                    require_feature(conn, ident, "live_tour_admin")
            if action in {"booking", "multi_booking", "update_booking"} and (
                payload.get("start_now") or any(row.get("start_now") for row in (payload.get("bookings") or []) if isinstance(row, dict))
            ):
                require_feature(conn, ident, "live_tour_operate")
            if action == "pending_update" and ({"customer_id", "combo_purchase_id"} & payload.keys()):
                require_feature(conn, ident, "live_tour_customers_view")
            if action in {"pending_update", "pending_delete"} or (action in {"checkout", "quick_checkout"} and payload.get("pending_id")):
                require_feature(conn, ident, "live_tour_pending_view")
                require_feature(conn, ident, "live_tour_invoice_view")
            if action in {"report_invoice_update", "report_invoice_delete"}:
                require_feature(conn, ident, "live_tour_reports_view")
                require_feature(conn, ident, "live_tour_paid_invoice_view")
            if "invoice_at" in payload:
                require_feature(conn, ident, "live_tour_invoice_date_edit")
            if action == "customer_upsert" and payload.get("customer_id"):
                require_feature(conn, ident, "live_tour_customers_edit")
            if action in {"customer_delete", "customer_combo_update", "customer_combo_delete"}:
                require_feature(conn, ident, "live_tour_customers_view")
            if action in {"paid_invoice_update", "paid_invoice_delete"}:
                require_feature(conn, ident, "live_tour_paid_invoice_view")
            if action in BACKDATE_ACTIONS and _backdate_requested(payload):
                # Lùi ngày changes the financial ledger date and therefore
                # requires both the normal payment grant and the admin grant.
                require_feature(conn, ident, "live_tour_admin")
            if action in {"booking", "multi_booking", "update_booking", "finish_to_pending"} and (
                _contains_customer_pii(payload) or "combo_purchase_id" in payload
                or any("combo_purchase_id" in row for row in (payload.get("bookings") or []) if isinstance(row, dict))
            ):
                require_feature(conn, ident, "live_tour_customers_view")
            if action == "combo_import":
                require_feature(conn, ident, "live_tour_payment")
            if action in {"combo_import", "combo_purchase", "combo_sale_decide", "customer_upsert"}:
                require_feature(conn, ident, "live_tour_customers_view")
            if action == "combo_sale_decide":
                require_feature(conn, ident, "live_tour_payment")
            if action in {"checkout", "quick_checkout"} and _contains_customer_pii(payload):
                require_feature(conn, ident, "live_tour_customers_view")
            # Build response capabilities before entering the global state
            # critical section. Some grants read employee/payment metadata.
            grants = permissions(conn, ident)
            timing.mark('authorize')
            if action == "sync_daily_status":
                state, revision = read_board(conn, now, project=False)
                if body.expected_revision is None:
                    raise HTTPException(428, "Thiếu phiên bản Live Tour. Hãy tải lại bảng trước khi thao tác.")
                if body.expected_revision != revision:
                    raise HTTPException(409, "Live Tour đã thay đổi ở thiết bị khác. Hãy làm mới rồi thao tác lại.")
                job_queue.enqueue_conn(
                    conn, PROJECTION_QUEUE, f"manual:{idempotency_key}",
                    {"reason": "manual", "actor": actor, "requested_at": now.isoformat()},
                )
                return action_response(
                    state=state, revision=revision, now=now, action=action,
                    result={"queued": True, "refresh_seconds": PROJECTION_REFRESH_SECONDS}, grants=grants, response_view=body.response_view,
                )
            resource_fresh = False
            if resource_store.enabled():
                state, revision, resource_fresh = resource_store.begin_action(
                    conn, action, payload, body.expected_revision, idempotency_key,
                    _counter_business_date(now).isoformat(),
                    compact=body.response_view in {"receipt", "board"},
                )
                state = _normalize_state(state, now)
            else:
                acquire_state_lock(conn, STATE_LOCK)
                state, revision = read_state_without_projection(conn, now, for_update=True)
            timing.mark('lock_read')
            previous = _idempotency_replay(
                state, idempotency_key, action=action, actor=actor, payload_hash=payload_hash,
            )
            if previous:
                return action_response(
                    state=state, revision=revision, now=now, action=action,
                    result=deepcopy(previous.get("result") or {}), grants=grants, duplicate=True, response_view=body.response_view,
                )
            if body.expected_revision is None:
                raise HTTPException(428, "Thiếu phiên bản Live Tour. Hãy tải lại bảng trước khi thao tác.")
            # Check the submitted area version even when the board revision is
            # current: refreshing the list must not rebase an unsaved stale form.
            area_fresh = _area_precondition(state, action, payload)
            if body.expected_revision != revision and not resource_fresh and not (area_fresh and body.expected_revision <= revision):
                raise HTTPException(409, "Live Tour đã thay đổi ở thiết bị khác. Hãy làm mới rồi thao tác lại.")
            if action == "clear_expired_preview":
                return {"ok": True, "base_revision": revision, **_expired_preview(state, payload, now)}
            # A defensive copy guarantees multi-step actions never leak a partial
            # mutation into the value written after an exception.
            working = deepcopy(state)
            payload.pop("_manual_break_allowed", None)
            payload.pop("_admin_start", None)
            if action in {"start", "start_room"} and _can_start_outside_shift(
                getattr(ident, "role", ""), grants.get("can_start_outside_shift", False),
                datetime.now(timezone),
            ):
                payload["_admin_start"] = True
            if manual_break_allowed:
                payload["_manual_break_allowed"] = True
            if action == "combo_purchase":
                payload["_actor_role"] = str(getattr(ident, "role", "") or "").strip().lower()
            # Authority comes exclusively from the authenticated identity, never
            # from a payload flag, an account name or a delegated feature grant.
            result = _apply_action(working, action, payload, actor, now,
                                   admin_invoice_override=str(getattr(ident, "role", "") or "").strip().lower() == "admin")
            timing.mark('apply')
            if action in {"checkout", "quick_checkout", "combo_purchase", "combo_sale_decide"} and result.get("invoice"):
                bank = _selected_bank(working.get("payment_settings") or {}, grants.get("viewer_bank"), payload.get("bank_selection", "auto"))
                result["invoice"]["payment_bank"] = bank
                for invoice in working["invoices"]:
                    if invoice["id"] == result["invoice"]["id"]:
                        invoice["payment_bank"] = deepcopy(bank)
            if idempotency_key:
                _remember_idempotency(
                    working, idempotency_key, action=action, actor=actor,
                    payload_hash=payload_hash, result=result, now=now,
                )
            # ``state`` is the locked pre-mutation snapshot.  Passing it to the
            # shadow synchronizer avoids a second full JSON aggregate SELECT and
            # normalization while the global board lock is held.
            if action in {'booking', 'multi_booking'}:
                from vera_live_tour_booking_notifications import enqueue_bookings
                enqueue_bookings(conn, action, result, idempotency_key)
            next_revision = _write_state_compat(
                conn, working, revision, actor, previous_state=state,
            )
            timing.mark('write')
        timing.mark('commit')
        if resource_store.enabled() and body.response_view != "receipt":
            with timing.transaction(engine_instance()) as response_conn:
                if body.response_view == "board" and action in resource_store.OPERATIONAL_ACTIONS:
                    working, next_revision = read_board_view(response_conn, now)
                else:
                    working, next_revision = read_board(response_conn, now, project=False)
        timing.mark('response_read')
        response = action_response(
            state=working, revision=next_revision, now=now, action=action,
            result=result, grants=grants, response_view=body.response_view,
        )
        timing.mark('render')
        timing.emit()
        return response

    @app.get("/v2/live-tour/projection-queue/health")
    def live_tour_projection_queue_health():
        metrics = job_queue.health_metrics(engine_instance, PROJECTION_QUEUE)
        alerting = queue_alerts.health_status(engine_instance, PROJECTION_QUEUE, metrics)
        return {
            "ok": not alerting["active"], "release": PROJECTION_RELEASE,
            "queue_release": job_queue.RELEASE,
            "refresh_seconds": PROJECTION_REFRESH_SECONDS,
            "claim_strategy": "for_update_skip_locked",
            "counts": job_queue.counts(engine_instance, PROJECTION_QUEUE),
            **metrics,
            "alerting": alerting,
        }

    @app.get("/v2/live-tour/recovery")
    def live_tour_recovery(ident: identity_type = Depends(current_identity)):
        role = str(getattr(ident, "role", "") or "").strip().lower()
        if role != "admin":
            raise HTTPException(403, "Chỉ Admin được xem khôi phục Live Tour.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_view")
        # Each query closes its connection before the next one starts.
        return {
            "counts": job_queue.counts(engine_instance, PROJECTION_QUEUE),
            "metrics": job_queue.health_metrics(engine_instance, PROJECTION_QUEUE),
            "history": job_queue.recovery_history(engine_instance, PROJECTION_QUEUE),
            "can_recover": role == "admin",
        }

    @app.post("/v2/live-tour/recovery/retry")
    def live_tour_recovery_retry(ident: identity_type = Depends(current_identity)):
        if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được thử lại tác vụ quá hạn.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_admin")
        actor = str(ident.employee_username or ident.full_name or "admin")
        return job_queue.recover_expired(engine_instance, PROJECTION_QUEUE, actor)

    @app.get("/v2/live-tour/export.xlsx")
    def live_tour_export_excel(
        kind: str = Query(default="board"), include_hidden: bool = Query(default=False),
        date_from: str = Query(default=""), date_to: str = Query(default=""),
        time_from: str = Query(default=""), time_to: str = Query(default=""),
        customer_id: str = Query(default=""),
        employee: str = "", customer: str = "", service: str = "", bill_no: str = "",
        report_kind: str = "", performance_timing: str = "",
        total_amount: int | None = Query(default=None, ge=0, le=MAX_MONEY),
        tip_amount: int | None = Query(default=None, ge=0, le=MAX_MONEY),
        columns: list[str] | None = Query(default=None),
        employee_ids: list[str] | None = Query(default=None),
        ident: identity_type = Depends(current_identity),
    ):
        now = datetime.now(timezone)
        export_kind = kind.strip().lower()
        if export_kind not in {
            "board", "custom", "revenue", "tip", "reports", "customers", "pending", "history",
            "breaks", "customer_detail", "performance", "employee",
        }:
            raise HTTPException(400, "Loại báo cáo Live Tour không hợp lệ.")
        customer_id_value = str(customer_id or "").strip()
        if export_kind == "customer_detail" and not customer_id_value:
            raise HTTPException(400, "Xuất lịch sử khách hàng cần customer_id.")
        bounds = _parse_export_bounds(
            date_from=date_from.strip(), date_to=date_to.strip(),
            time_from=time_from.strip(), time_to=time_to.strip(),
        )
        bounds['tip_amount'] = tip_amount
        bounds.update(total_amount=total_amount, employee=employee.strip(), customer=customer.strip(), service=service.strip(), bill_no=bill_no.strip(), report_kind=report_kind.strip(), performance_timing=performance_timing.strip().lower(), calendar_date=export_kind in {"revenue", "tip", "reports", "pending", "performance", "employee"}, invoice_dates=export_kind in {"revenue", "tip", "reports", "employee"})
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_export")
            for feature in EXPORT_FEATURES.get(export_kind, ()):
                require_feature(conn, ident, feature)
            state, _ = read_board(conn, now)
            can_admin = feature_allowed(conn, ident, "live_tour_admin")
            can_recover_hidden = can_admin or feature_allowed(conn, ident, "live_tour_operate")
            grants = permissions(conn, ident)
        if export_kind == "history":
            state = deepcopy(state)
            state["audit"] = _readable_audit(state["audit"], invoice_view=grants["can_invoice_view"] and grants["can_pending_view"],
                                             paid_invoice_view=grants["can_paid_invoice_view"], customers_view=grants["can_customers_view"])
        elif export_kind == "revenue" and not (grants["can_customers_view"] or grants["can_paid_invoice_view"]):
            state = deepcopy(state)
            state["invoices"] = _redact_customer_pii(state["invoices"])
        elif export_kind == "reports" and not (grants["can_customers_view"] or grants["can_paid_invoice_view"]):
            state = deepcopy(state)
            state["reports"] = _redact_customer_pii(state["reports"])
        content, filename = _excel_bytes(
            state, export_kind, now, include_hidden=bool(include_hidden and can_recover_hidden),
            bounds=bounds, customer_id=customer_id_value, selected_columns=columns, employee_ids=employee_ids,
        )
        return StreamingResponse(
            BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    @app.post("/v2/live-tour/import.xlsx")
    async def live_tour_import_excel(
        request: Request,
        expected_revision: int = Query(..., ge=0),
        ident: identity_type = Depends(current_identity),
    ):
        if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được Import Excel vào Bảng tua.")
        length = int(request.headers.get("content-length") or 0)
        if length > 5 * 1024 * 1024:
            raise HTTPException(413, "File Excel vượt quá 5 MB.")
        content = await request.body()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(413, "File Excel vượt quá 5 MB.")
        rows = _board_import_rows(content)
        now = datetime.now(timezone)
        actor = str(ident.employee_username or ident.full_name or "web_v2")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_admin")
            if resource_store.enabled():
                resource_store.lock(conn)
            else:
                acquire_state_lock(conn, STATE_LOCK)
            state, revision = read_state(conn, now, for_update=True)
            if expected_revision != revision:
                raise HTTPException(409, "Live Tour đã thay đổi ở thiết bị khác. Hãy làm mới rồi Import lại.")
            working = deepcopy(state)
            imported = _import_board_into_state(working, rows, now)
            working["updated_at"] = _iso(now)
            working["business_date"] = _business_date(now).isoformat()
            _audit(working, "board_excel_import", {"imported": imported}, actor, now)
            next_revision = _write_state_compat(
                conn, working, revision, actor, previous_state=state,
            )
            grants = permissions(conn, ident)
        response = _state_response(working, next_revision, now, **grants)
        return {**response, "ok": True, "imported": imported, "message": f"Đã Import và lưu {imported} nhân viên vào Bảng tua."}

    @app.get("/v2/live-tour/export.png")
    def live_tour_export_png(
        kind: str = Query(default="board"), include_hidden: bool = Query(default=False),
        ident: identity_type = Depends(current_identity),
    ):
        if kind.strip().lower() != "board":
            raise HTTPException(400, "Export PNG hiện chỉ hỗ trợ Bảng tua.")
        now = datetime.now(timezone)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "live_tour_export")
            state, _ = read_board(conn, now)
            can_admin = feature_allowed(conn, ident, "live_tour_admin")
            can_recover_hidden = can_admin or feature_allowed(conn, ident, "live_tour_operate")
        filename = f"Live_Tour_{_business_date(now).strftime('%Y%m%d')}.png"
        return StreamingResponse(
            BytesIO(_png_bytes(state, now, include_hidden=bool(include_hidden and can_recover_hidden))), media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    app.state.live_tour_installed = True

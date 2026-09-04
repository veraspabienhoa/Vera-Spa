"""Same-day outside-break restriction for late/early leave records.

Business rule:
- Only the explicitly configured same-day Đi trễ/Về sớm registration reasons
  restrict the normal outside/mid-shift break. Automatic attendance violations
  such as "Đi trễ nhỏ hơn hoặc bằng 30 phút" do not remove that entitlement.
- TimeSoft remains the first source of the actual outside time; the attendance
  break stack may then fall back to TourVera R=Break, S=Giờ ra, U=Giờ vào.
- A Về sớm record that already existed before a TimeSoft checkout at/after
  17:00 means that FaceID is the employee's final early checkout, not a break.
- If the employee went outside first and the late/early record was entered
  afterwards, Auto Check still catches it on the next attendance poll.
  Violation minutes are calculated from the actual Giờ ra through 17:00.
- If a real outside Giờ ra is after 17:00, use
  "Ra ngoài chỉ có dữ liệu một lần".

The module wraps snapshot._records after TimeSoft/TourVera break reconstruction,
so it works for both the CHẤM CÔNG screen and the break-alert poller without
changing either data source.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import math
import unicodedata
from typing import Any, Callable

from sqlalchemy import text

import vera_auto_check as auto_check
import vera_auto_penalty_notifications as penalty_notifications
import vera_web_v2_attendance_break_alerts as break_alerts
import vera_web_v2_snapshot as snapshot


RELEASE = "outside-leave-restriction-2026-09-04-v5-exact-reasons"
VN_TZ = timezone(timedelta(hours=7))
CUTOFF = time(17, 0, 0)


RESTRICTED_LEAVE_REASONS = {
    "Đi trễ CÓ phép",
    "Đi trễ KHÔNG phép",
    "Đi trễ CUỐI TUẦN CÓ phép",
    "Đi trễ CUỐI TUẦN KHÔNG phép",
    "Đi trễ phát sinh",
    "Leader đi trễ sớm theo chính sách",
    "Về sớm CÓ phép",
    "Về sớm KHÔNG phép",
    "Về sớm CUỐI TUẦN CÓ phép",
    "Về sớm CUỐI TUẦN KHÔNG phép",
    "Về sớm phát sinh",
    "Leader về sớm về sớm theo chính sách",
}


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFD", str(value or "").strip().lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return " ".join(raw.replace("đ", "d").split())


RESTRICTED_LEAVE_REASON_KEYS = frozenset(_norm(reason) for reason in RESTRICTED_LEAVE_REASONS)
EARLY_LEAVE_REASON_KEYS = frozenset(
    _norm(reason) for reason in RESTRICTED_LEAVE_REASONS if "Về sớm" in reason
)


def _restricted_leave_reason(value: Any) -> bool:
    return _norm(value) in RESTRICTED_LEAVE_REASON_KEYS


def _early_leave_reason(value: Any) -> bool:
    return _norm(value) in EARLY_LEAVE_REASON_KEYS


def _local_naive(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(VN_TZ).replace(tzinfo=None)


def _restriction_map(conn, start: date, end: date) -> dict[tuple[date, str], dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT leave_date, employee_name, leave_reason, created_at
        FROM leave_records
        WHERE leave_date BETWEEN :start_date AND :end_date
        ORDER BY leave_date, employee_name, created_at
    """), {"start_date": start, "end_date": end}).mappings().all()
    output: dict[tuple[date, str], dict[str, Any]] = {}
    for row in rows:
        reason = str(row.get("leave_reason") or "").strip()
        if not _restricted_leave_reason(reason):
            continue
        key = (row["leave_date"], _norm(row.get("employee_name")))
        entry = output.setdefault(key, {"reasons": [], "early_leave_registered_at": None})
        if reason and reason not in entry["reasons"]:
            entry["reasons"].append(reason)
        if _early_leave_reason(reason):
            created_at = _local_naive(row.get("created_at"))
            current = entry.get("early_leave_registered_at")
            if created_at is not None and (current is None or created_at < current):
                entry["early_leave_registered_at"] = created_at
    return output


def _parse_clock(value: Any, work_day: date) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in (
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%H:%M:%S", "%H:%M",
    ):
        try:
            parsed = datetime.strptime(raw, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=work_day.year, month=work_day.month, day=work_day.day)
            return parsed
        except ValueError:
            continue
    return None


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "."))
    except ValueError:
        return 0.0


def _work_day(item: dict[str, Any]) -> date | None:
    raw = str(item.get("date") or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _single_side_item(catalog: dict[str, dict]) -> dict | None:
    for name in (
        "Ra ngoài chỉ có dữ liệu một lần",
        "Ra ngoài thiếu giờ ra/vào",
    ):
        item = auto_check.catalog_item(catalog, name)
        if item:
            return item
    return None


def _violation_for(
    *,
    catalog: dict[str, dict],
    work_day: date,
    break_out: datetime,
) -> tuple[dict | None, int, str]:
    cutoff = datetime.combine(work_day, CUTOFF)
    if break_out > cutoff:
        return _single_side_item(catalog), 0, "Giờ ra sau 17:00"

    minutes = max(0, int(math.ceil((cutoff - break_out).total_seconds() / 60)))
    return auto_check.outside_reason(catalog, minutes), minutes, "Tính từ Giờ ra đến 17:00"


def _same_event(left: datetime | None, right: datetime | None, tolerance_seconds: int = 180) -> bool:
    if left is None or right is None:
        return False
    return abs((left - right).total_seconds()) <= tolerance_seconds


def _scheduled_early_checkout(
    item: dict[str, Any],
    *,
    work_day: date,
    reasons: list[str],
    early_leave_registered_at: datetime | None,
    break_out: datetime,
) -> datetime | None:
    """Return the final checkout when a Về sớm schedule existed before FaceID.

    This deliberately distinguishes two business cases:
    1) Về sớm was already registered before the >=17:00 checkout -> final exit,
       not a mid-shift break and never an outside-break penalty.
    2) Employee went outside first, then Về sớm was entered afterwards -> keep
       the recorded outside event so the existing automatic penalty still runs.
    """
    if not any(_early_leave_reason(reason) for reason in reasons):
        return None
    if break_out.time() < CUTOFF:
        return None
    if early_leave_registered_at is None or early_leave_registered_at > break_out:
        return None

    source = _norm(item.get("break_source") or item.get("break_method"))
    if source and "timesoft" not in source:
        return None

    departure_status = _norm(item.get("departure_status"))
    early_minutes = _number(item.get("early_minutes"))
    if "ve som" not in departure_status and "ra som" not in departure_status and early_minutes <= 0:
        return None

    faceid_last = _parse_clock(item.get("faceid_last"), work_day)
    summary_checkout = _parse_clock(item.get("check_out"), work_day)
    candidate = faceid_last or summary_checkout
    if candidate is None or not _same_event(candidate, break_out):
        return None
    return candidate


def _mark_final_early_checkout(
    item: dict[str, Any],
    *,
    checkout: datetime,
    restriction_text: str,
) -> None:
    checkout_text = checkout.strftime("%H:%M:%S")
    item["check_out"] = checkout_text
    item["faceid_check_out"] = checkout_text
    item["break_out"] = ""
    item["break_in"] = ""
    item["break_started"] = False
    item["break_count"] = 0
    item["break_actual_minutes"] = 0
    item["break_over_minutes"] = 0
    item["break_return_late_minutes"] = 0
    item["break_return_deadline"] = ""
    item["break_return_deadline_iso"] = ""
    item["break_remaining_seconds"] = 0
    item["break_source"] = ""
    item["break_method"] = "Check-out Về sớm đã đăng ký trước"
    item["break_detail"] = f"Check-out Về sớm {item.get('date', '')} {checkout_text}"
    item["break_status"] = f"KHÔNG NGHỈ GIỮA CA · {restriction_text} · Check-out {checkout_text}"
    item["break_final_early_checkout"] = True


def _apply_restrictions_and_penalties(
    engine_instance: Callable[[], Any],
    conn,
    records: list[dict[str, Any]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    restrictions = _restriction_map(conn, start, end)
    if not restrictions:
        return records

    today = datetime.now(VN_TZ).date()
    catalog: dict[str, dict] | None = None
    output: list[dict[str, Any]] = []

    for raw in records:
        item = dict(raw)
        work_day = _work_day(item)
        if work_day is None:
            output.append(item)
            continue

        restriction = restrictions.get((work_day, _norm(item.get("employee_name"))))
        if not restriction:
            output.append(item)
            continue

        reasons = list(restriction.get("reasons") or [])
        restriction_text = " / ".join(reasons)
        item["break_restricted_reason"] = restriction_text
        item["break_alert_suppressed"] = True
        item["break_status"] = f"KHÔNG ĐƯỢC SỬ DỤNG GIỜ RA NGOÀI · {restriction_text}"
        item["break_return_deadline"] = ""
        item["break_return_deadline_iso"] = ""
        item["break_remaining_seconds"] = 0

        break_out = _parse_clock(item.get("break_out"), work_day)
        if break_out is None:
            output.append(item)
            continue

        checkout = _scheduled_early_checkout(
            item,
            work_day=work_day,
            reasons=reasons,
            early_leave_registered_at=restriction.get("early_leave_registered_at"),
            break_out=break_out,
        )
        if checkout is not None:
            _mark_final_early_checkout(
                item,
                checkout=checkout,
                restriction_text=restriction_text,
            )
            output.append(item)
            continue

        if work_day != today:
            output.append(item)
            continue

        if catalog is None:
            with engine_instance().connect() as catalog_conn:
                catalog = auto_check.load_catalog(catalog_conn)

        reason_item, minutes, calculation = _violation_for(
            catalog=catalog or {},
            work_day=work_day,
            break_out=break_out,
        )
        if not reason_item:
            item["break_auto_penalty_error"] = "Nội quy chưa có lý do phạt Ra ngoài phù hợp."
            output.append(item)
            continue

        detail = (
            f"Tự động phạt do trong ngày đã có {restriction_text} nên không được sử dụng giờ ra ngoài"
            f" · Giờ ra {break_out.strftime('%H:%M:%S')} · {calculation}"
        )
        source = str(item.get("break_source") or item.get("break_method") or "TimeSoft/TourVera")
        detail += f" · Dữ liệu ra ngoài: {source}"

        try:
            with engine_instance().begin() as write_conn:
                ok, message = auto_check.save_violation(
                    write_conn,
                    work_date=work_day,
                    employee=str(item.get("employee_name") or "").strip(),
                    reason_item=reason_item,
                    detail=detail,
                    source="AUTO UPDATE 24/7 - QUY TẮC RA NGOÀI",
                    minutes=minutes,
                )
            if message == "SKIP_GRACE_PERIOD":
                item["break_auto_penalty_grace"] = True
                item["break_auto_penalty_status"] = message
            else:
                item["break_auto_penalty_reason"] = str(reason_item.get("name") or "")
                item["break_auto_penalty_minutes"] = minutes
                item["break_auto_penalty_status"] = message if ok else f"ERROR: {message}"
        except Exception as exc:
            # Never make the attendance page unavailable because a background
            # penalty write failed; surface the error for operational diagnosis.
            item["break_auto_penalty_error"] = str(exc)[:240]

        output.append(item)

    penalty_notifications.notify_pending(engine_instance())
    return output


def install_outside_leave_rule(
    app,
    *,
    engine_instance: Callable[[], Any],
) -> None:
    if getattr(app.state, "outside_leave_rule_installed", False):
        return

    original_records = snapshot._records
    original_fact = break_alerts._fact

    def records_with_leave_restriction(conn, start: date, end: date):
        records = original_records(conn, start, end)
        return _apply_restrictions_and_penalties(
            engine_instance,
            conn,
            records,
            start,
            end,
        )

    def fact_without_normal_break_alert(item: dict[str, Any], now: datetime):
        # A late/early-leave day has no 90-minute outside allowance, so do not
        # send the ordinary "15 minutes remaining" break reminder for it.
        if item.get("break_restricted_reason"):
            return None
        return original_fact(item, now)

    snapshot._records = records_with_leave_restriction
    break_alerts._fact = fact_without_normal_break_alert

    @app.get("/v2/attendance/outside-leave-rule/health")
    def outside_leave_rule_health():
        return {
            "ok": True,
            "release": RELEASE,
            "restricted_same_day_reasons": sorted(RESTRICTED_LEAVE_REASONS),
            "exact_reason_match": True,
            "permission_independent": True,
            "scheduled_early_checkout_rule": "Về sớm registered before >=17:00 TimeSoft checkout is final checkout, not break",
            "late_entered_early_leave_rule": "outside first, Về sớm entered later keeps outside penalty",
            "before_or_at_1700": "penalty minutes = 17:00 - Giờ ra",
            "after_1700": "Ra ngoài chỉ có dữ liệu một lần",
            "source_priority": ["TimeSoft", "TourVera R=Break S=Giờ ra U=Giờ vào"],
        }

    app.state.outside_leave_rule_installed = True
    app.state.outside_leave_rule_release = RELEASE

"""Normalized leave analytics and attendance-driven return-to-work handling.

``vera_phase14_record`` remains the canonical leave request store.  The tables
in this module are indexed projections/audits used for overlap analysis and
idempotent TimeSoft check-in processing.
"""
from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import Any, Callable
from uuid import uuid4

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_web_v2_long_leave import (
    LONG_LEAVE_DATASET,
    REQUEST_TYPE_RESIGNATION,
    STATUS_APPROVED,
    _parse_vn_date,
    _payload_value,
)


RELEASE = "hr-leave-overlap-checkin-v1"
ACTIVE_STATUS_SQL = "lower(COALESCE(payload->>'Trạng thái làm việc',payload->>'employment_status','Đang làm việc')) IN ('đang làm việc','active')"


class CheckinEvent(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    checkin_at: datetime
    source: str = Field(default="timesoft", min_length=1, max_length=80)
    external_id: str = Field(default="", max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)


def ensure_hr_schema(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_hr_leave_period (
            request_id TEXT PRIMARY KEY,
            employee_username TEXT NOT NULL,
            department_id TEXT NOT NULL DEFAULT '',
            leave_type TEXT NOT NULL,
            scheduled_start DATE NOT NULL,
            scheduled_end DATE NOT NULL,
            actual_end_at TIMESTAMPTZ,
            status TEXT NOT NULL,
            end_source TEXT NOT NULL DEFAULT '',
            source_revision INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_hr_leave_username_created
            ON vera_hr_leave_period(lower(employee_username), created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_hr_leave_department_range
            ON vera_hr_leave_period(department_id, scheduled_start, scheduled_end);
        CREATE INDEX IF NOT EXISTS idx_hr_leave_status_range
            ON vera_hr_leave_period(status, scheduled_start, scheduled_end);

        CREATE TABLE IF NOT EXISTS vera_hr_attendance_log (
            id TEXT PRIMARY KEY,
            employee_username TEXT NOT NULL,
            checkin_at TIMESTAMPTZ NOT NULL,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL DEFAULT '',
            raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(employee_username, checkin_at, source)
        );
        CREATE INDEX IF NOT EXISTS idx_hr_attendance_username_time
            ON vera_hr_attendance_log(lower(employee_username), checkin_at DESC);
        CREATE INDEX IF NOT EXISTS idx_hr_attendance_created
            ON vera_hr_attendance_log(created_at DESC);

        CREATE TABLE IF NOT EXISTS vera_hr_leave_return_audit (
            id BIGSERIAL PRIMARY KEY,
            request_id TEXT NOT NULL,
            employee_username TEXT NOT NULL,
            previous_actual_end_at TIMESTAMPTZ,
            actual_end_at TIMESTAMPTZ NOT NULL,
            source TEXT NOT NULL,
            attendance_log_id TEXT,
            actor_username TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """))


def _status(payload: dict[str, Any], record_status: Any) -> str:
    if str(payload.get("Trạng thái kỳ nghỉ") or "").strip() == "Đã kết thúc":
        return "completed"
    return "approved" if str(record_status or "").strip() == STATUS_APPROVED else "pending"


def sync_leave_periods(conn) -> int:
    """Refresh the indexed projection from canonical Phase-14 leave rows."""
    ensure_hr_schema(conn)
    rows = conn.execute(text("""
        SELECT r.logical_id,r.record_type,r.record_status,r.date_from,r.date_to,
               r.payload,r.revision,lower(COALESCE(e.role,'')) department_id
        FROM vera_phase14_record r
        LEFT JOIN employees e
          ON lower(btrim(e.username))=lower(btrim(COALESCE(r.payload->>'Tên nhân viên','')))
        WHERE r.dataset=:dataset AND COALESCE(r.record_type,'')<>:resignation
          AND r.record_status IN ('Chờ duyệt','Đã duyệt')
    """), {"dataset": LONG_LEAVE_DATASET, "resignation": REQUEST_TYPE_RESIGNATION}).mappings().all()
    count = 0
    for row in rows:
        payload = _payload_value(row.get("payload"))
        start = _parse_vn_date(row.get("date_from") or payload.get("Từ ngày"))
        end = _parse_vn_date(row.get("date_to") or payload.get("Đến ngày"))
        username = str(payload.get("Tên nhân viên") or "").strip()
        if not start or not end or not username:
            continue
        request_id = str(payload.get("ID") or str(row.get("logical_id") or "").split(":", 1)[-1])
        returned = _parse_vn_date(payload.get("Ngày quay lại làm việc"))
        actual_end = datetime.combine(returned, time.min) if returned else None
        source = str(payload.get("Nguồn kết thúc kỳ nghỉ") or ("manual" if returned else "")).strip()
        conn.execute(text("""
            INSERT INTO vera_hr_leave_period(
                request_id,employee_username,department_id,leave_type,scheduled_start,
                scheduled_end,actual_end_at,status,end_source,source_revision)
            VALUES (:id,:employee,:department,:leave_type,:start,:end,:actual_end,:status,:source,:revision)
            ON CONFLICT (request_id) DO UPDATE SET
                employee_username=EXCLUDED.employee_username,
                department_id=EXCLUDED.department_id,
                leave_type=EXCLUDED.leave_type,
                scheduled_start=EXCLUDED.scheduled_start,
                scheduled_end=EXCLUDED.scheduled_end,
                actual_end_at=EXCLUDED.actual_end_at,
                status=EXCLUDED.status,
                end_source=EXCLUDED.end_source,
                source_revision=EXCLUDED.source_revision,
                updated_at=NOW()
        """), {"id": request_id, "employee": username, "department": str(row.get("department_id") or ""),
                 "leave_type": str(row.get("record_type") or ""), "start": start, "end": end,
                 "actual_end": actual_end, "status": _status(payload, row.get("record_status")),
                 "source": source, "revision": int(row.get("revision") or 0)})
        count += 1
    return count


def _resolve_username(conn, value: Any, employee_code: Any = "") -> str:
    candidate = str(value or "").strip()
    code = str(employee_code or "").strip()
    row = conn.execute(text("""
        SELECT username FROM employees
        WHERE lower(btrim(username)) IN (lower(btrim(:candidate)),lower(btrim(:code)))
           OR lower(btrim(COALESCE(full_name,'')))=lower(btrim(:candidate))
        ORDER BY CASE WHEN lower(btrim(username))=lower(btrim(:candidate)) THEN 0 ELSE 1 END
        LIMIT 1
    """), {"candidate": candidate, "code": code}).scalar_one_or_none()
    return str(row or candidate).strip()


def record_checkin(conn, *, username: str, checkin_at: datetime, source: str,
                   external_id: str = "", payload: dict[str, Any] | None = None,
                   actor: str = "timesoft", sync_projection: bool = True) -> dict[str, Any]:
    ensure_hr_schema(conn)
    if sync_projection:
        sync_leave_periods(conn)
    username = _resolve_username(conn, username)
    log_id = str(uuid4())
    inserted = conn.execute(text("""
        INSERT INTO vera_hr_attendance_log(id,employee_username,checkin_at,source,external_id,raw_payload)
        VALUES (:id,:employee,:checkin,:source,:external_id,CAST(:payload AS jsonb))
        ON CONFLICT (employee_username,checkin_at,source) DO NOTHING
        RETURNING id
    """), {"id": log_id, "employee": username, "checkin": checkin_at, "source": source,
             "external_id": external_id, "payload": json.dumps(payload or {}, ensure_ascii=False)}).scalar_one_or_none()
    if not inserted:
        return {"inserted": False, "leave_closed": False, "username": username}

    leave = conn.execute(text("""
        SELECT * FROM vera_hr_leave_period
        WHERE lower(employee_username)=lower(:employee)
          AND status='approved'
          AND scheduled_start<=CAST(:checkin AS date)
          AND scheduled_end>=CAST(:checkin AS date)
        ORDER BY scheduled_start DESC LIMIT 1 FOR UPDATE
    """), {"employee": username, "checkin": checkin_at}).mappings().first()
    if not leave:
        return {"inserted": True, "leave_closed": False, "username": username, "attendance_log_id": inserted}

    # A later explicit manual correction remains authoritative until another
    # explicit correction.  Otherwise the first real check-in closes the leave.
    if str(leave.get("end_source") or "") == "manual":
        return {"inserted": True, "leave_closed": False, "manual_override": True,
                "username": username, "attendance_log_id": inserted}

    logical_id = f"long:{leave['request_id']}"
    canonical = conn.execute(text("""
        SELECT payload FROM vera_phase14_record
        WHERE dataset=:dataset AND logical_id=:logical_id FOR UPDATE
    """), {"dataset": LONG_LEAVE_DATASET, "logical_id": logical_id}).mappings().first()
    if not canonical:
        return {"inserted": True, "leave_closed": False, "username": username, "attendance_log_id": inserted}
    canonical_payload = _payload_value(canonical.get("payload"))
    canonical_payload["Ngày quay lại làm việc"] = checkin_at.strftime("%d/%m/%Y")
    canonical_payload["Ghi chú quay lại"] = "Tự động kết thúc theo lần Check-in TimeSoft đầu tiên."
    canonical_payload["Trạng thái kỳ nghỉ"] = "Đã kết thúc"
    canonical_payload["Nguồn kết thúc kỳ nghỉ"] = source
    canonical_payload["Kết thúc lúc"] = checkin_at.isoformat()
    canonical_payload["Người cập nhật"] = actor
    conn.execute(text("""
        UPDATE vera_phase14_record SET payload=CAST(:payload AS jsonb),updated_by=:actor,
            revision=revision+1,updated_at=NOW()
        WHERE dataset=:dataset AND logical_id=:logical_id
    """), {"payload": json.dumps(canonical_payload, ensure_ascii=False), "actor": actor,
             "dataset": LONG_LEAVE_DATASET, "logical_id": logical_id})
    conn.execute(text("""
        UPDATE vera_hr_leave_period SET actual_end_at=:actual_end,status='completed',
            end_source=:source,updated_at=NOW() WHERE request_id=:id
    """), {"actual_end": checkin_at, "source": source, "id": leave["request_id"]})
    conn.execute(text("""
        INSERT INTO vera_hr_leave_return_audit(
            request_id,employee_username,previous_actual_end_at,actual_end_at,
            source,attendance_log_id,actor_username)
        VALUES (:request_id,:employee,:previous,:actual,:source,:log_id,:actor)
    """), {"request_id": leave["request_id"], "employee": username,
             "previous": leave.get("actual_end_at"), "actual": checkin_at,
             "source": source, "log_id": inserted, "actor": actor})
    return {"inserted": True, "leave_closed": True, "request_id": leave["request_id"],
            "username": username, "attendance_log_id": inserted}


def sync_attendance_records(conn, records: list[dict[str, Any]], *, source: str = "timesoft-cache") -> dict[str, int]:
    sync_leave_periods(conn)
    inserted = closed = 0
    for item in records:
        check_in = str(item.get("check_in") or "").strip()
        work_day = _parse_vn_date(item.get("date"))
        if not check_in or not work_day:
            continue
        try:
            clock = datetime.strptime(check_in.split()[-1][:5], "%H:%M").time()
        except ValueError:
            continue
        username = _resolve_username(conn, item.get("employee_name"), item.get("employee_code"))
        result = record_checkin(
            conn, username=username, checkin_at=datetime.combine(work_day, clock),
            source=source, external_id=f"{username}:{work_day.isoformat()}:{clock.isoformat()}", payload=item,
            sync_projection=False,
        )
        inserted += int(result.get("inserted", False))
        closed += int(result.get("leave_closed", False))
    return {"inserted": inserted, "leave_closed": closed}


def _require_hr_manager(ident) -> None:
    if str(getattr(ident, "role", "") or "").lower() not in {"admin", "quanly"}:
        raise HTTPException(403, "Chỉ Admin hoặc Quản lý được xem phân tích nghỉ phép.")


def install_hr_enhancement_routes(
    app, *, engine_instance: Callable[[], Any], current_identity: Callable,
    identity_type: Any,
) -> None:
    @app.post("/v2/hr/attendance/check-in")
    def ingest_checkin(body: CheckinEvent, ident: identity_type = Depends(current_identity)):
        _require_hr_manager(ident)
        with engine_instance().begin() as conn:
            return {"ok": True, **record_checkin(
                conn, username=body.username, checkin_at=body.checkin_at,
                source=body.source, external_id=body.external_id,
                payload=body.payload, actor=ident.employee_username,
            )}

    @app.get("/v2/hr/leaves/overlap")
    def leave_overlap(
        start: date = Query(...), end: date = Query(...),
        department_id: str = Query(default="", max_length=80),
        threshold: float = Query(default=0.2, ge=0, le=1),
        ident: identity_type = Depends(current_identity),
    ):
        _require_hr_manager(ident)
        if end < start or (end - start).days > 92:
            raise HTTPException(400, "Khoảng kiểm tra phải từ 1 đến 93 ngày.")
        with engine_instance().begin() as conn:
            sync_leave_periods(conn)
            params = {"start": start, "end": end, "department": department_id.strip().lower()}
            department_clause = "" if not params["department"] else " AND department_id=:department"
            rows = conn.execute(text("""
                SELECT request_id,employee_username,department_id,leave_type,scheduled_start,
                       scheduled_end,status
                FROM vera_hr_leave_period
                WHERE status IN ('pending','approved')
                  AND scheduled_start<=:end AND scheduled_end>=:start
            """ + department_clause + " ORDER BY scheduled_start,employee_username"), params).mappings().all()
            headcounts = dict(conn.execute(text("""
                SELECT lower(COALESCE(role,'')) department_id,COUNT(*)::int count
                FROM employees WHERE COALESCE(payload->>'__deleted','false')<>'true'
                  AND """ + ACTIVE_STATUS_SQL + """
                GROUP BY lower(COALESCE(role,''))
            """)).all())
        days: list[dict[str, Any]] = []
        cursor = start
        while cursor <= end:
            groups: dict[str, list[dict[str, Any]]] = {}
            for raw in rows:
                item = dict(raw)
                if item["scheduled_start"] <= cursor <= item["scheduled_end"]:
                    groups.setdefault(str(item["department_id"] or ""), []).append(item)
            departments = []
            for dept, items in sorted(groups.items()):
                total = int(headcounts.get(dept, 0))
                usernames = sorted({str(item["employee_username"]) for item in items})
                ratio = len(usernames) / total if total else 0
                departments.append({"department_id": dept, "headcount": total,
                                    "leave_count": len(usernames), "ratio": round(ratio, 4),
                                    "exceeds_threshold": ratio > threshold,
                                    "usernames": usernames, "requests": items})
            days.append({"date": cursor.isoformat(), "departments": departments,
                         "leave_count": sum(item["leave_count"] for item in departments),
                         "has_alert": any(item["exceeds_threshold"] for item in departments)})
            cursor = date.fromordinal(cursor.toordinal() + 1)
        return {"start": start.isoformat(), "end": end.isoformat(),
                "department_id": department_id, "threshold": threshold,
                "days": days, "has_alert": any(item["has_alert"] for item in days)}

    @app.get("/v2/hr/enhancements/health")
    def hr_enhancements_health():
        return {"ok": True, "release": RELEASE}

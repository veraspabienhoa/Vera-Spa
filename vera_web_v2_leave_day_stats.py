"""Separate daily person quotas from filtered actual-day statistics."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends, HTTPException, Query
from sqlalchemy import text

from vera_leave_registration_shared import count_unique_leave_people, summarize_leave_days


LEAVE_DAY_STATS_RELEASE = "leave-day-stats-2026-09-01.1-all-visible"


def _remove_route(app, path: str, method: str) -> None:
    method = method.upper()
    for route in list(app.router.routes):
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", None) == path and method in methods:
            app.router.routes.remove(route)


def install_leave_day_stats_routes(
    app,
    *,
    engine_instance,
    current_identity,
    require_feature,
    feature_allowed,
    daily_quota_config,
    employee_name_matches,
    norm,
    weekday_short_label,
    identity_type,
) -> None:
    """Install unique-person daily counts and actual-day list totals.

    Every account that can open the leave feature sees the same operational
    leave statistics. The optional employee filter only narrows the requested
    view; it is never silently replaced with the logged-in employee. Penalty
    money remains protected separately by employee_penalty_view.
    """
    if getattr(app.state, "leave_day_stats_installed", False):
        return

    _remove_route(app, "/v2/leave/daily-stats", "GET")

    @app.get("/v2/leave/daily-stats")
    def leave_daily_person_stats(
        start_date: date = Query(alias="start"),
        end_date: date = Query(alias="end"),
        employee: str = Query(default="", max_length=200),
        ident: identity_type = Depends(current_identity),
    ):
        if end_date < start_date:
            raise HTTPException(400, "Khoảng thời gian không hợp lệ.")
        if (end_date - start_date).days > 365:
            raise HTTPException(400, "Khoảng thống kê tối đa là 366 ngày.")

        with engine_instance().connect() as conn:
            require_feature(conn, ident, "leave")
            can_view_penalty = feature_allowed(conn, ident, "employee_penalty_view")
            quota = daily_quota_config(conn)
            rows = conn.execute(text("""
                SELECT l.leave_date, l.employee_name, l.leave_reason, l.leave_type,
                       COALESCE(l.calculated_days, 0) AS calculated_days,
                       COALESCE(l.penalty, 0) AS penalty
                FROM leave_records l
                WHERE l.leave_date BETWEEN :start_date AND :end_date
                  AND EXISTS (
                    SELECT 1
                    FROM employees e
                    WHERE lower(btrim(e.username)) = lower(btrim(l.employee_name))
                      AND lower(COALESCE(e.role, '')) NOT IN ('admin','letan','locker','tapvu')
                  )
                ORDER BY l.leave_date, l.employee_name, l.record_uid
            """), {"start_date": start_date, "end_date": end_date}).mappings().all()

        if norm(employee):
            rows = [row for row in rows if employee_name_matches(row["employee_name"], employee)]

        buckets: dict[date, dict[str, Any]] = {}
        for row in rows:
            bucket = buckets.setdefault(row["leave_date"], {"rows": [], "total_penalty": 0.0})
            bucket["rows"].append(row)
            bucket["total_penalty"] += float(row.get("penalty") or 0)

        output = []
        for day in sorted(buckets):
            bucket = buckets[day]
            people = count_unique_leave_people(bucket["rows"])
            day_quota = quota["days"][day.weekday()]
            paid_limit = int(day_quota["paid_limit"])
            generated_limit = int(day_quota["generated_limit"])
            item = {
                "date": day.isoformat(),
                "weekday_label": weekday_short_label(day),
                **people,
                "paid_limit": paid_limit,
                "generated_limit": generated_limit,
                "paid_full": people["paid"] >= paid_limit,
                "generated_full": (
                    people["generated"] > 0 if generated_limit == 0
                    else people["generated"] >= generated_limit
                ),
            }
            if can_view_penalty:
                item["total_penalty"] = bucket["total_penalty"]
            output.append(item)
        return {"days": output, "release": LEAVE_DAY_STATS_RELEASE, "scope": "all_registered_employees"}

    @app.get("/v2/leave/list-stats")
    def leave_list_day_stats(
        start_date: date = Query(alias="start"),
        end_date: date = Query(alias="end"),
        employee: str = Query(default="", max_length=200),
        ident: identity_type = Depends(current_identity),
    ):
        if end_date < start_date:
            raise HTTPException(400, "Khoảng thời gian không hợp lệ.")
        if (end_date - start_date).days > 365:
            raise HTTPException(400, "Khoảng thống kê tối đa là 366 ngày.")

        employee_filter = employee.strip()

        with engine_instance().connect() as conn:
            require_feature(conn, ident, "leave")
            can_view_penalty = feature_allowed(conn, ident, "employee_penalty_view")
            rows = conn.execute(text("""
                SELECT employee_name, leave_reason, leave_type, calculated_days,
                       COALESCE(penalty, 0) AS penalty
                FROM leave_records
                WHERE leave_date BETWEEN :start_date AND :end_date
                ORDER BY leave_date, employee_name, record_uid
            """), {"start_date": start_date, "end_date": end_date}).mappings().all()

        if employee_filter:
            rows = [row for row in rows if employee_name_matches(row["employee_name"], employee_filter)]
        summary = summarize_leave_days(rows)
        if not can_view_penalty:
            summary.pop("total_penalty", None)
        return {
            "summary": summary,
            "release": LEAVE_DAY_STATS_RELEASE,
            "scope": "employee_filter" if employee_filter else "all_registered_employees",
        }

    app.state.leave_day_stats_installed = True

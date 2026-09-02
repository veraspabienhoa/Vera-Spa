"""Dependency-free state transition for cumulative TourVera Break events."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def tour_business_date(now: datetime) -> date:
    """Keep the prior Tour workday active until 10:00 the next morning."""
    return now.date() - timedelta(days=1) if now.hour < 10 else now.date()


def next_break_event_state(
    previous: dict[str, Any], observed_events: dict[str, str], active_employees: dict[str, str],
) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    """Increment newly observed attendance breaks and return live employee counts."""
    prior_seen = previous.get("seen_events") if isinstance(previous, dict) else {}
    prior_seen = prior_seen if isinstance(prior_seen, dict) else {}
    raw_totals = previous.get("totals") if isinstance(previous, dict) else {}
    raw_totals = raw_totals if isinstance(raw_totals, dict) else {}
    totals = {bucket: max(0, int(raw_totals.get(bucket, 0) or 0)) for bucket in ("all", "ca1", "ca2")}

    for key in observed_events.keys() - prior_seen.keys():
        totals["all"] += 1
        bucket = observed_events.get(key, "")
        if bucket in {"ca1", "ca2"}:
            totals[bucket] += 1

    active_counts = {"all": len(active_employees), "ca1": 0, "ca2": 0}
    for bucket in active_employees.values():
        if bucket in {"ca1", "ca2"}:
            active_counts[bucket] += 1

    state = {
        "totals": totals,
        "seen_events": {**prior_seen, **observed_events},
        "active_employees": dict(active_employees),
    }
    metrics = {
        bucket: {"break_total_count": totals[bucket], "break_active_count": active_counts[bucket]}
        for bucket in ("all", "ca1", "ca2")
    }
    return state, metrics

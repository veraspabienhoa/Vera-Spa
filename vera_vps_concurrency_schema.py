"""Install and verify the system-wide PostgreSQL concurrency foundation."""
from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import vera_live_tour_relational as live_tour
import vera_resource_concurrency as concurrency
import vera_postgres_job_queue as background_queue
import vera_revenue_store as revenue_store
from vera_web_v2_revenue_leave_list import REVENUE_SPREADSHEET_ID, REVENUE_WORKSHEET
from vera_vps_data_check import (
    RUNTIME_ENV_KEYS,
    _database_url,
    _running_api_environment,
    load_managed_runtime_environment,
)


REQUIRED_TABLES = (
    concurrency.REVISION_TABLE,
    concurrency.MUTATION_TABLE,
    concurrency.CLAIM_TABLE,
    concurrency.EVENT_TABLE,
    concurrency.COUNTER_TABLE,
    live_tour.META_TABLE,
    *live_tour.RESOURCE_TABLES.values(),
    live_tour.MUTATION_TABLE,
    live_tour.CLAIM_TABLE,
    background_queue.TABLE,
    revenue_store.TABLE,
)


def _backfill(conn) -> dict:
    concurrency.ensure_schema(conn)
    live_tour.ensure_schema(conn)
    background_queue.ensure_schema_conn(conn)
    revenue_bootstrap_raw = revenue_store.bootstrap_from_google_sheet(
        conn, spreadsheet_id=REVENUE_SPREADSHEET_ID, worksheet_name=REVENUE_WORKSHEET,
    )
    revenue_bootstrap = {
        "skipped": bool(revenue_bootstrap_raw.get("skipped")),
        "row_count": int(revenue_bootstrap_raw.get("row_count") or 0),
    }
    conn.execute(text(f"""
        INSERT INTO {concurrency.REVISION_TABLE}(domain,resource_id,revision,updated_at)
        SELECT 'employee', lower(btrim(username)), 1, NOW() FROM employees
        ON CONFLICT(domain,resource_id) DO NOTHING
    """))
    conn.execute(text(f"""
        INSERT INTO {concurrency.REVISION_TABLE}(domain,resource_id,revision,updated_at)
        SELECT 'leave_record', record_uid, 1, NOW() FROM leave_records
        WHERE COALESCE(record_uid,'') <> ''
        ON CONFLICT(domain,resource_id) DO NOTHING
    """))
    counter = conn.execute(text("""
        SELECT source_sheet_id,COALESCE(MAX(source_row),1) AS current_value
        FROM leave_records WHERE source_row IS NOT NULL GROUP BY source_sheet_id
    """)).mappings().all()
    for row in counter:
        conn.execute(text(f"""
            INSERT INTO {concurrency.COUNTER_TABLE}(scope,counter_key,value,updated_at)
            VALUES('leave_sheet',:key,:value,NOW())
            ON CONFLICT(scope,counter_key) DO UPDATE SET
              value=GREATEST({concurrency.COUNTER_TABLE}.value,EXCLUDED.value), updated_at=NOW()
        """), {"key": str(row["source_sheet_id"] or ""), "value": int(row["current_value"] or 1)})

    aggregate = conn.execute(text("""
        SELECT value_json,revision FROM vera_app_setting
        WHERE category='live_tour' AND setting_key='state'
    """)).mappings().first()
    mirrored = {"upserted": 0, "deleted": 0}
    if aggregate:
        state = aggregate["value_json"]
        if not isinstance(state, dict):
            state = json.loads(state)
        previous, _ = live_tour.load_state(conn)
        mirrored = live_tour.sync_changes(
            conn, previous, state, int(aggregate["revision"] or 0), force=True,
        )
    conn.execute(text("""
        INSERT INTO vera_schema_version(component,version,updated_at)
        VALUES('system_resource_concurrency',1,NOW())
        ON CONFLICT(component) DO UPDATE SET
          version=GREATEST(vera_schema_version.version,EXCLUDED.version), updated_at=NOW()
    """))
    return {"live_tour": mirrored, "revenue": revenue_bootstrap}


def _verify(conn) -> dict:
    missing = [
        table_name for table_name in REQUIRED_TABLES
        if not conn.execute(text("SELECT to_regclass(:name)"), {"name": table_name}).scalar()
    ]
    if missing:
        return {"ok": False, "missing_tables": missing}
    aggregate = conn.execute(text("""
        SELECT value_json,revision FROM vera_app_setting
        WHERE category='live_tour' AND setting_key='state'
    """)).mappings().first()
    parity = {"ok": True, "empty": True}
    if aggregate:
        state = aggregate["value_json"]
        if not isinstance(state, dict):
            state = json.loads(state)
        parity = live_tour.parity(conn, state, int(aggregate["revision"] or 0))
    return {
        "ok": bool(parity.get("ok")),
        "schema_version": concurrency.SCHEMA_VERSION,
        "required_tables": len(REQUIRED_TABLES),
        "live_tour_parity": parity,
    }


def _runtime_engine():
    loaded = load_managed_runtime_environment()
    environment = (
        {key: os.environ.get(key, "") for key in RUNTIME_ENV_KEYS}
        if loaded else _running_api_environment()
    )
    if not environment:
        raise RuntimeError("runtime environment unavailable")
    sslmode = str(environment.get("DB_SSLMODE", "require") or "require").strip().lower()
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        sslmode = "require"
    return create_engine(
        _database_url(environment), poolclass=NullPool,
        connect_args={"sslmode": sslmode, "connect_timeout": 10},
    )


def run(*, apply: bool = False, verify: bool = False, engine=None) -> dict:
    engine = engine or _runtime_engine()
    context = engine.begin() if apply else engine.connect()
    with context as conn:
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text("SET LOCAL statement_timeout = '60s'"))
        backfill = _backfill(conn) if apply else None
        result = _verify(conn) if verify else {"ok": True}
        if backfill is not None:
            result["backfill"] = backfill
        if verify and not result.get("ok"):
            raise SystemExit("SYSTEM RESOURCE CONCURRENCY VERIFY: FAILED")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not (args.apply or args.verify):
        parser.error("choose --apply and/or --verify")
    try:
        result = run(apply=args.apply, verify=args.verify)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except SystemExit:
        raise
    except Exception as exc:
        # Never expose connection strings, SQL parameters or business payloads
        # in a public GitHub Actions log.
        raise SystemExit(
            f"SYSTEM RESOURCE CONCURRENCY FAILED: {type(exc).__name__}; no migration committed"
        ) from None

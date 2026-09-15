"""Install and verify the system-wide PostgreSQL concurrency foundation."""
from __future__ import annotations

import argparse
import json

from sqlalchemy import text

import vera_live_tour_relational as live_tour
import vera_postgres
import vera_resource_concurrency as concurrency


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
)


def _backfill(conn) -> dict:
    concurrency.ensure_schema(conn)
    live_tour.ensure_schema(conn)
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
    return mirrored


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


def run(*, apply: bool = False, verify: bool = False) -> dict:
    engine = vera_postgres.get_engine()
    context = engine.begin() if apply else engine.connect()
    with context as conn:
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text("SET LOCAL statement_timeout = '60s'"))
        backfill = _backfill(conn) if apply else None
        result = _verify(conn) if verify else {"ok": True}
        if backfill is not None:
            result["live_tour_backfill"] = backfill
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
    print(json.dumps(run(apply=args.apply, verify=args.verify), ensure_ascii=False, sort_keys=True))

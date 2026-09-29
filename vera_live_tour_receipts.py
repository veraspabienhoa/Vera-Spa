"""Versioned receipt rows; cutover is explicit and transactional under both fences.

The existing mutation table is reserved for this format. Its result column stores
an entire original receipt, including unknown legacy fields, without conversion.
No financial receipt is expired by this module.
"""
from sqlalchemy import text
import vera_live_tour_relational as relational

MARKER = '_receipt_rows_ready'


def enabled_in(state):
    return state.get(MARKER) is True


def ready(conn):
    return conn.execute(text(f"SELECT payload->>'{MARKER}' FROM {relational.META_TABLE} WHERE singleton=1")).scalar() == 'true'


def entry_sql(parameter):
    # parameter is an internal constant, never a user-supplied SQL identifier.
    if parameter not in {'receipt_key', 'payment_key'}:
        raise ValueError('invalid receipt parameter')
    return f"""CASE WHEN payload->>'{MARKER}'='true'
        THEN (SELECT result FROM {relational.MUTATION_TABLE} WHERE idempotency_key=:{parameter})
        ELSE payload->'idempotency'->:{parameter} END"""


def all_sql():
    return f"(SELECT COALESCE(jsonb_object_agg(idempotency_key,result),'{{}}'::jsonb) FROM {relational.MUTATION_TABLE})"


def write_changes(conn, changed, removed):
    if changed:
        conn.execute(text(f"""INSERT INTO {relational.MUTATION_TABLE}
            (idempotency_key,actor,action,payload_hash,status,result)
            SELECT key,COALESCE(value->>'actor',''),COALESCE(value->>'action',''),
              COALESCE(value->>'payload_hash',''),
              CASE WHEN value->>'status' IN ('started','completed','failed')
                   THEN value->>'status' ELSE 'started' END,value
            FROM jsonb_each(CAST(:receipts AS jsonb))
            ON CONFLICT(idempotency_key) DO UPDATE SET actor=EXCLUDED.actor,
              action=EXCLUDED.action,payload_hash=EXCLUDED.payload_hash,
              status=EXCLUDED.status,result=EXCLUDED.result
        """), {'receipts': relational._json(changed)})
    if removed:
        # Only keys in the caller's before snapshot: never erase concurrent keys.
        conn.execute(text(f"DELETE FROM {relational.MUTATION_TABLE} WHERE idempotency_key=ANY(CAST(:keys AS text[]))"), {'keys': removed})


def install_guard(conn):
    # An older API would see an empty inline receipt archive. Reject its write
    # atomically instead of allowing a financial retry to execute a second time.
    conn.execute(text(f"""CREATE OR REPLACE FUNCTION vera_live_tour_receipt_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.payload->>'{MARKER}'='true'
             AND (NEW.payload->>'{MARKER}' IS DISTINCT FROM 'true' OR NEW.payload ? 'idempotency')
             AND current_setting('vera.live_tour_receipt_cutover',true) IS DISTINCT FROM 'allow-inline'
          THEN RAISE EXCEPTION 'Live Tour receipt rows are authoritative; use verified receipt rollback' USING ERRCODE='55000';
          END IF;
          RETURN NEW;
        END $$"""))
    conn.execute(text(f'DROP TRIGGER IF EXISTS vera_live_tour_receipt_guard ON {relational.META_TABLE}'))
    conn.execute(text(f"CREATE TRIGGER vera_live_tour_receipt_guard BEFORE UPDATE OF payload ON {relational.META_TABLE} FOR EACH ROW EXECUTE FUNCTION vera_live_tour_receipt_guard()"))


def migrate(conn, *, rollback=False):
    """Writers must be stopped by the maintenance runner; caller owns commit."""
    import vera_live_tour_resource_store as resources
    conn.execute(text("SET LOCAL lock_timeout='5s'"))
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'vera:v2:live_tour:state'})
    resources.lock(conn)
    row = conn.execute(text(f'SELECT payload,aggregate_revision FROM {relational.META_TABLE} WHERE singleton=1 FOR UPDATE')).mappings().one()
    if not row['payload'].get('_resource_ready'):
        raise RuntimeError('Receipt optimization requires active resource storage')
    is_ready = enabled_in(row['payload'])
    if is_ready == (not rollback):
        return {'changed': False, 'receipt_storage': 'rows' if is_ready else 'inline'}
    if rollback:
        conn.execute(text("SET LOCAL vera.live_tour_receipt_cutover='allow-inline'"))
        # Materialize latest rows, not the pre-cutover backup. Compare before
        # deleting the duplicate representation, in the SAME transaction.
        conn.execute(text(f"""UPDATE {relational.META_TABLE}
            SET payload=(payload-'{MARKER}') || jsonb_build_object('idempotency',{all_sql()}),
                aggregate_revision=aggregate_revision+1,payload_hash='active',updated_at=NOW()
            WHERE singleton=1"""))
        equal = conn.execute(text(f"SELECT payload->'idempotency'={all_sql()} FROM {relational.META_TABLE} WHERE singleton=1")).scalar_one()
        if not equal:
            raise RuntimeError('Receipt export parity failed')
        conn.execute(text(f'DELETE FROM {relational.MUTATION_TABLE}'))
        conn.execute(text("SET LOCAL vera.live_tour_receipt_cutover='deny'"))
    else:
        if conn.execute(text(f'SELECT EXISTS(SELECT 1 FROM {relational.MUTATION_TABLE})')).scalar_one():
            raise RuntimeError('Reserved mutation table contains unrecognized records; migration refused')
        source = row['payload'].get('idempotency', {})
        if not isinstance(source, dict):
            raise RuntimeError('Receipt archive must be an object')
        # PostgreSQL expands the archive once. Never serialize it through Python
        # on ordinary mutations after cutover.
        conn.execute(text(f"""INSERT INTO {relational.MUTATION_TABLE}
            (idempotency_key,actor,action,payload_hash,status,result)
            SELECT entry.key,COALESCE(entry.value->>'actor',''),COALESCE(entry.value->>'action',''),
              COALESCE(entry.value->>'payload_hash',''),
              CASE WHEN entry.value->>'status' IN ('started','completed','failed')
                   THEN entry.value->>'status' ELSE 'started' END,entry.value
            FROM {relational.META_TABLE},
              LATERAL jsonb_each(COALESCE(payload->'idempotency','{{}}'::jsonb)) AS entry
            WHERE singleton=1"""))
        equal = conn.execute(text(f"SELECT COALESCE(payload->'idempotency','{{}}'::jsonb)={all_sql()} FROM {relational.META_TABLE} WHERE singleton=1")).scalar_one()
        if not equal:
            raise RuntimeError('Receipt migration parity failed')
        install_guard(conn)
        conn.execute(text(f"""UPDATE {relational.META_TABLE}
            SET payload=(payload-'idempotency') || jsonb_build_object('{MARKER}',true),
                aggregate_revision=aggregate_revision+1,payload_hash='active',updated_at=NOW()
            WHERE singleton=1"""))
    return {'changed': True, 'receipt_storage': 'inline' if rollback else 'rows'}

"""Durable invoice-number reservations on the caller's transaction.

Schema installation is inert. Activation is an explicit, writers-stopped
maintenance operation after every writer supports this module. Until then the
existing ledger-locked allocator is retained. Never use a sequence: reservations,
number counters and financial writes must commit or roll back together.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
import argparse
import json
import re

from fastapi import HTTPException
from sqlalchemy import text

import vera_live_tour_relational as relational
from vera_versioned_schema import ensure, _ready

COMPONENT = 'live_tour_bill_numbers'
VERSION = 1
MARKER = '_bill_numbers_ready'
NUMBER_TABLE = 'vera_live_tour_bill_number'
COUNTER_TABLE = 'vera_live_tour_bill_counter'
_ALLOCATOR = ContextVar('live_tour_bill_allocator', default=None)
# Leave space below PostgreSQL's btree entry limit for multibyte/manual numbers.
MAX_KEY_BYTES = 2000


def normalized(value):
    from vera_web_v2_live_tour import _norm
    return _norm(value)


def _checked_key(value):
    key = normalized(value)
    if len(key.encode('utf-8')) > MAX_KEY_BYTES:
        raise ValueError('Invoice number exceeds durable index limit')
    return key


def _number_floor(value):
    match = re.fullmatch(r'(?:VERA|LIVE)-(\d{8})-(\d+)', str(value or ''))
    if not match:
        return None
    try:
        raw = match[1]
        day = date.fromisoformat(f'{raw[:4]}-{raw[4:6]}-{raw[6:]}').isoformat()
        return day, int(match[2])
    except ValueError:
        return None


def ensure_schema(conn):
    def migrate(tx):
        tx.execute(text(f'''CREATE TABLE IF NOT EXISTS {NUMBER_TABLE} (
            normalized text COLLATE "C" PRIMARY KEY, invoice_id text NOT NULL,
            raw_numbers text[] NOT NULL, created_at timestamptz NOT NULL DEFAULT NOW(),
            CHECK(octet_length(normalized)<={MAX_KEY_BYTES}),
            CHECK(cardinality(raw_numbers)>0));
            CREATE INDEX IF NOT EXISTS idx_vera_bill_owner ON {NUMBER_TABLE}(invoice_id);
            CREATE TABLE IF NOT EXISTS {COUNTER_TABLE} (
            day date PRIMARY KEY, value numeric NOT NULL CHECK(value>=0 AND value=trunc(value)),
            updated_at timestamptz NOT NULL DEFAULT NOW());'''))
        for table in (NUMBER_TABLE, COUNTER_TABLE):
            tx.execute(text(f'''ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
                REVOKE ALL ON {table} FROM PUBLIC;
                DO $$ BEGIN
                  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON {table} FROM anon; END IF;
                  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON {table} FROM authenticated; END IF;
                END $$'''))
        # Every reservation is a permanent tombstone, even after a void.
        tx.execute(text(f'''CREATE OR REPLACE FUNCTION vera_bill_number_immutable()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            IF TG_OP='DELETE' THEN
                RAISE EXCEPTION 'Invoice number reservations cannot be deleted' USING ERRCODE='55000';
            END IF;
            IF NEW.normalized IS DISTINCT FROM OLD.normalized OR NEW.invoice_id IS DISTINCT FROM OLD.invoice_id
                OR NOT OLD.raw_numbers <@ NEW.raw_numbers THEN
                RAISE EXCEPTION 'Invoice number reservations cannot be reassigned' USING ERRCODE='55000';
            END IF;
            RETURN NEW;
            END $$;
            CREATE OR REPLACE TRIGGER vera_bill_number_immutable BEFORE UPDATE OR DELETE ON {NUMBER_TABLE}
            FOR EACH ROW EXECUTE FUNCTION vera_bill_number_immutable();'''))
    ensure(conn, COMPONENT, VERSION, migrate)


def schema_ready(conn):
    return _ready(conn, COMPONENT, VERSION)


def enabled_in(state):
    return state.get(MARKER) is True


@contextmanager
def allocation_scope(conn, state):
    # A ContextVar keeps concurrent requests/reentrant domain calls isolated.
    # No connection or callback is placed in persisted JSON or a process cache.
    token = _ALLOCATOR.set(conn if enabled_in(state) else None)
    try:
        yield
    finally:
        _ALLOCATOR.reset(token)


def current_connection():
    return _ALLOCATOR.get()


def _raise_collision():
    raise HTTPException(409, 'Số hóa đơn đã tồn tại hoặc đã được sử dụng. Hãy chọn số khác.')


def _reserve(conn, number, invoice_id, *, allow_existing=False):
    key = _checked_key(number)
    inserted = conn.execute(text(f'''INSERT INTO {NUMBER_TABLE}(normalized,invoice_id,raw_numbers)
        VALUES(:key,:owner,ARRAY[CAST(:number AS text)]) ON CONFLICT(normalized) DO NOTHING
        RETURNING normalized'''), {'key': key, 'owner': invoice_id, 'number': number}).scalar_one_or_none()
    if inserted is not None:
        return True
    if allow_existing:
        owner = conn.execute(text(f'SELECT invoice_id FROM {NUMBER_TABLE} WHERE normalized=:key'), {'key':key}).scalar_one()
        if owner == invoice_id:
            conn.execute(text(f'''UPDATE {NUMBER_TABLE} SET raw_numbers=array_append(raw_numbers,CAST(:number AS text))
                WHERE normalized=:key AND NOT CAST(:number AS text)=ANY(raw_numbers)'''), {'key':key,'number':number})
            return True
    return False


def _raise_floor(conn, day, floor):
    conn.execute(text(f'''INSERT INTO {COUNTER_TABLE}(day,value) VALUES(CAST(:day AS date),CAST(:floor AS numeric))
        ON CONFLICT(day) DO UPDATE SET value=GREATEST({COUNTER_TABLE}.value,EXCLUDED.value),updated_at=NOW()'''),
        {'day':day,'floor':str(floor)})


def allocate(conn, state, manual, day, invoice_id):
    if not invoice_id:
        raise RuntimeError('Durable invoice numbering requires an invoice identity')
    if manual:
        # Counter before reservation, matching automatic allocation lock order.
        # Otherwise a concurrent manual/automatic collision could deadlock.
        floor = _number_floor(manual)
        if floor:
            _raise_floor(conn, *floor)
        try:
            reserved = _reserve(conn, manual, invoice_id)
        except ValueError:
            raise HTTPException(400, 'Số hóa đơn nhập tay quá dài.') from None
        if not reserved:
            _raise_collision()
        return manual
    while True:
        number = int(conn.execute(text(f'''INSERT INTO {COUNTER_TABLE}(day,value)
            VALUES(CAST(:day AS date),1) ON CONFLICT(day) DO UPDATE
            SET value={COUNTER_TABLE}.value+1,updated_at=NOW() RETURNING value'''), {'day':day}).scalar_one())
        candidate = f"VERA-{day.replace('-', '')}-{number:04d}"
        if _reserve(conn, candidate, invoice_id):
            # Preserve legacy rollback floors. Ledger serialization is retained.
            state.setdefault('bill_counters', {})[day] = number
            return candidate


def _source_numbers(conn):
    """Maintenance only. Include tombstones and the immutable correction archive."""
    rows = conn.execute(text(f'''SELECT resource_id,payload FROM {relational.RESOURCE_TABLES['invoices']}
        ORDER BY resource_id''')).mappings()
    for row in rows:
        number = str(row['payload'].get('bill_no') or '')
        if number:
            yield number, row['resource_id']
    rows = conn.execute(text(f'''SELECT resource_id,payload FROM {relational.RESOURCE_TABLES['invoice_changes']}
        ORDER BY resource_id''')).mappings()
    for row in rows:
        for field in ('before', 'after'):
            invoice = row['payload'].get(field)
            if isinstance(invoice, dict) and invoice.get('bill_no'):
                owner = str(invoice.get('id') or row['payload'].get('invoice_id') or 'legacy:change:'+row['resource_id'])
                yield str(invoice['bill_no']), owner


def _source_floors(state):
    for day, value in (state.get('bill_counters') or {}).items():
        # Unknown legacy keys remain in metadata; only real calendar days are allocatable.
        try:
            canonical = date.fromisoformat(day).isoformat()
        except (TypeError, ValueError):
            continue
        floor = int(value or 0)
        if floor < 0:
            raise ValueError('Invalid legacy invoice counter')
        yield canonical, floor


def verify(conn):
    """Full maintenance parity, sanitized output only; never used per checkout."""
    if not schema_ready(conn):
        return {'ok':False, 'schema_ready':False, 'active':False}
    state = conn.execute(text(f'SELECT payload FROM {relational.META_TABLE} WHERE singleton=1')).scalar_one()
    reservations = {row['normalized']:row for row in conn.execute(text(f'SELECT normalized,invoice_id,raw_numbers FROM {NUMBER_TABLE}')).mappings()}
    floors = {str(row['day']):int(row['value']) for row in conn.execute(text(f'SELECT day,value FROM {COUNTER_TABLE}')).mappings()}
    sources = list(_source_numbers(conn))
    expected_floors = dict(_source_floors(state))
    for number, _ in sources:
        floor = _number_floor(number)
        if floor:
            expected_floors[floor[0]] = max(expected_floors.get(floor[0],0),floor[1])
    missing = sum(1 for number, owner in sources if
        (entry := reservations.get(_checked_key(number))) is None or entry['invoice_id'] != owner or number not in entry['raw_numbers'])
    behind = sum(1 for day, value in expected_floors.items() if floors.get(day,-1) < value)
    return {'ok':not missing and not behind, 'schema_ready':True, 'active':enabled_in(state),
            'source_numbers':len(sources),'reserved_numbers':len(reservations),'missing':missing,'counter_mismatches':behind}


def _install_guards(conn):
    # Exact raw spelling + invoice owner proves that Python's established Unicode
    # normalization reserved this number. PostgreSQL locale cannot approximate it.
    conn.execute(text(f'''CREATE OR REPLACE FUNCTION vera_live_tour_bill_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE doc jsonb; owner text; number text;
        BEGIN
          IF TG_TABLE_NAME='{relational.RESOURCE_TABLES['invoices']}' THEN
            doc := NEW.payload; owner := NEW.resource_id;
            number := COALESCE(doc->>'bill_no','');
            IF number<>'' AND NOT EXISTS(SELECT 1 FROM {NUMBER_TABLE}
                WHERE invoice_id=owner AND number=ANY(raw_numbers)) THEN
              RAISE EXCEPTION 'Invoice numbering cutover requires a registry-aware writer' USING ERRCODE='55000';
            END IF;
          ELSE
            FOR doc IN SELECT value FROM jsonb_each(NEW.payload) WHERE key IN ('before','after') LOOP
              IF jsonb_typeof(doc)='object' THEN
                owner := COALESCE(NULLIF(doc->>'id',''),NULLIF(NEW.payload->>'invoice_id',''),'legacy:change:'||NEW.resource_id);
                number := COALESCE(doc->>'bill_no','');
                IF number<>'' AND NOT EXISTS(SELECT 1 FROM {NUMBER_TABLE}
                    WHERE invoice_id=owner AND number=ANY(raw_numbers)) THEN
                  RAISE EXCEPTION 'Invoice history number is not reserved' USING ERRCODE='55000';
                END IF;
              END IF;
            END LOOP;
          END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION vera_live_tour_bill_meta_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF OLD.payload->>'{MARKER}'='true' THEN
            IF NEW.payload->>'_resource_ready' IS DISTINCT FROM 'true'
               AND NEW.payload->>'{MARKER}'='true' THEN
              RAISE EXCEPTION 'Deactivate invoice numbering before aggregate rollback' USING ERRCODE='55000';
            END IF;
            IF NEW.payload->>'{MARKER}' IS DISTINCT FROM 'true' THEN
              -- The GUC declares maintenance intent; it is not proof. Verify
              -- coverage and floors in the database even if a caller spoofs it.
              IF current_setting('vera.live_tour_bill_cutover',true) IS DISTINCT FROM 'allow-legacy'
                OR EXISTS(SELECT 1 FROM {NUMBER_TABLE} n WHERE NOT EXISTS(
                  SELECT 1 FROM {relational.RESOURCE_TABLES['invoices']} i
                  WHERE i.deleted_at IS NULL AND i.resource_id=n.invoice_id
                    AND i.payload->>'bill_no'=ANY(n.raw_numbers)) AND NOT EXISTS(
                  SELECT 1 FROM {relational.RESOURCE_TABLES['invoice_changes']} c
                  WHERE c.deleted_at IS NULL
                    AND COALESCE(NULLIF(c.payload->'before'->>'id',''),NULLIF(c.payload->>'invoice_id',''),
                      'legacy:change:'||c.resource_id)=n.invoice_id
                    AND c.payload->'before'->>'bill_no'=ANY(n.raw_numbers)))
                OR EXISTS(SELECT 1 FROM {COUNTER_TABLE} c WHERE NOT CASE
                  WHEN COALESCE(NEW.payload->'bill_counters'->>c.day::text,'') ~ '^[0-9]+$'
                  THEN (NEW.payload->'bill_counters'->>c.day::text)::numeric >= c.value
                  ELSE false END) THEN
                RAISE EXCEPTION 'Invoice numbering deactivation parity failed' USING ERRCODE='55000';
              END IF;
            END IF;
          END IF;
          RETURN NEW;
        END $$;'''))
    for table in (relational.RESOURCE_TABLES['invoices'], relational.RESOURCE_TABLES['invoice_changes']):
        conn.execute(text(f'''DROP TRIGGER IF EXISTS vera_live_tour_bill_guard ON {table};
            CREATE TRIGGER vera_live_tour_bill_guard BEFORE INSERT OR UPDATE OF payload ON {table}
            FOR EACH ROW EXECUTE FUNCTION vera_live_tour_bill_guard();'''))
    conn.execute(text(f'''DROP TRIGGER IF EXISTS vera_live_tour_bill_meta_guard ON {relational.META_TABLE};
        CREATE TRIGGER vera_live_tour_bill_meta_guard BEFORE UPDATE OF payload ON {relational.META_TABLE}
        FOR EACH ROW EXECUTE FUNCTION vera_live_tour_bill_meta_guard();'''))


def activate(conn):
    """Explicit writers-stopped operation. Any failure rolls back everything."""
    import vera_live_tour_resource_store as resources
    conn.execute(text("SET LOCAL lock_timeout='5s'"))
    conn.execute(text("SET LOCAL statement_timeout='60s'"))
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:v2:live_tour:state'))"))
    resources.lock(conn)
    ensure_schema(conn)
    row = conn.execute(text(f'SELECT payload FROM {relational.META_TABLE} WHERE singleton=1 FOR UPDATE')).mappings().one()
    state = row['payload']
    if not state.get('_resource_ready'):
        raise RuntimeError('Invoice numbering requires active resource storage')
    # Validate the whole synthetic/production source before publishing any
    # readiness. Batch database writes instead of one round trip per old invoice.
    reservations = {row['normalized']:dict(row) for row in conn.execute(
        text(f'SELECT normalized,invoice_id,raw_numbers FROM {NUMBER_TABLE}')).mappings()}
    floors = dict(_source_floors(state))
    count = 0
    for number, owner in _source_numbers(conn):
        key = _checked_key(number)
        prior = reservations.get(key)
        if prior is not None and prior['invoice_id'] != owner:
            raise RuntimeError('Conflicting legacy invoice numbers; activation refused')
        if prior is None:
            prior = reservations[key] = {'normalized':key,'invoice_id':owner,'raw_numbers':[]}
        if number not in prior['raw_numbers']:
            prior['raw_numbers'].append(number)
        floor = _number_floor(number)
        if floor:
            floors[floor[0]] = max(floors.get(floor[0],0),floor[1])
        count += 1
    if reservations:
        conn.execute(text(f'''INSERT INTO {NUMBER_TABLE}(normalized,invoice_id,raw_numbers)
            SELECT normalized,invoice_id,raw_numbers FROM jsonb_to_recordset(CAST(:rows AS jsonb))
            AS source(normalized text,invoice_id text,raw_numbers text[]) WHERE true
            ON CONFLICT(normalized) DO UPDATE SET raw_numbers=EXCLUDED.raw_numbers'''),
            {'rows':json.dumps(list(reservations.values()),ensure_ascii=False)})
    if floors:
        conn.execute(text(f'''INSERT INTO {COUNTER_TABLE}(day,value)
            SELECT CAST(day AS date),CAST(value AS numeric) FROM jsonb_each_text(CAST(:floors AS jsonb)) AS source(day,value)
            ON CONFLICT(day) DO UPDATE SET value=GREATEST({COUNTER_TABLE}.value,EXCLUDED.value),updated_at=NOW()'''),
            {'floors':json.dumps({day:str(value) for day,value in floors.items()})})
    result = verify(conn)
    if not result['ok']:
        raise RuntimeError('Invoice number backfill parity failed')
    _install_guards(conn)
    if not enabled_in(state):
        conn.execute(text(f'''UPDATE {relational.META_TABLE} SET
            payload=payload || jsonb_build_object('{MARKER}',true), aggregate_revision=aggregate_revision+1,
            payload_hash='active',updated_at=NOW() WHERE singleton=1'''))
    return {**result, 'active':True, 'backfilled_sources':count}


def deactivate(conn):
    """Export floors only after proving the legacy allocator cannot reuse any number."""
    import vera_live_tour_resource_store as resources
    conn.execute(text("SET LOCAL lock_timeout='5s'"))
    conn.execute(text("SET LOCAL statement_timeout='60s'"))
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:v2:live_tour:state'))"))
    resources.lock(conn)
    state = conn.execute(text(f'SELECT payload FROM {relational.META_TABLE} WHERE singleton=1 FOR UPDATE')).scalar_one()
    if not enabled_in(state):
        return {'active':False,'changed':False}
    # Legacy reads exclude soft-deleted rows and only inspect correction.before.
    legacy = conn.execute(text(f'''SELECT payload->>'bill_no' AS number FROM {relational.RESOURCE_TABLES['invoices']} WHERE deleted_at IS NULL
        UNION ALL SELECT payload->'before'->>'bill_no' FROM {relational.RESOURCE_TABLES['invoice_changes']} WHERE deleted_at IS NULL''')).scalars()
    represented = {normalized(number) for number in legacy if number}
    registered = set(conn.execute(text(f'SELECT normalized FROM {NUMBER_TABLE}')).scalars())
    if not registered <= represented:
        raise RuntimeError('Legacy history cannot preserve all reserved numbers; rollback refused')
    counters = dict(state.get('bill_counters') or {})
    for row in conn.execute(text(f'SELECT day,value FROM {COUNTER_TABLE}')).mappings():
        day = str(row['day']); counters[day] = max(int(counters.get(day) or 0),int(row['value']))
    conn.execute(text("SET LOCAL vera.live_tour_bill_cutover='allow-legacy'"))
    conn.execute(text(f'''UPDATE {relational.META_TABLE} SET payload=(payload-'{MARKER}') ||
        jsonb_build_object('bill_counters',CAST(:counters AS jsonb)), aggregate_revision=aggregate_revision+1,
        payload_hash='active',updated_at=NOW() WHERE singleton=1'''), {'counters':json.dumps(counters)})
    for table in (relational.RESOURCE_TABLES['invoices'], relational.RESOURCE_TABLES['invoice_changes']):
        conn.execute(text(f'DROP TRIGGER IF EXISTS vera_live_tour_bill_guard ON {table}'))
    conn.execute(text("SET LOCAL vera.live_tour_bill_cutover='deny'"))
    return {'active':False,'changed':True,'reserved_numbers':len(registered)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--activate',action='store_true')
    group.add_argument('--deactivate',action='store_true')
    group.add_argument('--verify',action='store_true')
    parser.add_argument('--writers-stopped',action='store_true')
    args = parser.parse_args()
    if not args.verify and not args.writers_stopped:
        parser.error('activation/deactivation requires --writers-stopped after stopping every writer')
    try:
        from vera_vps_concurrency_schema import _runtime_engine
        engine = _runtime_engine()
        with engine.begin() as connection:
            result = activate(connection) if args.activate else deactivate(connection) if args.deactivate else verify(connection)
        print(json.dumps(result,sort_keys=True))
        if not result.get('ok',True):
            raise SystemExit(1)
    except Exception as exc:
        raise SystemExit(f'Invoice numbering operation rolled back: {type(exc).__name__}') from None

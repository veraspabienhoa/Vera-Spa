"""Bounded, fail-closed, read-only evidence for a separately approved cutover.

This module deliberately imports no application code. Importing the application
can install schemas or start workers. All application SQL below is fixed SELECT;
transaction settings are supplied to libpq/the PostgreSQL dialect. No source
value, identifier, URL, exception, SQL, job payload or error text is returned.

A pass is evidence from one bounded database snapshot, never permission to
activate or proof that writers are stopped, releases match, or pooling is affine.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
import re
from time import monotonic
import unicodedata

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

MAX_ROWS = 50_000
MAX_FIELD_BYTES = 16_384
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_KEY_BYTES = 2000
MAX_SECONDS = 20
CONNECT_SECONDS = 3
STATEMENT_MS = 1500
LOCK_MS = 150
IDLE_MS = 5000
FETCH_ROWS = 64

EXPECTED_WORKERS = (
    'live-tour-projection-scheduler', 'live-tour-projection-worker',
    'live-tour-queue-alert-monitor', 'vera-leave-sheet-sync',
    'leave-quota-monitor', 'vera-notification-delivery', 'technical-retention-monitor',
)
TABLES = (
    'vera_live_tour_meta', 'vera_live_tour_invoice', 'vera_live_tour_invoice_change',
    'vera_read_path_schema', 'vera_live_tour_bill_number', 'vera_live_tour_bill_counter',
    'vera_live_tour_mutation', 'vera_worker_runtime', 'vera_background_job',
    'vera_leave_sheet_sync_queue', 'vera_notification_delivery',
)

# Only technical names in this fixed catalog list can appear in the output.
CATALOG_SQL = """SELECT requested.name,
    c.oid IS NOT NULL AS present,
    c.relkind IN ('r','p') AS ordinary_table,
    has_table_privilege(c.oid,'SELECT') AS selectable,
    (NOT c.relrowsecurity OR r.rolsuper OR r.rolbypassrls OR
       (c.relowner=r.oid AND NOT c.relforcerowsecurity)) AS unfiltered
  FROM (VALUES
    ('vera_live_tour_meta'),('vera_live_tour_invoice'),('vera_live_tour_invoice_change'),
    ('vera_read_path_schema'),('vera_live_tour_bill_number'),('vera_live_tour_bill_counter'),
    ('vera_live_tour_mutation'),('vera_worker_runtime'),('vera_background_job'),
    ('vera_leave_sheet_sync_queue'),('vera_notification_delivery')) AS requested(name)
  LEFT JOIN pg_catalog.pg_class c ON c.oid=pg_catalog.to_regclass(requested.name)
  JOIN pg_catalog.pg_roles r ON r.rolname=current_user"""
SETTINGS_SQL = """SELECT
    current_setting('transaction_read_only')='on' AS read_only,
    current_setting('transaction_isolation')='repeatable read' AS repeatable_read,
    current_setting('statement_timeout')='1500ms' AS statement_bounded,
    current_setting('lock_timeout')='150ms' AS lock_bounded,
    current_setting('idle_in_transaction_session_timeout')='5s' AS idle_bounded"""
META_SQL = """SELECT
    payload->'_resource_ready'='true'::jsonb AS resource_active,
    payload->'_receipt_rows_ready'='true'::jsonb AS receipt_rows,
    payload->'_bill_numbers_ready'='true'::jsonb AS registry_active,
    jsonb_typeof(payload)='object' AS valid_payload,
    (NOT payload ? 'bill_counters' OR payload->'bill_counters'='null'::jsonb
      OR jsonb_typeof(payload->'bill_counters')='object') AS valid_counters
  FROM vera_live_tour_meta WHERE singleton=1 LIMIT 2"""
SCHEMA_SQL = """SELECT version FROM vera_read_path_schema
  WHERE component='live_tour_bill_numbers' LIMIT 2"""
TRIGGERS_SQL = """SELECT expected.label,
    t.oid IS NOT NULL AS present,
    COALESCE(t.tgenabled IN ('O','A'),false) AS enabled,
    COALESCE(p.proname=expected.function_name AND t.tgtype=expected.kind
      AND NOT t.tgisinternal AND t.tgqual IS NULL
      AND t.tgnargs=0 AND NOT t.tgdeferrable
      AND ((expected.label='immutable' AND t.tgattr::text='')
        OR (expected.label<>'immutable' AND t.tgattr::text=(
          SELECT a.attnum::text FROM pg_catalog.pg_attribute a
          WHERE a.attrelid=t.tgrelid AND a.attname='payload' AND NOT a.attisdropped))),false) AS expected_shape
  FROM (VALUES
    ('immutable','vera_live_tour_bill_number','vera_bill_number_immutable','vera_bill_number_immutable',27),
    ('invoice_guard','vera_live_tour_invoice','vera_live_tour_bill_guard','vera_live_tour_bill_guard',23),
    ('change_guard','vera_live_tour_invoice_change','vera_live_tour_bill_guard','vera_live_tour_bill_guard',23),
    ('meta_guard','vera_live_tour_meta','vera_live_tour_bill_meta_guard','vera_live_tour_bill_meta_guard',19),
    ('receipt_guard','vera_live_tour_meta','vera_live_tour_receipt_guard','vera_live_tour_receipt_guard',19)
  ) AS expected(label,table_name,trigger_name,function_name,kind)
  LEFT JOIN pg_catalog.pg_trigger t ON t.tgrelid=pg_catalog.to_regclass(expected.table_name)
    AND t.tgname=expected.trigger_name
  LEFT JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid"""

# Values are selected as JSON, not ->> text: Python str(True), str(dict), etc.
# must retain the exact production coercion semantics. Only the necessary scalar
# fields are projected; customer/amount/history payloads never reach Python.
INVOICES_SQL = f"""SELECT
    jsonb_typeof(payload) IS DISTINCT FROM 'object' AS malformed_source,
    octet_length(resource_id)>{MAX_FIELD_BYTES} OR
      COALESCE(octet_length((payload->'bill_no')::text),0)>{MAX_FIELD_BYTES} AS oversized_field,
    CASE WHEN octet_length(resource_id)<={MAX_FIELD_BYTES} THEN resource_id END AS resource_id,
    CASE WHEN COALESCE(octet_length((payload->'bill_no')::text),0)<={MAX_FIELD_BYTES}
      THEN payload->'bill_no' END AS number,
    deleted_at IS NOT NULL AS soft_deleted
  FROM vera_live_tour_invoice LIMIT {MAX_ROWS + 1}"""
CHANGES_SQL = f"""SELECT
    jsonb_typeof(c.payload) IS DISTINCT FROM 'object' AS malformed_source,
    octet_length(c.resource_id)>{MAX_FIELD_BYTES} OR
      COALESCE(octet_length((side.doc->'bill_no')::text),0)>{MAX_FIELD_BYTES} OR
      COALESCE(octet_length((side.doc->'id')::text),0)>{MAX_FIELD_BYTES} OR
      COALESCE(octet_length((c.payload->'invoice_id')::text),0)>{MAX_FIELD_BYTES} AS oversized_field,
    CASE WHEN octet_length(c.resource_id)<={MAX_FIELD_BYTES} THEN c.resource_id END AS resource_id,
    CASE WHEN COALESCE(octet_length((side.doc->'bill_no')::text),0)<={MAX_FIELD_BYTES}
      THEN side.doc->'bill_no' END AS number,
    CASE WHEN COALESCE(octet_length((side.doc->'id')::text),0)<={MAX_FIELD_BYTES}
      THEN side.doc->'id' END AS owner,
    CASE WHEN COALESCE(octet_length((c.payload->'invoice_id')::text),0)<={MAX_FIELD_BYTES}
      THEN c.payload->'invoice_id' END AS fallback_owner,
    side.is_after, c.deleted_at IS NOT NULL AS soft_deleted
  FROM vera_live_tour_invoice_change c
  CROSS JOIN LATERAL (VALUES (c.payload->'before',false),(c.payload->'after',true)) AS side(doc,is_after)
  WHERE jsonb_typeof(side.doc)='object' OR jsonb_typeof(c.payload) IS DISTINCT FROM 'object' LIMIT {MAX_ROWS + 1}"""
REGISTRY_SQL = f"""SELECT
    octet_length(normalized)>{MAX_FIELD_BYTES} OR octet_length(invoice_id)>{MAX_FIELD_BYTES}
      OR COALESCE(octet_length(array_to_json(raw_numbers)::text),0)>{MAX_FIELD_BYTES} AS oversized_field,
    CASE WHEN octet_length(normalized)<={MAX_FIELD_BYTES} THEN normalized END AS normalized,
    CASE WHEN octet_length(invoice_id)<={MAX_FIELD_BYTES} THEN invoice_id END AS owner,
    CASE WHEN COALESCE(octet_length(array_to_json(raw_numbers)::text),0)<={MAX_FIELD_BYTES}
      THEN raw_numbers END AS aliases
  FROM vera_live_tour_bill_number LIMIT {MAX_ROWS + 1}"""
LEGACY_FLOORS_SQL = f"""SELECT
    octet_length(f.key)>{MAX_FIELD_BYTES} OR octet_length(f.value::text)>{MAX_FIELD_BYTES} AS oversized_field,
    CASE WHEN octet_length(f.key)<={MAX_FIELD_BYTES} THEN f.key END AS day,
    CASE WHEN octet_length(f.value::text)<={MAX_FIELD_BYTES} THEN f.value END AS value
  FROM vera_live_tour_meta m
  CROSS JOIN LATERAL jsonb_each(CASE WHEN jsonb_typeof(m.payload->'bill_counters')='object'
    THEN m.payload->'bill_counters' ELSE '{{}}'::jsonb END) f
  WHERE m.singleton=1 LIMIT {MAX_ROWS + 1}"""
COUNTERS_SQL = f"""SELECT octet_length(value::text)>1000 AS oversized_field,
    day::text AS day, CASE WHEN octet_length(value::text)<=1000 THEN value::text END AS value
  FROM vera_live_tour_bill_counter LIMIT {MAX_ROWS + 1}"""

# Fixed allowlisted job inventory: never return arbitrary worker JSON or names.
_WORKERS_JSON = json.dumps(EXPECTED_WORKERS)
WORKERS_SQL = f"""SELECT count(*) AS total,
    count(*) FILTER(WHERE role IN ('combined','worker')) AS worker_instances,
    count(*) FILTER(WHERE role IN ('combined','worker') AND heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '30 seconds'
      AND heartbeat_at<=CURRENT_TIMESTAMP) AS fresh_instances,
    count(*) FILTER(WHERE role IN ('combined','worker') AND state='running'
      AND heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '30 seconds' AND heartbeat_at<=CURRENT_TIMESTAMP
      AND jsonb_typeof(workers)='array' AND workers @> '{_WORKERS_JSON}'::jsonb) AS ready_instances,
    count(*) FILTER(WHERE role IN ('combined','worker') AND jsonb_typeof(workers)='array'
      AND workers @> '{_WORKERS_JSON}'::jsonb) AS complete_inventory_instances,
    count(*) FILTER(WHERE state IN ('degraded','drain_timeout','database_unverified')) AS unhealthy_instances,
    count(*) FILTER(WHERE heartbeat_at>CURRENT_TIMESTAMP) AS future_heartbeats,
    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP-MAX(heartbeat_at)
      FILTER(WHERE role IN ('combined','worker') AND heartbeat_at<=CURRENT_TIMESTAMP)) AS newest_worker_age_seconds
  FROM (SELECT role,state,workers,heartbeat_at FROM vera_worker_runtime LIMIT {MAX_ROWS + 1}) bounded"""
BACKGROUND_SQL = f"""SELECT count(*) AS total,
    count(*) FILTER(WHERE status='pending') AS pending,
    count(*) FILTER(WHERE status='retry') AS retry,
    count(*) FILTER(WHERE status='processing') AS processing,
    count(*) FILTER(WHERE status='failed') AS failed,
    count(*) FILTER(WHERE status='done') AS completed,
    count(*) FILTER(WHERE status NOT IN ('pending','retry','processing','failed','done') OR status IS NULL) AS unknown_status,
    count(*) FILTER(WHERE status='processing' AND (locked_at IS NULL OR locked_at<CURRENT_TIMESTAMP-INTERVAL '10 minutes')) AS stale_processing,
    count(*) FILTER(WHERE last_error IS NOT NULL) AS rows_with_error,
    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP-MIN(created_at) FILTER(WHERE status IN ('pending','retry'))) AS oldest_pending_seconds,
    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP-MAX(completed_at) FILTER(WHERE status='done')) AS last_success_age_seconds
  FROM (SELECT status,locked_at,last_error,created_at,completed_at FROM vera_background_job
    WHERE queue_name='live_tour_projection' LIMIT {MAX_ROWS + 1}) bounded"""
LEAVE_SQL = f"""SELECT count(*) AS total,
    count(*) FILTER(WHERE status='pending') AS pending,
    count(*) FILTER(WHERE status='retry') AS retry,
    count(*) FILTER(WHERE status='processing') AS processing,
    count(*) FILTER(WHERE status='failed') AS failed,
    count(*) FILTER(WHERE status='done') AS completed,
    count(*) FILTER(WHERE status NOT IN ('pending','retry','processing','failed','done') OR status IS NULL) AS unknown_status,
    count(*) FILTER(WHERE status='processing' AND (locked_at IS NULL OR locked_at<CURRENT_TIMESTAMP-INTERVAL '10 minutes')) AS stale_processing,
    count(*) FILTER(WHERE last_error IS NOT NULL) AS rows_with_error,
    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP-MIN(created_at) FILTER(WHERE status IN ('pending','retry'))) AS oldest_pending_seconds,
    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP-MAX(completed_at) FILTER(WHERE status='done')) AS last_success_age_seconds
  FROM (SELECT status,locked_at,last_error,created_at,completed_at FROM vera_leave_sheet_sync_queue LIMIT {MAX_ROWS + 1}) bounded"""
NOTIFICATIONS_SQL = f"""SELECT count(*) AS total,
    count(*) FILTER(WHERE sent_at IS NULL) AS pending,
    count(*) FILTER(WHERE sent_at IS NULL AND attempts>0) AS retry,
    count(*) FILTER(WHERE sent_at IS NULL AND claimed_at IS NOT NULL) AS processing,
    count(*) FILTER(WHERE sent_at IS NOT NULL) AS completed,
    count(*) FILTER(WHERE sent_at IS NULL AND claimed_at<CURRENT_TIMESTAMP-INTERVAL '5 minutes') AS stale_processing,
    count(*) FILTER(WHERE sent_at IS NULL AND last_error IS NOT NULL) AS rows_with_error,
    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP-MIN(created_at) FILTER(WHERE sent_at IS NULL)) AS oldest_pending_seconds,
    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP-MAX(sent_at)) AS last_success_age_seconds
  FROM (SELECT sent_at,attempts,claimed_at,last_error,created_at FROM vera_notification_delivery
    WHERE channel='push' LIMIT {MAX_ROWS + 1}) bounded"""
CONNECTIONS_SQL = """SELECT
    current_setting('max_connections')::integer AS max_connections,
    current_setting('superuser_reserved_connections')::integer AS superuser_reserved_connections,
    COALESCE(current_setting('reserved_connections',true),'0')::integer AS reserved_connections,
    count(*) AS observed_backends,
    count(*) FILTER(WHERE backend_type='client backend') AS observed_connections,
    (SELECT datconnlimit FROM pg_catalog.pg_database WHERE datname=current_database()) AS database_connection_limit,
    count(*) FILTER(WHERE datname=current_database()) AS current_database_connections,
    count(*) FILTER(WHERE usename=current_user) AS current_role_connections,
    (SELECT rolconnlimit FROM pg_catalog.pg_roles WHERE rolname=current_user) AS role_connection_limit,
    count(*) FILTER(WHERE application_name='vera-web-v2-auth') AS auth_tag_connections,
    count(*) FILTER(WHERE application_name='vera-web-v2-business') AS business_tag_connections,
    count(*) FILTER(WHERE application_name='vera-background') AS background_tag_connections,
    count(*) FILTER(WHERE state='active') AS active,
    count(*) FILTER(WHERE state='idle') AS idle,
    count(*) FILTER(WHERE state='idle in transaction') AS idle_in_transaction,
    count(*) FILTER(WHERE wait_event_type='Lock') AS lock_waiters,
    (SELECT rolsuper OR pg_has_role(current_user,'pg_read_all_stats','MEMBER')
       FROM pg_catalog.pg_roles WHERE rolname=current_user) AS complete_activity_visibility
  FROM pg_catalog.pg_stat_activity"""


def _normalize(value):
    """Exact pure production _norm semantics; tests extract that source via AST."""
    value = str(value or '')
    raw = unicodedata.normalize('NFD', value.strip().lower())
    raw = ''.join(ch for ch in raw if unicodedata.category(ch) != 'Mn').replace('đ', 'd')
    return ' '.join(raw.replace('_', ' ').split())


def _number_floor(value):
    match = re.fullmatch(r'(?:VERA|LIVE)-(\d{8})-(\d+)', str(value or ''))
    if not match:
        return None
    try:
        raw = match[1]
        return date.fromisoformat(f'{raw[:4]}-{raw[4:6]}-{raw[6:]}').isoformat(), int(match[2])
    except ValueError:
        return None


def _gate(status, reason, **fields):
    return {'status': status, 'reason': reason, **fields}


class _BoundReached(Exception):
    pass


class _Budget:
    def __init__(self):
        self.deadline = monotonic() + MAX_SECONDS
        self.rows = 0
        self.bytes = 0

    def check(self):
        if monotonic() > self.deadline:
            raise _BoundReached()

    def rows_from(self, conn, sql):
        self.check()
        result = conn.execution_options(stream_results=True, max_row_buffer=FETCH_ROWS).execute(text(sql))
        try:
            for row in result.mappings():
                self.check()
                if row.get('oversized_field'):
                    raise _BoundReached()
                self.rows += 1
                self.bytes += len(json.dumps(dict(row), ensure_ascii=True, default=str).encode('utf-8'))
                if self.rows > MAX_ROWS or self.bytes > MAX_TOTAL_BYTES:
                    raise _BoundReached()
                yield row
        finally:
            result.close()


def _one(conn, sql, budget):
    budget.check()
    result = conn.execute(text(sql))
    try:
        rows = result.mappings().fetchmany(2)
        budget.check()
        if len(rows) != 1:
            raise ValueError('unexpected cardinality')
        return dict(rows[0])
    finally:
        result.close()


def _available(catalog, *tables):
    return all(catalog.get(t, {}).get('readable') is True for t in tables)


def _default_report():
    unknown = lambda: _gate('unknown', 'not_observed')
    return {
        'status': 'unknown', 'snapshot': 'read_only_repeatable_read',
        'session_affinity': 'unverified', 'writers_stopped': 'unverified',
        'limits': {'rows': MAX_ROWS, 'field_bytes': MAX_FIELD_BYTES, 'total_bytes': MAX_TOTAL_BYTES,
                   'inspection_seconds': MAX_SECONDS, 'connect_seconds': CONNECT_SECONDS,
                   'statement_ms': STATEMENT_MS, 'lock_ms': LOCK_MS, 'idle_ms': IDLE_MS},
        'connection': unknown(), 'tables': {}, 'storage': unknown(), 'schema': unknown(),
        'triggers': unknown(), 'sources': unknown(), 'registry_parity': unknown(),
        'counter_parity': unknown(), 'workers': unknown(),
        'queues': {name: unknown() for name in ('projection', 'leave', 'notifications')},
        'connections': unknown(), 'activation_candidate': unknown(),
    }


def _inspect_sources(conn, report, catalog, budget, active):
    if not _available(catalog, 'vera_live_tour_invoice', 'vera_live_tour_invoice_change', 'vera_live_tour_meta'):
        report['sources'] = _gate('unknown', 'source_tables_unavailable')
        return
    source = {}
    floors = {}
    counts = dict(source_numbers=0, normalized_numbers=0, collisions=0, oversize_normalized_keys=0,
                  invoice_numbers=0, before_numbers=0, after_numbers=0, soft_deleted_numbers=0,
                  invalid_legacy_counters=0, legacy_counter_days=0, malformed_source_payloads=0)
    for row in budget.rows_from(conn, LEGACY_FLOORS_SQL):
        try:
            day = date.fromisoformat(row['day']).isoformat()
        except (ValueError, TypeError):
            continue  # Production preserves but does not allocate unknown day keys.
        try:
            value = int(row['value'] or 0)
            if value < 0:
                raise ValueError()
            floors[day] = value
        except (ValueError, TypeError, OverflowError):
            counts['invalid_legacy_counters'] += 1
    counts['legacy_counter_days'] = len(floors)
    for sql, history in ((INVOICES_SQL, False), (CHANGES_SQL, True)):
        for row in budget.rows_from(conn, sql):
            if row['malformed_source']:
                counts['malformed_source_payloads'] += 1
                continue
            number = str(row['number'] or '')
            if not number:
                continue
            owner = str(row['owner'] or row['fallback_owner'] or 'legacy:change:' + row['resource_id']) if history else row['resource_id']
            key = _normalize(number)
            counts['source_numbers'] += 1
            counts['after_numbers' if history and row['is_after'] else 'before_numbers' if history else 'invoice_numbers'] += 1
            counts['soft_deleted_numbers'] += int(row['soft_deleted'])
            counts['oversize_normalized_keys'] += int(len(key.encode('utf-8')) > MAX_KEY_BYTES)
            entry = source.setdefault(key, {'owner': owner, 'aliases': set()})
            if entry['owner'] != owner:
                counts['collisions'] += 1
            entry['aliases'].add(number)
            floor = _number_floor(number)
            if floor:
                floors[floor[0]] = max(floors.get(floor[0], 0), floor[1])
    counts['normalized_numbers'] = len(source)
    bad = any(counts[k] for k in ('collisions', 'oversize_normalized_keys', 'invalid_legacy_counters', 'malformed_source_payloads'))
    report['sources'] = _gate('fail' if bad else 'pass', 'source_conflict' if bad else 'complete_source_scan', **counts)
    if not _available(catalog, 'vera_live_tour_bill_number', 'vera_live_tour_bill_counter'):
        report['registry_parity'] = _gate('unknown', 'registry_tables_unavailable')
        report['counter_parity'] = _gate('unknown', 'registry_tables_unavailable')
        return
    missing = set(source)
    aliases_missing = owner_mismatches = malformed = reserved = permanent_conflicts = 0
    for row in budget.rows_from(conn, REGISTRY_SQL):
        reserved += 1
        key, owner, aliases = row['normalized'], row['owner'], row['aliases']
        if not isinstance(key, str) or not isinstance(owner, str) or not isinstance(aliases, list) or not aliases:
            malformed += 1
            continue
        if len(key.encode('utf-8')) > MAX_KEY_BYTES or any(not isinstance(a, str) or _normalize(a) != key for a in aliases):
            malformed += 1
        entry = source.get(key)
        if entry is not None:
            missing.discard(key)
            if owner != entry['owner']:
                owner_mismatches += 1
                permanent_conflicts += 1
            aliases_missing += len(entry['aliases'] - set(aliases))
    parity_bad = bool(missing or aliases_missing or owner_mismatches or malformed)
    report['registry_parity'] = _gate('fail' if parity_bad else 'pass',
        'registry_mismatch' if parity_bad else 'complete_registry_scan',
        reserved_numbers=reserved, missing_normalized_numbers=len(missing), missing_raw_aliases=aliases_missing,
        owner_mismatches=owner_mismatches, malformed_reservations=malformed,
        activation_backfill_expected=not active)
    if permanent_conflicts or malformed:
        report['sources']['status'] = 'fail'
        report['sources']['reason'] = 'permanent_registry_conflict'
    report['sources']['permanent_registry_conflicts'] = permanent_conflicts
    remaining = dict(floors)
    behind = invalid = preserved_higher = counter_days = 0
    for row in budget.rows_from(conn, COUNTERS_SQL):
        counter_days += 1
        try:
            numeric = Decimal(row['value'])
            value = int(numeric)
            if value < 0 or numeric != value:
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            invalid += 1
            continue
        required = remaining.pop(row['day'], 0)
        behind += int(value < required)
        preserved_higher += int(value > required)
    behind += len(remaining)
    counter_bad = bool(behind or invalid)
    report['counter_parity'] = _gate('fail' if counter_bad else 'pass',
        'counter_floor_mismatch' if counter_bad else 'counter_floors_preserved',
        expected_counter_days=len(floors), stored_counter_days=counter_days,
        counter_mismatches=behind, invalid_counters=invalid,
        higher_preserved_counter_days=preserved_higher, activation_backfill_expected=not active)
    if invalid:
        report['sources']['status'] = 'fail'
        report['sources']['reason'] = 'invalid_registry_counter'


def _aggregate(conn, sql, budget):
    row = _one(conn, sql, budget)
    if int(row['total']) > MAX_ROWS:
        return _gate('unknown', 'row_limit')
    for name, value in tuple(row.items()):
        if name.endswith('_seconds'):
            row[name] = None if value is None else round(max(0, float(value)), 1)
        else:
            row[name] = int(value or 0)
    return row


def _inspect_snapshot(conn, report, budget):
    settings = _one(conn, SETTINGS_SQL, budget)
    if not all(settings.values()):
        report['connection'] = _gate('unknown', 'read_only_deadlines_not_verified')
        return
    report['connection'] = _gate('pass', 'read_only_deadlines_verified')
    rows = list(budget.rows_from(conn, CATALOG_SQL))
    catalog = {}
    for row in rows:
        if row['name'] in TABLES:
            catalog[row['name']] = {'present': bool(row['present']), 'readable': all(row[k] is True for k in ('present', 'ordinary_table', 'selectable', 'unfiltered'))}
    report['tables'] = catalog
    active = False
    if _available(catalog, 'vera_live_tour_meta'):
        meta = _one(conn, META_SQL, budget)
        active = meta['registry_active'] is True
        valid = (meta['valid_payload'] is True and meta['valid_counters'] is True
                 and (not meta['receipt_rows'] or catalog['vera_live_tour_mutation']['readable']))
        report['storage'] = _gate('pass' if valid and meta['resource_active'] else 'fail',
            'resource_storage_active' if valid and meta['resource_active'] else 'storage_prerequisite_missing',
            resource_store='resources' if meta['resource_active'] else 'aggregate',
            receipt_store='rows' if meta['receipt_rows'] else 'inline', registry_active=active,
            valid_counter_container=meta['valid_counters'] is True,
            receipt_rows_table_present=catalog['vera_live_tour_mutation']['present'])
    if _available(catalog, 'vera_read_path_schema'):
        budget.check()
        versions = conn.execute(text(SCHEMA_SQL)).scalars().fetchmany(2)
        ready = len(versions) == 1 and isinstance(versions[0], int) and versions[0] >= 1
        ready = ready and _available(catalog, 'vera_live_tour_bill_number', 'vera_live_tour_bill_counter')
        report['schema'] = _gate('pass' if ready else 'fail', 'registry_schema_ready' if ready else 'registry_schema_not_ready',
            version=versions[0] if len(versions) == 1 and isinstance(versions[0], int) else None)
    elif not catalog.get('vera_read_path_schema', {}).get('present'):
        report['schema'] = _gate('fail', 'schema_table_missing')
    trigger_rows = list(budget.rows_from(conn, TRIGGERS_SQL))
    triggers = {row['label']: {k: bool(row[k]) for k in ('present','enabled','expected_shape')} for row in trigger_rows}
    required = ['immutable']
    if active:
        required += ['invoice_guard','change_guard','meta_guard']
    if report['storage'].get('receipt_store') == 'rows':
        required += ['receipt_guard']
    trigger_ok = all(all(triggers.get(name, {}).get(k) is True for k in ('present','enabled','expected_shape')) for name in required)
    report['triggers'] = _gate('pass' if trigger_ok else 'fail', 'expected_trigger_flags_present' if trigger_ok else 'expected_trigger_flags_missing',
        flags=triggers, required=required, function_bodies_verified=False)
    _inspect_sources(conn, report, catalog, budget, active)
    if _available(catalog, 'vera_worker_runtime'):
        workers = _aggregate(conn, WORKERS_SQL, budget)
        if workers.get('status') == 'unknown':
            report['workers'] = workers
        else:
            ready = workers['ready_instances'] > 0 and not workers['future_heartbeats']
            report['workers'] = _gate('pass' if ready else 'fail', 'fresh_complete_heartbeat' if ready else 'no_verified_fresh_worker',
                expected_job_inventory=list(EXPECTED_WORKERS), freshness_seconds=30, **workers)
    for name, table, sql in (
        ('projection','vera_background_job',BACKGROUND_SQL),
        ('leave','vera_leave_sheet_sync_queue',LEAVE_SQL),
        ('notifications','vera_notification_delivery',NOTIFICATIONS_SQL),
    ):
        if _available(catalog, table):
            row = _aggregate(conn, sql, budget)
            if row.get('status') == 'unknown':
                report['queues'][name] = row
            else:
                bad = any(row.get(k, 0) for k in ('failed','stale_processing','unknown_status'))
                report['queues'][name] = _gate('fail' if bad else 'pass', 'queue_failure_flags' if bad else 'no_queue_failure_flags', **row)
    connections = _one(conn, CONNECTIONS_SQL, budget)
    visible = connections.pop('complete_activity_visibility') is True
    report['connections'] = _gate('pass' if visible else 'unknown', 'activity_aggregates_observed' if visible else 'restricted_activity_visibility',
        complete_activity_visibility=visible, **{k: int(v) for k, v in connections.items()})
    sections = ('storage','schema','triggers','sources') + (('registry_parity','counter_parity') if active else ())
    statuses = [report[k]['status'] for k in sections]
    candidate = 'fail' if 'fail' in statuses else 'unknown' if 'unknown' in statuses else 'pass'
    # Catalog flags do not prove the guard function bodies are the audited ones.
    # This read-only snapshot alone must therefore never advertise a go decision.
    reason = 'database_prerequisite_failed' if candidate == 'fail' else (
        'additional_guard_verification_required' if candidate == 'pass' else 'database_evidence_incomplete')
    candidate = 'unknown' if candidate == 'pass' else candidate
    report['activation_candidate'] = _gate(candidate, reason,
        operator_window_required=True, stopped_writers_required=True, compatible_releases_required=True)
    budget.check()
    report['status'] = 'complete'


def inspect_database(database_url):
    """Return only bounded technical evidence. Failures never expose exceptions.

    Preserves an existing libpq options/search_path configuration, then overrides
    its timeout/read-only settings. Connection routing or pooler affinity cannot
    be established by this inspection. The caller owns a process-level deadline
    for DNS/driver stalls that PostgreSQL/libpq deadlines cannot interrupt.
    """
    report = _default_report()
    engine = None
    budget = _Budget()
    try:
        url = make_url(database_url)
        if url.drivername not in {'postgresql','postgresql+psycopg','postgresql+psycopg2'}:
            report['connection'] = _gate('unknown', 'unsupported_database_driver')
            return report
        options = url.query.get('options', '')
        if not isinstance(options, str):
            raise ValueError()
        options += (f' -c default_transaction_read_only=on -c statement_timeout={STATEMENT_MS}'
                    f' -c lock_timeout={LOCK_MS} -c idle_in_transaction_session_timeout={IDLE_MS}')
        engine = create_engine(url, poolclass=NullPool, echo=False, hide_parameters=True,
            connect_args={'connect_timeout': CONNECT_SECONDS, 'options': options,
                          'application_name':'vera-phase-three-readonly-preflight'},
            execution_options={'isolation_level':'REPEATABLE READ','postgresql_readonly':True})
        with engine.connect() as conn:
            # Always roll back this snapshot, including the successful case.
            transaction = conn.begin()
            try:
                _inspect_snapshot(conn, report, budget)
            finally:
                transaction.rollback()
    except _BoundReached:
        report['status'] = 'unknown'
        report['activation_candidate'] = _gate('unknown', 'inspection_bound_reached')
    except Exception:
        # Exception text/types may include passwords, hostnames, SQL or PII.
        report['status'] = 'unknown'
        report['activation_candidate'] = _gate('unknown', 'database_inspection_unavailable')
        if report['connection']['status'] != 'pass':
            report['connection'] = _gate('unknown', 'connection_or_read_only_setup_unavailable')
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                report['status'] = 'unknown'
                report['activation_candidate'] = _gate('unknown', 'database_cleanup_unverified')
    return report

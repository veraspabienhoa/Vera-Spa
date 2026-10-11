"""The preflight never imports the API and never mutates its inspected database."""
import ast
from datetime import date
from functools import lru_cache
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import unicodedata
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('phase_three_db_preflight', ROOT / 'scripts/phase_three_db_preflight.py')
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def production_normalizer():
    """Compile only pure functions and their cache, never import the application."""
    tree = ast.parse((ROOT / 'vera_web_v2_live_tour.py').read_text())
    names = {'_normalize_text', '_norm'}
    nodes = [node for node in tree.body if
             isinstance(node, ast.FunctionDef) and node.name in names or
             isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_cached_normalize_text' for t in node.targets)]
    namespace = {'unicodedata': unicodedata, 'lru_cache': lru_cache, 'Any': object}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<pure-production-normalizer>', 'exec'), namespace)
    return namespace['_norm']


@pytest.mark.parametrize('value', [
    None, False, True, 0, 12, [], {}, ['ĐẶC_BIỆT'], {'bill_no': 'ĐẶC'},
    '  ĐẶC_BIỆT  01 ', 'ĐẶC BIỆT 01', '\u2003A\t__B\n', 'STRAẞE',
    'i\u0307', '  LIVE-20260905-0088  ', 'a'*256, 'a'*257,
    'đ\u0301_'*1500, '\u00a0\u202f\u2009', '😀账单',
])
def test_normalization_matches_ast_extracted_production(value):
    assert preflight._normalize(value) == production_normalizer()(value)


def test_unicode_normalization_parity_randomized():
    norm = production_normalizer()
    rng = random.Random(2749)
    for _ in range(300):
        value = ''.join(chr(rng.choice([rng.randrange(0xD800), rng.randrange(0xE000, 0x110000)])) for _ in range(rng.randrange(1, 500)))
        assert preflight._normalize(value) == norm(value)


def test_number_floor_matches_ast_extracted_production():
    tree = ast.parse((ROOT / 'vera_live_tour_bill_numbers.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_number_floor')
    namespace = {'date': date, 're': preflight.re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<pure-production-floor>', 'exec'), namespace)
    for value in ('VERA-20260905-0099', 'LIVE-20260905-99', 'vera-20260905-99',
                  'VERA-20260230-1', 'VERA-20260905-0000', 'VERA-20260905-'+'9'*4500,
                  'VERA-20260905-١٢', '', None):
        assert preflight._number_floor(value) == namespace['_number_floor'](value)


def test_module_imports_no_application_and_queries_only_select():
    tree = ast.parse((ROOT / 'scripts/phase_three_db_preflight.py').read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert all(not (name or '').startswith('vera_') for name in imports)
    for name, value in vars(preflight).items():
        if name.endswith('_SQL'):
            assert value.lstrip().upper().startswith('SELECT'), name
            assert not any(word in value.lower() for word in ('pg_advisory', 'set_config', 'for update', 'for share'))
    assert 'payload FROM' not in preflight.INVOICES_SQL
    assert 'payload FROM' not in preflight.CHANGES_SQL
    assert 'LIMIT 50001' in preflight.INVOICES_SQL
    assert 'LIMIT 50001' in preflight.CHANGES_SQL


def test_unavailable_connection_never_echoes_exception_url_or_secret(monkeypatch):
    seen = {}
    def unavailable(url, **kwargs):
        seen.update(kwargs)
        raise RuntimeError('secret-user:secret-password@private-host SQL customer-name')
    monkeypatch.setattr(preflight, 'create_engine', unavailable)
    result = preflight.inspect_database('postgresql+psycopg://secret-user:secret-password@private-host/private-db')
    assert result['status'] == result['activation_candidate']['status'] == 'unknown'
    rendered = json.dumps(result)
    for secret in ('secret-user','secret-password','private-host','private-db','customer-name','RuntimeError'):
        assert secret not in rendered
    assert seen['poolclass'] is NullPool
    assert seen['hide_parameters'] is True and seen['echo'] is False
    assert seen['connect_args']['connect_timeout'] == 3
    assert 'default_transaction_read_only=on' in seen['connect_args']['options']
    assert seen['execution_options'] == {'isolation_level':'REPEATABLE READ','postgresql_readonly':True}


@pytest.mark.parametrize('url', ['', 'not a url', 'sqlite://', 'mysql://secret@host/db'])
def test_invalid_or_unsupported_url_is_unknown(url):
    result = preflight.inspect_database(url)
    assert result['status'] == 'unknown'
    assert result['activation_candidate']['status'] == 'unknown'


class FakeResult:
    def __init__(self, rows):
        self.rows, self.closed = rows, False
    def mappings(self):
        return iter(self.rows)
    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, rows):
        self.result = FakeResult(rows)
    def execution_options(self, **kwargs):
        assert kwargs == {'stream_results':True,'max_row_buffer':preflight.FETCH_ROWS}
        return self
    def execute(self, statement):
        assert str(statement).startswith('SELECT')
        return self.result


@pytest.mark.parametrize('kind', ['field','rows','bytes','time'])
def test_each_budget_fails_closed_and_closes_stream(kind, monkeypatch):
    budget = preflight._Budget()
    conn = FakeConnection([{'oversized_field':kind == 'field','number':'private-value'}])
    if kind == 'rows':
        budget.rows = preflight.MAX_ROWS
    elif kind == 'bytes':
        budget.bytes = preflight.MAX_TOTAL_BYTES
    elif kind == 'time':
        budget.deadline = -1
    with pytest.raises(preflight._BoundReached):
        list(budget.rows_from(conn, 'SELECT fixed'))
    if kind != 'time':
        assert conn.result.closed


DDL = '''
CREATE TABLE vera_live_tour_meta(singleton integer primary key,payload jsonb);
CREATE TABLE vera_live_tour_invoice(resource_id text primary key,payload jsonb,deleted_at timestamptz);
CREATE TABLE vera_live_tour_invoice_change(resource_id text primary key,payload jsonb,deleted_at timestamptz);
CREATE TABLE vera_read_path_schema(component text primary key,version integer);
CREATE TABLE vera_live_tour_bill_number(normalized text primary key,invoice_id text,raw_numbers text[]);
CREATE TABLE vera_live_tour_bill_counter(day date primary key,value numeric);
CREATE TABLE vera_live_tour_mutation(idempotency_key text primary key,result jsonb);
CREATE TABLE vera_worker_runtime(instance_id uuid primary key,role text,state text,workers jsonb,heartbeat_at timestamptz);
CREATE TABLE vera_background_job(id serial primary key,queue_name text,status text,locked_at timestamptz,last_error text,created_at timestamptz,completed_at timestamptz);
CREATE TABLE vera_leave_sheet_sync_queue(id serial primary key,status text,locked_at timestamptz,last_error text,created_at timestamptz,completed_at timestamptz);
CREATE TABLE vera_notification_delivery(id serial primary key,channel text,sent_at timestamptz,attempts integer,claimed_at timestamptz,last_error text,created_at timestamptz);
CREATE FUNCTION vera_bill_number_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
CREATE TRIGGER vera_bill_number_immutable BEFORE UPDATE OR DELETE ON vera_live_tour_bill_number FOR EACH ROW EXECUTE FUNCTION vera_bill_number_immutable();
CREATE FUNCTION vera_live_tour_bill_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
CREATE FUNCTION vera_live_tour_bill_meta_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
CREATE FUNCTION vera_live_tour_receipt_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
'''


@pytest.fixture
def database():
    base_url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not base_url:
        pytest.skip('VERA_TEST_POSTGRES_URL is required for disposable PostgreSQL tests')
    schema = 'preflight_test_' + uuid4().hex
    admin = create_engine(base_url)
    with admin.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + schema))
    url = make_url(base_url).update_query_dict({'options': '-csearch_path=' + schema})
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(DDL))
        conn.execute(text("INSERT INTO vera_live_tour_meta VALUES(1, '{\"_resource_ready\": true}')"))
        conn.execute(text("INSERT INTO vera_read_path_schema VALUES('live_tour_bill_numbers',1)"))
        conn.execute(text('INSERT INTO vera_worker_runtime VALUES(:id,\'worker\',\'running\',CAST(:workers AS jsonb),CURRENT_TIMESTAMP)'),
                     {'id':uuid4(),'workers':json.dumps(preflight.EXPECTED_WORKERS)})
    try:
        yield engine, url
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        admin.dispose()


def insert_invoice(engine, owner, number, *, deleted=False):
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO vera_live_tour_invoice VALUES(:id,CAST(:payload AS jsonb),CASE WHEN :deleted THEN CURRENT_TIMESTAMP END)'),
                     {'id':owner,'payload':json.dumps({'bill_no':number,'customer':'private-customer','money':999999}), 'deleted':deleted})


def insert_change(engine, key, before, after, invoice_id=None, *, deleted=False):
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO vera_live_tour_invoice_change VALUES(:id,CAST(:payload AS jsonb),CASE WHEN :deleted THEN CURRENT_TIMESTAMP END)'),
                     {'id':key,'payload':json.dumps({'before':before,'after':after,'invoice_id':invoice_id,'private':'private-history'}), 'deleted':deleted})


def reserve(engine, number, owner, aliases=None):
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO vera_live_tour_bill_number VALUES(:key,:owner,:aliases)'),
                     {'key':preflight._normalize(number),'owner':owner,'aliases':aliases or [number]})


def activate_markers(engine, *, receipt=False):
    with engine.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_meta SET payload=payload || '{\"_bill_numbers_ready\": true}'"))
        conn.execute(text('CREATE TRIGGER vera_live_tour_bill_guard BEFORE INSERT OR UPDATE OF payload ON vera_live_tour_invoice FOR EACH ROW EXECUTE FUNCTION vera_live_tour_bill_guard()'))
        conn.execute(text('CREATE TRIGGER vera_live_tour_bill_guard BEFORE INSERT OR UPDATE OF payload ON vera_live_tour_invoice_change FOR EACH ROW EXECUTE FUNCTION vera_live_tour_bill_guard()'))
        conn.execute(text('CREATE TRIGGER vera_live_tour_bill_meta_guard BEFORE UPDATE OF payload ON vera_live_tour_meta FOR EACH ROW EXECUTE FUNCTION vera_live_tour_bill_meta_guard()'))
        if receipt:
            conn.execute(text("UPDATE vera_live_tour_meta SET payload=payload || '{\"_receipt_rows_ready\": true}'"))
            conn.execute(text('CREATE TRIGGER vera_live_tour_receipt_guard BEFORE UPDATE OF payload ON vera_live_tour_meta FOR EACH ROW EXECUTE FUNCTION vera_live_tour_receipt_guard()'))


def snapshot(engine):
    with engine.connect() as conn:
        return {table: conn.execute(text(f'SELECT md5(COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,\'\')) FROM {table} t')).scalar_one()
                for table in preflight.TABLES}


def test_read_only_snapshot_and_fixed_sql_leave_every_row_unchanged(database, monkeypatch):
    engine, url = database
    insert_invoice(engine, 'private-owner', 'private-number')
    before = snapshot(engine)
    statements = []
    observed = {}
    real_create = preflight.create_engine
    def capture_engine(*args, **kwargs):
        db = real_create(*args, **kwargs)
        @event.listens_for(db, 'before_cursor_execute')
        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        return db
    real_snapshot = preflight._inspect_snapshot
    def capture_snapshot(conn, report, budget):
        observed.update(dict(conn.execute(text("SELECT current_setting('transaction_read_only') AS ro,current_setting('transaction_isolation') AS isolation")).mappings().one()))
        return real_snapshot(conn, report, budget)
    monkeypatch.setattr(preflight, 'create_engine', capture_engine)
    monkeypatch.setattr(preflight, '_inspect_snapshot', capture_snapshot)
    result = preflight.inspect_database(url)
    assert result['status'] == 'complete', result
    assert observed == {'ro':'on','isolation':'repeatable read'}
    assert result['activation_candidate']['status'] == 'unknown'
    assert result['activation_candidate']['reason'] == 'additional_guard_verification_required'
    assert result['registry_parity']['status'] == 'fail'  # Inactive backfill is expected.
    assert result['session_affinity'] == result['writers_stopped'] == 'unverified'
    assert result['workers']['ready_instances'] == 1
    assert all(s.lstrip().upper().startswith(('SELECT','SHOW')) for s in statements)
    assert snapshot(engine) == before
    output = json.dumps(result)
    for secret in ('private-owner','private-number','private-customer','999999'):
        assert secret not in output


def test_tombstones_and_both_change_sides_detect_unicode_collision(database):
    engine, url = database
    insert_invoice(engine, 'private-a', 'ĐẶC_BIỆT  01', deleted=True)
    insert_change(engine, 'private-change', {'id':'private-a','bill_no':'Đặc biệt 01'},
                  {'id':'private-b','bill_no':'dac_biet_01'}, deleted=True)
    result = preflight.inspect_database(url)
    assert result['status'] == 'complete'
    assert result['sources']['source_numbers'] == 3
    assert result['sources']['before_numbers'] == result['sources']['after_numbers'] == 1
    assert result['sources']['soft_deleted_numbers'] == 3
    assert result['sources']['collisions'] == 1
    assert result['activation_candidate']['status'] == 'fail'
    assert 'private-' not in json.dumps(result)


def test_change_owner_fallback_and_non_string_json_coercion_match(database):
    engine, url = database
    insert_change(engine, 'archive-one', {'id':False,'bill_no':True}, {'bill_no':12}, invoice_id=0)
    reserve(engine, 'True', 'legacy:change:archive-one')
    reserve(engine, '12', 'legacy:change:archive-one')
    result = preflight.inspect_database(url)
    assert result['registry_parity']['status'] == 'pass'
    assert result['sources']['source_numbers'] == 2


def test_normalized_key_limit_uses_utf8_bytes(database):
    engine, url = database
    insert_invoice(engine, 'wide', '帳'*667)
    result = preflight.inspect_database(url)
    assert result['sources']['oversize_normalized_keys'] == 1
    assert result['sources']['status'] == result['activation_candidate']['status'] == 'fail'


def test_raw_field_limit_is_unknown_even_if_normalization_would_shrink(database):
    engine, url = database
    insert_invoice(engine, 'very-wide', '\u0301'*20_000)
    result = preflight.inspect_database(url)
    assert result['status'] == result['activation_candidate']['status'] == 'unknown'
    assert result['activation_candidate']['reason'] == 'inspection_bound_reached'
    assert len(json.dumps(result)) < 10_000


def test_legacy_and_live_floors_and_higher_existing_floors_are_preserved(database):
    engine, url = database
    insert_invoice(engine, 'one', 'LIVE-20260905-0088')
    insert_change(engine, 'two', {'id':'two','bill_no':'VERA-20260905-0090'}, None)
    reserve(engine, 'LIVE-20260905-0088', 'one')
    reserve(engine, 'VERA-20260905-0090', 'two')
    with engine.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_meta SET payload=payload || '{\"bill_counters\": {\"2026-09-04\": 121,\"invalid-day\": 999999}}'"))
        conn.execute(text("INSERT INTO vera_live_tour_bill_counter VALUES('2026-09-05',90.0),('2026-09-04',200)"))
    activate_markers(engine, receipt=True)
    result = preflight.inspect_database(url)
    assert result['registry_parity']['status'] == result['counter_parity']['status'] == 'pass', result
    assert result['counter_parity']['expected_counter_days'] == 2
    assert result['counter_parity']['higher_preserved_counter_days'] == 1
    assert result['storage']['receipt_store'] == 'rows'
    assert result['activation_candidate']['status'] == 'unknown'
    assert result['activation_candidate']['reason'] == 'additional_guard_verification_required'
    with engine.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_bill_counter SET value=89 WHERE day='2026-09-05'"))
    result = preflight.inspect_database(url)
    assert result['counter_parity']['counter_mismatches'] == 1
    assert result['activation_candidate']['status'] == 'fail'


def test_existing_reservation_owner_and_raw_alias_mismatches(database):
    engine, url = database
    insert_invoice(engine, 'right-owner', 'ĐẶC_01')
    reserve(engine, 'dac 01', 'wrong-owner')
    result = preflight.inspect_database(url)
    assert result['registry_parity']['owner_mismatches'] == 1
    assert result['registry_parity']['missing_raw_aliases'] == 1
    assert result['sources']['permanent_registry_conflicts'] == 1
    assert result['activation_candidate']['status'] == 'fail'


@pytest.mark.parametrize('bad_counter', [-1, 'not-an-integer', {'private':'data'}])
def test_invalid_legacy_counters_refuse_candidate(database, bad_counter):
    engine, url = database
    with engine.begin() as conn:
        conn.execute(text('UPDATE vera_live_tour_meta SET payload=payload || CAST(:extra AS jsonb)'),
                     {'extra':json.dumps({'bill_counters':{'2026-09-05':bad_counter}})})
    result = preflight.inspect_database(url)
    assert result['sources']['invalid_legacy_counters'] == 1
    assert result['activation_candidate']['status'] == 'fail'


def test_active_missing_or_disabled_guard_is_fail(database):
    engine, url = database
    activate_markers(engine)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE vera_live_tour_invoice DISABLE TRIGGER vera_live_tour_bill_guard'))
    result = preflight.inspect_database(url)
    assert result['triggers']['status'] == result['activation_candidate']['status'] == 'fail'
    assert result['triggers']['flags']['invoice_guard']['enabled'] is False


def test_missing_schema_is_never_false_pass(database):
    engine, url = database
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE vera_read_path_schema'))
    result = preflight.inspect_database(url)
    assert result['schema']['status'] == result['activation_candidate']['status'] == 'fail'


def test_missing_source_and_receipt_tables_never_pass(database):
    engine, url = database
    activate_markers(engine, receipt=True)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE vera_live_tour_invoice'))
        conn.execute(text('DROP TABLE vera_live_tour_mutation'))
    result = preflight.inspect_database(url)
    assert result['sources']['status'] == 'unknown'
    assert result['storage']['status'] == 'fail'
    assert result['activation_candidate']['status'] != 'pass'


def test_bounded_worker_inventory_freshness_and_queue_flags_hide_raw_data(database):
    engine, url = database
    with engine.begin() as conn:
        conn.execute(text("UPDATE vera_worker_runtime SET workers='[\"private-job\"]',heartbeat_at=CURRENT_TIMESTAMP-INTERVAL '31 seconds'"))
        conn.execute(text("INSERT INTO vera_background_job(queue_name,status,locked_at,last_error,created_at) VALUES('live_tour_projection','processing',CURRENT_TIMESTAMP-INTERVAL '11 minutes','private-failure',CURRENT_TIMESTAMP-INTERVAL '20 minutes'),('live_tour_projection','failed',NULL,'private-error',CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO vera_leave_sheet_sync_queue(status,last_error,created_at) VALUES('private-status','private-error',CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO vera_notification_delivery(channel,attempts,claimed_at,last_error,created_at) VALUES('push',1,CURRENT_TIMESTAMP-INTERVAL '6 minutes','private-notification',CURRENT_TIMESTAMP)"))
    result = preflight.inspect_database(url)
    assert result['workers']['status'] == 'fail'
    assert result['workers']['complete_inventory_instances'] == 0
    assert result['workers']['newest_worker_age_seconds'] >= 31
    assert result['queues']['projection']['failed'] == 1
    assert result['queues']['projection']['stale_processing'] == 1
    assert result['queues']['leave']['unknown_status'] == 1
    assert result['queues']['notifications']['stale_processing'] == 1
    assert all(result['queues'][k]['status'] == 'fail' for k in result['queues'])
    assert 'private-' not in json.dumps(result)


def test_statement_timeout_returns_unknown_without_exception_or_sql(database, monkeypatch):
    engine, url = database
    monkeypatch.setattr(preflight, 'META_SQL', 'SELECT pg_sleep(2)')
    result = preflight.inspect_database(url)
    assert result['status'] == result['activation_candidate']['status'] == 'unknown'
    assert 'pg_sleep' not in json.dumps(result)
    assert 'QueryCanceled' not in json.dumps(result)


def test_lock_timeout_does_not_wait_for_writer_or_mutate(database):
    engine, url = database
    with engine.begin() as conn:
        conn.execute(text('LOCK TABLE vera_live_tour_meta IN ACCESS EXCLUSIVE MODE'))
        result = preflight.inspect_database(url)
    assert result['status'] == result['activation_candidate']['status'] == 'unknown'


def test_repeatable_read_retains_snapshot_while_writer_commits(database, monkeypatch):
    engine, url = database
    real_sources = preflight._inspect_sources
    def insert_after_snapshot(conn, report, catalog, budget, active):
        insert_invoice(engine, 'late-owner', 'LATE-NUMBER')
        return real_sources(conn, report, catalog, budget, active)
    monkeypatch.setattr(preflight, '_inspect_sources', insert_after_snapshot)
    result = preflight.inspect_database(url)
    assert result['sources']['source_numbers'] == 0
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_live_tour_invoice')).scalar_one() == 1


@pytest.mark.parametrize('table', ['vera_live_tour_invoice','vera_live_tour_invoice_change'])
@pytest.mark.parametrize('payload', ['[]','null','123','"private-corrupt-data"'])
def test_nonobject_source_payloads_are_not_silently_skipped(database, table, payload):
    engine, url = database
    with engine.begin() as conn:
        conn.execute(text(f'INSERT INTO {table} VALUES(\'malformed\',CAST(:payload AS jsonb),NULL)'), {'payload':payload})
    result = preflight.inspect_database(url)
    assert result['sources']['malformed_source_payloads'] > 0
    assert result['sources']['status'] == result['activation_candidate']['status'] == 'fail'
    assert 'private-corrupt-data' not in json.dumps(result)


def test_inactive_registry_missing_counter_table_is_not_a_candidate(database):
    engine, url = database
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE vera_live_tour_bill_counter'))
    result = preflight.inspect_database(url)
    assert result['schema']['status'] == 'fail'
    assert result['counter_parity']['status'] == 'unknown'
    assert result['activation_candidate']['status'] == 'fail'


def test_guard_on_wrong_update_column_is_not_expected_shape(database):
    engine, url = database
    activate_markers(engine)
    with engine.begin() as conn:
        conn.execute(text('DROP TRIGGER vera_live_tour_bill_guard ON vera_live_tour_invoice'))
        conn.execute(text('CREATE TRIGGER vera_live_tour_bill_guard BEFORE INSERT OR UPDATE OF resource_id ON vera_live_tour_invoice FOR EACH ROW EXECUTE FUNCTION vera_live_tour_bill_guard()'))
    result = preflight.inspect_database(url)
    assert result['triggers']['flags']['invoice_guard']['expected_shape'] is False
    assert result['activation_candidate']['status'] == 'fail'


def test_guard_bodies_are_unverified_even_when_all_catalog_flags_match(database):
    engine, url = database
    activate_markers(engine)
    result = preflight.inspect_database(url)
    assert result['triggers']['status'] == 'pass'
    assert result['triggers']['function_bodies_verified'] is False
    assert result['activation_candidate']['status'] == 'unknown'
    assert result['activation_candidate']['reason'] == 'additional_guard_verification_required'


def test_connection_capacity_fields_are_numeric_without_connection_identities(database):
    _, url = database
    result = preflight.inspect_database(url)
    stats = result['connections']
    assert stats['status'] == 'pass'
    for name in ('max_connections','role_connection_limit','database_connection_limit',
                 'current_role_connections','current_database_connections','observed_connections',
                 'auth_tag_connections','business_tag_connections','background_tag_connections'):
        assert type(stats[name]) is int
    assert stats['role_connection_limit'] == stats['database_connection_limit'] == -1
    assert stats['observed_backends'] >= stats['observed_connections']
    assert '127.0.0.1' not in json.dumps(result)
    assert 'preflight_test_' not in json.dumps(result)


def test_rls_filtered_role_never_reports_empty_sources_as_parity(database):
    engine, url = database
    role = 'preflight_reader_' + uuid4().hex
    schema = url.query['options'].split('=', 1)[1]
    insert_invoice(engine, 'hidden-owner', 'HIDDEN-NUMBER')
    with engine.begin() as conn:
        conn.execute(text('CREATE ROLE ' + role + ' LOGIN'))
        conn.execute(text(f'GRANT USAGE ON SCHEMA {schema} TO {role}'))
        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role}'))
        conn.execute(text('ALTER TABLE vera_live_tour_invoice ENABLE ROW LEVEL SECURITY'))
    try:
        result = preflight.inspect_database(url.set(username=role))
        assert result['tables']['vera_live_tour_invoice'] == {'present':True,'readable':False}
        assert result['sources']['status'] == 'unknown'
        assert result['activation_candidate']['status'] == 'unknown'
        assert result['connections']['status'] == 'unknown'
        assert 'hidden-owner' not in json.dumps(result)
    finally:
        with engine.begin() as conn:
            conn.execute(text('DROP OWNED BY ' + role))
            conn.execute(text('DROP ROLE ' + role))


def test_read_only_engine_rejects_mutation_even_with_superuser_fixture(database, monkeypatch):
    engine, url = database
    observed = {}
    def forbidden_mutation(conn, report, budget):
        try:
            conn.execute(text("UPDATE vera_live_tour_meta SET payload='{}'::jsonb"))
        except Exception as error:
            observed['sqlstate'] = getattr(error.orig, 'sqlstate', None)
            raise
    before = snapshot(engine)
    monkeypatch.setattr(preflight, '_inspect_snapshot', forbidden_mutation)
    result = preflight.inspect_database(url)
    assert observed['sqlstate'] == '25006'
    assert result['status'] == 'unknown'
    assert snapshot(engine) == before


def test_catalog_or_aggregate_partial_scan_never_false_passes(database, monkeypatch):
    _, url = database
    monkeypatch.setattr(preflight, 'MAX_ROWS', 1)
    result = preflight.inspect_database(url)
    assert result['status'] == result['activation_candidate']['status'] == 'unknown'
    assert result['activation_candidate']['reason'] == 'inspection_bound_reached'


def test_aggregate_excess_rows_is_unknown_without_partial_counts(monkeypatch):
    monkeypatch.setattr(preflight, '_one', lambda *args: {'total':preflight.MAX_ROWS+1,'failed':0})
    assert preflight._aggregate(None, 'SELECT fixed', preflight._Budget()) == {
        'status':'unknown','reason':'row_limit'}


def test_single_row_query_crossing_deadline_is_unknown_and_closes_result(monkeypatch):
    budget = preflight._Budget()
    class LateResult:
        closed = False
        def mappings(self):
            return self
        def fetchmany(self, count):
            assert count == 2
            budget.deadline = -1
            return [{'total':0}]
        def close(self):
            self.closed = True
    result = LateResult()
    class Connection:
        def execute(self, query):
            return result
    with pytest.raises(preflight._BoundReached):
        preflight._one(Connection(), 'SELECT fixed', budget)
    assert result.closed


def test_final_snapshot_deadline_rechecked_before_complete(database, monkeypatch):
    _, url = database
    real_one = preflight._one
    def finish_after_deadline(conn, sql, budget):
        result = real_one(conn, sql, budget)
        if sql == preflight.CONNECTIONS_SQL:
            budget.deadline = -1
        return result
    monkeypatch.setattr(preflight, '_one', finish_after_deadline)
    result = preflight.inspect_database(url)
    assert result['status'] == result['activation_candidate']['status'] == 'unknown'
    assert result['activation_candidate']['reason'] == 'inspection_bound_reached'

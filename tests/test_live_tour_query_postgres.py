"""Query parity on isolated real PostgreSQL, including rolled-back migrations."""
from copy import deepcopy

import pytest
from sqlalchemy import event, text

import vera_live_tour_query as query
import vera_live_tour_resource_store as store
import vera_live_tour_relational as relational
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW
from test_live_tour_resource_postgres import database

GRANTS = {f'can_{name}': True for name in live.CAPABILITY_FEATURES}
FILTERS = dict(date_from='', date_to='', date='', employee='', customer='', service='', bill_no='',
               total_amount=None, tip_amount=None, performance_timing='all')


@pytest.fixture
def populated(database):
    with database.begin() as conn:
        query.ensure_schema(conn)
        store.lock(conn)
        before, _, _ = store.read(conn)
        state = deepcopy(before)
        state['customers'] = [dict(id=f'c{i}', name='Đặng Ánh' if i % 2 else 'Bình Minh', phone='84901234567', combo_purchases=[]) for i in range(8)]
        state['customers'][-1]['deleted_at'] = '2026-09-01'
        state['invoices'], state['reports'], state['pending'], state['combo_usage'] = [], [], [], []
        for i in range(137):
            timestamp = ['2026-09-30T16:59:59Z', '2026-09-30T17:00:00Z', '2026-10-01T00:01:00', '', 'not-a-date'][i % 5]
            entries = [dict(employee_id='e1', employee_name='Đặng Ánh', service='Body 90', room='1.1'),
                       dict(employee_id='e2', employee_name='Bình Minh', service='Combo VIP' if i % 3 == 0 else 'Foot 60', room='2.1')]
            invoice = dict(id=f'i{i}', bill_no=f'B{i:04}', customer_id=f'c{i%8}', customer_name='Khách Đặng Ánh', customer_phone='0901234567',
                           effective_at=timestamp, business_date='2026-10-02', created_at='2026-10-03T05:00:00Z', entries=entries,
                           total=i*100, tip=i*10, discount=2*i, purchased_combo_id='combo1' if i % 7 == 0 else '')
            state['invoices'].append(invoice)
            for j, entry in enumerate(entries):
                state['reports'].append(dict(invoice, **entry, id=f'r{i}-{j}', invoice_id=f'i{i}', entries=[], total=i*50, tip=i*5, request='YC' if j == 1 else ''))
            if i < 5:
                state['pending'].append(dict(invoice, id=f'p{i}'))
            if i < 10:
                state['combo_usage'].append(dict(id=f'u{i}', customer_id=f'c{i%8}', units=1))
        state['audit'] = [dict(id=f'a{i}', at='2026-10-01T15:00:00+07:00', actor='Đặng Ánh', action='checkout', before={'bill_no': f'B{i:04}'}) for i in range(123)]
        store.write(conn, before, state, 'admin')
    return database


def render_report(result, tab):
    state = live._normalize_state(result['state'], NOW)
    public = live._state_response(state, result['revision'], NOW, **GRANTS)
    return dict(rows=public['state']['invoices'] if tab == 'invoices' else public['report_rows'],
                invoices=public['state']['invoices'], total=result['total'], summary=result['summary'], employee_totals=result['employee_totals'])


@pytest.mark.parametrize('tab', ['revenue', 'employee', 'tip', 'combos', 'invoices'])
@pytest.mark.parametrize('filters', [
    {}, {'date_from': '2026-10-01', 'date_to': '2026-10-01'}, {'date': '2026-10-02'},
    {'employee': 'dang a', 'service': 'foot'}, {'employee': 'dang a', 'service': 'body'},
    {'customer': 'Dang +84 (901) 234-567'}, {'bill_no': 'b001'}, {'total_amount': 0}, {'tip_amount': 50},
])
def test_report_query_exact_full_filter_totals_and_pages(populated, tab, filters):
    filters = {**FILTERS, **filters}
    with populated.begin() as conn:
        state, revision, _ = store.read(conn, collections=relational.RESOURCE_COLLECTIONS)
        public = live._state_response(live._normalize_state(state, NOW), revision, NOW, **GRANTS)
        for page in (1, 2, 99):
            got = query.read_reports(conn, tab=tab, page=page, page_size=7, filters=filters, grants=GRANTS)
            expected = query.report_page(public, state, tab=tab, page=page, page_size=7, filters=filters, performance=[])
            rendered = render_report(got, tab)
            # Employee ties use database collation only for display ordering.
            rendered['employee_totals'].sort(key=lambda row: row['employee'])
            expected['employee_totals'].sort(key=lambda row: row['employee'])
            assert rendered == expected


@pytest.mark.parametrize('panel', ['customers', 'pending', 'invoices', 'reports', 'history'])
def test_collection_latest_page_preserves_source_order(populated, panel):
    with populated.begin() as conn:
        state, _, _ = store.read(conn)
        for page in (1, 2, 200):
            result = query.read_collection(conn, panel, page=page, page_size=7, filters={}, grants=GRANTS)
            for kind in query.GROUPS[panel]:
                rows = state[kind]
                if kind == 'customers':
                    rows = [row for row in rows if not row.get('deleted_at')]
                end = max(0, len(rows) - (page-1)*7)
                assert result['state'][kind] == rows[max(0,end-7):end]
                assert result['totals'].get(kind, 0) == len(rows)


def test_customer_history_is_exact_stable_id_without_other_customers(populated):
    with populated.begin() as conn:
        source, _, _ = store.read(conn)
        result = query.read_customer_history(conn, 'c1', GRANTS)
        assert live._customer_history(result['state'], 'c1') == live._customer_history(source, 'c1')
        assert all(row.get('customer_id') == 'c1' for row in result['state']['invoices'])
        assert result['state']['audit'] == []


def test_stale_old_writer_projection_falls_back_and_new_writer_repairs(populated):
    with populated.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_report SET payload=jsonb_set(payload,'{total}','999'),payload_hash='old-release' WHERE resource_id='r0-0'"))
    with populated.begin() as conn:
        assert query.read_reports(conn, tab='revenue', page=1, page_size=7, filters=FILTERS, grants=GRANTS) is None
        store.lock(conn)
        before, _, _ = store.read(conn)
        after = deepcopy(before)
        after['reports'][0]['total'] = 1000
        store.write(conn, before, after, 'admin')
        result = query.read_reports(conn, tab='revenue', page=1, page_size=7, filters=FILTERS, grants=GRANTS)
        assert result is not None and result['state']['reports'][0]['total'] == 1000


def test_projection_updates_rollback_and_deleted_financial_rows_are_excluded(populated):
    with pytest.raises(RuntimeError):
        with populated.begin() as conn:
            store.lock(conn)
            before, _, _ = store.read(conn)
            after = deepcopy(before)
            after['reports'] = []
            store.write(conn, before, after, 'admin')
            assert query.read_reports(conn, tab='revenue', page=1, page_size=7, filters=FILTERS, grants=GRANTS)['total'] == 0
            raise RuntimeError('rollback')
    with populated.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        after = deepcopy(before)
        after['reports'] = after['reports'][2:]
        after['invoices'] = after['invoices'][1:]
        store.write(conn, before, after, 'admin')
        result = query.read_reports(conn, tab='revenue', page=1, page_size=7, filters=FILTERS, grants=GRANTS)
        assert result['total'] == 272 and result['summary']['invoiceCount'] == 136
        assert result['state']['reports'][0]['id'] == 'r1-0'


def test_read_is_bounded_one_snapshot_and_never_ddl_or_additional_connection(populated):
    statements = []
    def collect(_conn, _cursor, sql, _params, _context, _many):
        statements.append(sql)
    event.listen(populated, 'before_cursor_execute', collect)
    try:
        with populated.begin() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            result = query.read_reports(conn, tab='revenue', page=2, page_size=11, filters=FILTERS, grants=GRANTS)
            assert len(result['state']['reports']) == 11
            assert len(result['state']['invoices']) <= 11
            assert result['total'] == 274
    finally:
        event.remove(populated, 'before_cursor_execute', collect)
    assert not any(any(word in sql.lower() for word in ('create ', 'alter ', 'insert ', 'update ', 'advisory')) for sql in statements)
    assert sum(sql.startswith('WITH ready AS') for sql in statements) == 1


def test_denied_history_and_customer_pii_filters_do_not_reveal_counts(populated):
    grants = {**GRANTS, 'can_customers_view': False, 'can_paid_invoice_view': False, 'can_invoice_view': False, 'can_history_view': False, 'can_backup': False}
    with populated.begin() as conn:
        result = query.read_reports(conn, tab='revenue', page=1, page_size=7, filters={**FILTERS, 'customer': 'dang'}, grants=grants)
        assert result['total'] == 0
        history = query.read_collection(conn, 'history', page=1, page_size=7, filters={}, grants=grants)
        assert history['totals'] == {} and all(not history['state'][kind] for kind in query.HISTORY)


def test_migration_rollback_never_caches_readiness(database):
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            query.ensure_schema(conn)
            assert query.schema_ready(conn)
            raise RuntimeError('rollback schema')
    with database.begin() as conn:
        assert not query.schema_ready(conn)
        assert query.read_reports(conn, tab='revenue', page=1, page_size=7, filters=FILTERS, grants=GRANTS) is None
        query.ensure_schema(conn)
        assert query.schema_ready(conn)


def test_shadow_never_reads_mirror_even_when_projection_schema_is_ready(populated, monkeypatch):
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE', 'shadow')
    with populated.begin() as conn:
        assert query.read_reports(conn, tab='revenue', page=1, page_size=7, filters=FILTERS, grants=GRANTS) is None


def test_explicit_repair_after_old_worker_write_preserves_financial_payloads(populated):
    with populated.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_report SET payload=jsonb_set(payload,'{total}','999'),payload_hash='older-writer' WHERE resource_id='r0-0'"))
    with populated.begin() as conn:
        before = conn.execute(text("SELECT payload,payload_hash,resource_revision,aggregate_revision FROM vera_live_tour_report WHERE resource_id='r0-0'")).one()
        assert not query.verify_projections(conn)['ok']
        assert query.repair_projections(conn) == {'repaired': 1}
        assert query.verify_projections(conn)['ok']
        after = conn.execute(text("SELECT payload,payload_hash,resource_revision,aggregate_revision FROM vera_live_tour_report WHERE resource_id='r0-0'")).one()
        assert after == before
        result = query.read_reports(conn, tab='revenue', page=1, page_size=7, filters=FILTERS, grants=GRANTS)
        assert result['state']['reports'][0]['total'] == 999


def test_repair_rollback_and_repeated_deploy_gate(populated):
    with populated.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_report SET query_hash='' WHERE resource_id='r0-0'"))
    with pytest.raises(RuntimeError):
        with populated.begin() as conn:
            query.repair_projections(conn)
            assert query.verify_projections(conn)['ok']
            raise RuntimeError('rollback repair')
    with populated.begin() as conn:
        assert query.verify_projections(conn)['stale_rows'] == 1
        query.ensure_schema(conn)
        assert query.verify_projections(conn)['ok']


@pytest.mark.parametrize('tab', ['revenue', 'employee', 'tip', 'combos'])
@pytest.mark.parametrize('filters', [{}, {'date':'2026-10-01'}, {'employee':'an an'}, {'employee':'a b'},
    {'customer':'Dang +84 (901) 234-567'}, {'customer':'0901234567,'}, {'bill_no':' '}])
def test_indexed_query_matches_actual_javascript_on_legacy_edges(database, tab, filters):
    from test_live_tour_query import edge_state, javascript_report
    with database.begin() as conn:
        query.ensure_schema(conn)
        store.lock(conn)
        before, _, _ = store.read(conn)
        state = edge_state()
        revision = store.write(conn, before, state, 'admin')
        public = live._state_response(state, revision, NOW, **GRANTS)
        expected = javascript_report(public, tab, {**FILTERS, **filters})
        result = query.read_reports(conn, tab=tab, page=1, page_size=100, filters={**FILTERS, **filters}, grants=GRANTS)
        rendered = render_report(result, tab)
        assert [row['id'] for row in rendered['rows']] == expected['ids']
        for key, value in expected['summary'].items():
            assert rendered['summary'][key] == pytest.approx(value)
        assert sorted(rendered['employee_totals'], key=lambda row: row['employee']) == expected['employee_totals']


def test_http_bounded_and_legacy_fallback_contract_are_identical(populated, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    class Identity(BaseModel):
        employee_username: str = 'admin'
        full_name: str = 'Admin'
        role: str = 'admin'
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda:populated, current_identity=lambda:Identity(),
                                 require_feature=lambda *args:None, feature_allowed=lambda *args:True, identity_type=Identity)
    client = TestClient(app)
    queries = [('/v2/live-tour/reports', dict(tab='revenue',page=2,page_size=11,date='2026-10-01')),
               ('/v2/live-tour/collections/reports', dict(page=2,page_size=11,date_from='2026-10-01',date_to='2026-10-01')),
               ('/v2/live-tour/customers/c1/history', {})]
    indexed = [client.get(path,params=params) for path,params in queries]
    assert all(response.status_code == 200 for response in indexed)
    monkeypatch.setattr(query, 'schema_ready', lambda conn:False)
    fallback = [client.get(path,params=params) for path,params in queries]
    assert all(response.status_code == 200 for response in fallback)
    assert [response.json() for response in indexed] == [response.json() for response in fallback]


@pytest.mark.parametrize('invoice_view', [False, True])
@pytest.mark.parametrize('panel', ['reports', 'history'])
def test_collection_customer_filter_privacy_matches_fallback(populated, monkeypatch, panel, invoice_view):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    class Identity(BaseModel):
        employee_username: str = 'manager'
        full_name: str = 'Manager'
        role: str = 'quanly'
    features = {'live_tour_view', 'live_tour_reports_view', 'live_tour_history_view'}
    if invoice_view:
        features.add('live_tour_invoice_view')
    with populated.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        after = deepcopy(before)
        after['audit'][0]['customer_name'] = 'Đặng Ánh'
        store.write(conn, before, after, 'admin')
    def require(_conn, _ident, feature):
        if feature not in features:
            raise HTTPException(403, feature)
    app = FastAPI()
    live.install_live_tour_routes(app, engine_instance=lambda:populated, current_identity=lambda:Identity(),
                                 require_feature=require, feature_allowed=lambda _c,_i,f:f in features, identity_type=Identity)
    client = TestClient(app)
    response = client.get('/v2/live-tour/collections/' + panel, params={'customer':'dang'})
    assert response.status_code == 200, response.text
    expected_total = (274 if panel == 'reports' else 1) if invoice_view else 0
    assert response.json()['total'] == expected_total
    monkeypatch.setattr(query, 'schema_ready', lambda conn:False)
    fallback = client.get('/v2/live-tour/collections/' + panel, params={'customer':'dang'})
    assert fallback.status_code == 200, fallback.text
    assert fallback.json() == response.json()

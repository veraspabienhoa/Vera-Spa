"""Real PostgreSQL + HTTP tests for shared Auto cash accounting and write exclusion."""
from datetime import date, datetime
from io import BytesIO
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, text

import vera_revenue_auto as auto
import vera_revenue_store as ledger
import vera_purchase_store as purchases
import vera_web_v2_revenue_leave_list as routes
import vera_web_v2_purchase_reconcile as reconcile
import vera_web_v2_purchase_reconcile_v2 as reconcile_v2
from vera_live_tour_lists import matches as report_matches
from vera_web_v2_purchase_reconcile import install_purchase_reconcile_routes
from vera_web_v2_purchases import install_purchase_routes


@pytest.fixture
def database(monkeypatch):
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('VERA_TEST_POSTGRES_URL is required for real PostgreSQL tests')
    schema = 'revenue_auto_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 26, 12, tzinfo=auto.VN_TZ)
    monkeypatch.setattr(auto, 'datetime', Clock)
    monkeypatch.setattr(routes, 'datetime', Clock)
    monkeypatch.setattr(reconcile, 'datetime', Clock)
    try:
        with engine.begin() as conn:
            conn.execute(text('''CREATE TABLE vera_app_setting (
                category text, setting_key text, value_json jsonb, source text, updated_by text,
                revision bigint NOT NULL, created_at timestamptz, updated_at timestamptz,
                PRIMARY KEY(category, setting_key))'''))
            conn.execute(text('CREATE TABLE vera_schema_version (component text PRIMARY KEY, version int, updated_at timestamptz)'))
            conn.execute(text('CREATE TABLE vera_live_tour_report (resource_id text PRIMARY KEY, payload jsonb, deleted_at timestamptz, aggregate_revision bigint NOT NULL DEFAULT 1)'))
            ledger.ensure_schema(conn)
            purchases.ensure_schema(conn)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def report(conn, key, day=None, *, total=0, tip=0, deleted=False, **fields):
    payload = {'total': total, 'tip': tip, **fields}
    if day:
        payload['business_date'] = day
    conn.execute(text('''INSERT INTO vera_live_tour_report(resource_id,payload,deleted_at) VALUES
        (:id, CAST(:payload AS jsonb), CASE WHEN :deleted THEN NOW() ELSE NULL END)'''),
        {'id': key, 'payload': json.dumps(payload), 'deleted': deleted})


def buy(conn, day, amount, deleted=False):
    conn.execute(text('''INSERT INTO vera_purchase_entry
        (purchase_date,item,quantity,unit_price,amount,deleted)
        VALUES (:day,'Synthetic purchase','100',999,:amount,:deleted)'''),
        {'day': day, 'amount': amount, 'deleted': deleted})


def seed(database):
    with database.begin() as conn:
        report(conn, 'before', '2025-09-04', total=999999)
        report(conn, 'cash-a', '2026-09-25', total=200, tip=25, subtotal=999)
        report(conn, 'cash-b', '2026-09-25', total=200, tip=25, subtotal=999)
        report(conn, 'sale', '2026-09-25', total=1000, type='combo_purchase')
        report(conn, 'use', '2026-09-26', total=30, tip=30, subtotal=700, payment_method='COMBO')
        report(conn, 'legacy', effective_at='2026-09-24T18:00:00Z', total=110, tip=10)
        report(conn, 'deleted', '2026-09-25', total=99999, deleted=True)
        report(conn, 'future', '2099-09-05', total=99999)
        report(conn, 'period', '2026-09-26', total=220, tip=20)
        buy(conn, '2025-09-04', 99999)
        buy(conn, '2026-09-25', 100)
        buy(conn, '2026-09-25', 50.25)
        buy(conn, '2026-09-26', 99999, deleted=True)
        buy(conn, '2026-09-26', 40)
        conn.execute(text("INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note) VALUES ('Thu',777,'2025-09-05','Manual retained')"))


def test_read_only_day_reconciliation_separates_manual_and_system_sources(database):
    from vera_revenue_day_check import summarize_day
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE vera_live_tour_invoice (resource_id text PRIMARY KEY, payload jsonb, deleted_at timestamptz)'))
        for key, moment, total, tip in (
            ('a', '2026-09-23T17:00:00Z', 42000000, 20000000),
            ('b', '2026-09-24T23:59:59+07:00', 7250000, 7250000),
            ('next-day', '2026-09-24T17:00:00Z', 999, 9),
        ):
            report(conn, key, '2026-09-23', effective_at=moment, created_at='2026-09-26T00:00:00Z', total=total, tip=tip)
            conn.execute(text('INSERT INTO vera_live_tour_invoice(resource_id,payload) VALUES (:id,CAST(:payload AS jsonb))'),
                         {'id': key, 'payload': json.dumps({'effective_at': moment, 'business_date': '2026-09-23', 'total': total, 'tip': tip})})
        report(conn, 'deleted', '2026-09-24', total=999, tip=9, deleted=True)
        conn.execute(text("INSERT INTO vera_live_tour_invoice VALUES ('deleted',CAST(:payload AS jsonb),NOW())"),
                     {'payload': json.dumps({'effective_at': '2026-09-24T12:00:00+07:00', 'total': 999})})
        buy(conn, '2026-09-24', 121000)
        buy(conn, '2026-09-25', 999)
        buy(conn, '2026-09-24', 999, deleted=True)
        conn.execute(text("""INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note)
            VALUES ('Thu',49250000,'2026-09-24','Manual'), ('Chi',121000,'2026-09-24','Manual'),
                   ('Thu',999,'2026-09-25','Other day')"""))
    with database.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        result = summarize_day(conn, date(2026, 9, 24))
        assert result['manual'] == {'rows': 2, 'income': 49250000, 'expense': 121000}
        assert result['auto'] == {'income': 49250000, 'expense': 121000, 'service': 22000000,
                                  'tip': 27250000, 'report_rows': 2, 'purchase_rows': 1}
        assert result['paid_invoices'] == {'count': 2, 'total': 49250000, 'tip': 27250000}
        assert result['invoice_report_difference'] == 0
    with database.begin() as conn:
        conn.execute(text("UPDATE vera_revenue_entry SET amount=50000000 WHERE transaction_type='Thu' AND transaction_date='2026-09-24'"))
    with database.connect() as conn:
        result = summarize_day(conn, date(2026, 9, 24))
        assert result['manual']['income'] == 50000000
        assert result['auto']['income'] == 49250000


@pytest.fixture
def client(database, monkeypatch):
    ident = SimpleNamespace(role='admin', employee_username='synthetic', full_name='Synthetic', allowed=True)
    def require(conn, identity, feature):
        if not identity.allowed:
            raise HTTPException(403, 'No permission')
    app = FastAPI()
    # Revenue is installed as part of the existing revenue/leave route bundle.
    # Supply the two upstream leave routes just as the production app does.
    app.add_api_route('/v2/leave/records', lambda: {'items': []}, methods=['GET'])
    app.add_api_route('/v2/leave/daily-stats', lambda: {}, methods=['GET'])
    shared = dict(engine_instance=lambda: database, current_identity=lambda: ident,
                  require_feature=require, norm=lambda value: str(value or '').strip().lower(), google_client=lambda: None)
    routes.install_revenue_leave_list_routes(app, **shared, feature_allowed=lambda *args: True, progressive_key=lambda *args: '')
    install_purchase_reconcile_routes(app, **shared)
    install_purchase_routes(app, engine_instance=lambda: database, current_identity=lambda: ident,
                            require_feature=require, feature_allowed=lambda *args: True)
    # Production replaces the base route with V2. Exercise that same HTTP chain,
    # including its forwarding of the shared-report source and cutoff filters.
    monkeypatch.setattr(reconcile, '_comparison', reconcile._comparison)
    monkeypatch.setattr(reconcile_v2, '_dispatch_mismatch_alerts', lambda **kwargs: None)
    reconcile_v2.install_purchase_reconcile_v2(
        app, engine_instance=lambda: database, api_module=None,
        current_identity=lambda: ident, identity_type=SimpleNamespace)
    monkeypatch.setattr(routes, '_dispatch_revenue_admin_push', lambda **kwargs: None)
    with TestClient(app) as client:
        yield client, ident


def enable(client):
    revision = client.get('/v2/revenue/source').json()['revision']
    response = client.put('/v2/revenue/source', json={'source': 'auto', 'revision': revision})
    assert response.status_code == 200, response.text
    return response.json()


def test_daily_totals_cutoff_cash_combo_discount_deleted_and_vietnam_day(database):
    seed(database)
    with database.connect() as conn:
        days = auto.daily(conn)
        result = auto.totals(days)
        assert result == dict(service_revenue=1650, tip_revenue=110, historical_income=0, total_revenue=1760,
                              total_income=1760, total_expense=190.25, net_income=1569.75)
        assert auto.tip_total(conn, date(2026, 9, 16), date(2026, 9, 26), auto=True) == 110
        assert auto.daily(conn, date(2026, 8, 1), date(2026, 9, 4)) == []
        entries = auto.ledger_rows(days)
        assert all(row['date'] >= '2025-09-05' and row['read_only'] for row in entries)
        assert len(entries) == 4
        assert sum(row['amount'] for row in entries if row['type'] == 'Thu') == 1760
        assert sum(row['amount'] for row in entries if row['type'] == 'Chi') == 190.25


def test_all_accounts_see_auto_summary_ledger_export_and_live_source_edits(database, client):
    seed(database)
    http, ident = client
    enable(http)
    for role in ['admin', 'giamdoc', 'quanly', 'letan', 'nhanvien']:
        ident.role = role
        summary = http.get('/v2/revenue/summary?source=manual').json()
        assert summary['source'] == 'auto'
        assert summary['start_date_label'] == '05-09-2025'
        assert summary['total_income'] == 1760 and summary['total_expense'] == 190.25
        assert summary['period_tip'] == 110 and summary['balance'] == 1459.75
        assert not any(summary[key] for key in ['can_create_entry', 'can_edit_entry', 'can_delete_entry', 'can_admin_crud'])
        detail = http.get('/v2/revenue/purchase-reconcile?preset=all').json()
        assert detail['ledger_income'] == summary['total_income']
        assert detail['ledger_expense'] == summary['total_expense']
        assert detail['all_match'] is True
    response = http.get('/v2/revenue/ledger/export.xlsx?preset=all&transaction_type=Chi')
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    exported = list(workbook.active.values)[1:]
    assert sum(row[2] for row in exported) == 190.25
    assert all(row[1] == 'Chi' for row in exported)
    with database.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_report SET deleted_at=now() WHERE resource_id='sale'"))
        conn.execute(text("UPDATE vera_purchase_entry SET amount=60 WHERE amount=40"))
    refreshed = http.get('/v2/revenue/summary').json()
    assert refreshed['total_income'] == 760 and refreshed['total_expense'] == 210.25


@pytest.mark.parametrize('role', ['admin', 'giamdoc', 'quanly', 'letan', 'nhanvien'])
def test_auto_blocks_every_manual_write_including_stale_tabs(database, client, role):
    seed(database)
    http, ident = client
    enable(http)
    ident.role = role
    requests = [
        ('post', '/v2/revenue/entry', {'json': {'transaction_date': '2026-09-25', 'income_amount': 1}}),
        ('patch', '/v2/revenue/entries/1', {'json': {'transaction_type': 'Thu', 'amount': 1}}),
        ('delete', '/v2/revenue/entries/1', {}),
        ('put', '/v2/revenue/tip', {'json': {'amount': 999}}),
        ('post', '/v2/revenue/import.xlsx?mode=replace', {'content': b'not an xlsx'}),
    ]
    for method, path, kwargs in requests:
        result = getattr(http, method)(path, **kwargs)
        assert result.status_code == (403 if 'import' in path and role != 'admin' else 409), (path, result.text)
    with database.connect() as conn:
        assert conn.execute(text('SELECT amount FROM vera_revenue_entry')).scalar() == 777
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry_audit')).scalar() == 0


def test_admin_mode_revision_auth_and_original_manual_tip_survive_switch(database, client):
    seed(database)
    http, ident = client
    with database.begin() as conn:
        routes._save_period_tip(conn, '2026-09-01', '2026-09-25', 88, 'synthetic')
    ident.role = 'quanly'
    assert http.put('/v2/revenue/source', json={'source': 'auto', 'revision': 0}).status_code == 403
    ident.role = 'admin'
    saved = enable(http)
    assert http.put('/v2/revenue/source', json={'source': 'manual', 'revision': 0}).status_code == 409
    response = http.put('/v2/revenue/tip-period', json={'start_date': '2026-09-25', 'end_date': '2026-09-26', 'amount': 999999})
    assert response.status_code == 200 and response.json()['period_tip'] == 110
    assert http.get('/v2/revenue/summary').json()['period_tip'] == 110
    assert http.put('/v2/revenue/source', json={'source': 'manual', 'revision': saved['revision']}).status_code == 200
    result = http.get('/v2/revenue/summary?source=auto').json()
    assert result['source'] == 'manual' and result['total_income'] == 777 and result['period_tip'] == 88
    ident.allowed = False
    assert http.get('/v2/revenue/source').status_code == 403
    assert http.get('/v2/revenue/tip-summary?start=2026-09-05&end=2026-09-06').status_code == 403


def test_mode_switch_cannot_interrupt_or_race_manual_transaction(database, client):
    http, _ = client
    with database.begin() as conn:
        auto.require_manual(conn)
        result = http.put('/v2/revenue/source', json={'source': 'auto', 'revision': 0})
        assert result.status_code == 409
        ledger.insert_web_entries(conn, transaction_date=date(2026, 9, 5), entries=[('Thu', 123, 'Committed first')],
                                  ident=SimpleNamespace(employee_username='synthetic', full_name='Synthetic'))
    enable(http)
    with database.begin() as conn:
        with pytest.raises(HTTPException) as exc:
            auto.require_manual(conn)
        assert exc.value.status_code == 409
        assert conn.execute(text('SELECT amount FROM vera_revenue_entry')).scalar() == 123
    # Reverse interleaving: an uncommitted mode change excludes a manual writer.
    with database.begin() as conn:
        auto.set_mode(conn, 'manual', 1, 'synthetic')
        result = http.post('/v2/revenue/entry', json={'transaction_date': '2026-09-25', 'income_amount': 2})
        assert result.status_code == 409
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar() == 1


def test_auto_uses_all_live_history_without_copying_or_adding_manual_rows(database, client):
    seed(database)
    http, _ = client
    with database.begin() as conn:
        report(conn, 'old-live', '2025-09-05', total=123, tip=3)
        buy(conn, '2025-09-05', 12)
    enable(http)
    result = http.get('/v2/revenue/summary').json()
    assert result['total_income'] == 1883 and result['total_expense'] == 202.25
    assert all(r.get('source') != 'manual_history' for r in result['entries'])
    with database.begin() as conn:
        assert conn.execute(text('SELECT SUM(amount) FROM vera_revenue_entry')).scalar() == 777
        conn.execute(text('UPDATE vera_live_tour_report SET deleted_at=now()'))
    assert http.get('/v2/revenue/summary').json()['total_income'] == 0


def test_realtime_revision_changes_on_edit_delete_and_mode_with_no_money_payload(database, client):
    seed(database)
    http, ident = client
    enable(http)
    before = http.get('/v2/revenue/revision')
    assert before.headers['cache-control'] == 'no-store'
    assert set(before.json()) == {'ok','revision'}
    assert http.get('/v2/revenue/revision').json() == before.json()
    with database.begin() as conn:
        conn.execute(text("UPDATE vera_live_tour_report SET aggregate_revision=2 WHERE resource_id='cash-a'"))
    after = http.get('/v2/revenue/revision').json()
    assert after != before.json()
    with database.begin() as conn:
        conn.execute(text('UPDATE vera_purchase_entry SET revision=revision+1,amount=amount+1 WHERE NOT deleted'))
    latest = http.get('/v2/revenue/revision').json()
    assert latest != after
    with database.begin() as conn:
        conn.execute(text('UPDATE vera_purchase_entry SET revision=revision+1,deleted=true WHERE NOT deleted'))
    after_delete = http.get('/v2/revenue/revision').json()
    assert after_delete != latest
    with database.begin() as conn:
        conn.execute(text('UPDATE vera_revenue_entry SET edit_revision=edit_revision+1,amount=amount+1'))
    after_history = http.get('/v2/revenue/revision').json()
    assert after_history != after_delete
    revision = http.get('/v2/revenue/source').json()['revision']
    assert http.put('/v2/revenue/source', json={'source':'manual','revision':revision}).status_code == 200
    assert http.get('/v2/revenue/revision').json() != after_history
    ident.allowed = False
    assert http.get('/v2/revenue/revision').status_code == 403


def test_auto_summary_cutoff_does_not_add_manual_history(database, client):
    seed(database)
    http, _ = client
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note) VALUES ('Thu',200,'2026-09-24','History'),('Chi',50,'2026-09-24','History')"))
    query = '?time_range=custom&start=2025-09-05&end=2026-09-24'
    manual = http.get('/v2/revenue/summary' + query).json()
    enable(http)
    http.put('/v2/revenue/tip-period', json={'start_date':'2026-09-16','end_date':'2026-09-24'})
    for _ in range(2):
        auto_summary = http.get('/v2/revenue/summary' + query).json()
        assert auto_summary['end_date'] == '2026-09-24'
        assert auto_summary['business_date'] == '2026-09-26'
        assert auto_summary['period_tip_start'] == '2026-09-16'
        assert auto_summary['period_tip_end'] == '2026-09-24'
        assert manual['total_income'] == 977 and manual['total_expense'] == 50
        assert auto_summary['total_income'] == 0 and auto_summary['total_expense'] == 0
        assert all(row['date'] <= '2026-09-24' for row in auto_summary['entries'])
    live = http.get('/v2/revenue/summary').json()
    assert live['total_income'] == 1760 and live['total_expense'] == 190.25
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar() == 3


def test_manual_register_and_export_remain_visible_after_saved_summary_cutoff(database, client):
    http, ident = client
    with database.begin() as conn:
        conn.execute(text("""INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note)
            VALUES ('Thu',49250000,'2026-09-24','Synthetic income'),
                   ('Chi',54000000,'2026-09-24','Synthetic expense A'),
                   ('Chi',202000,'2026-09-24','Synthetic expense B')"""))
    saved = http.put('/v2/revenue/report-period', json={'start_date':'2026-09-16','end_date':'2026-09-21'})
    assert saved.status_code == 200, saved.text
    assert saved.json()['total_income'] == saved.json()['total_expense'] == 0
    for query in ('preset=all', 'preset=custom&start=2026-09-24&end=2026-09-24'):
        response = http.get('/v2/revenue/purchase-reconcile?' + query + '&canonical=true')
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['ledger_row_count'] == 3
        assert data['ledger_income'] == 49250000 and data['ledger_expense'] == 54202000
        assert all(row['date'] == '2026-09-24' and not row.get('read_only') for row in data['ledger_rows'])
        response = http.get('/v2/revenue/ledger/export.xlsx?' + query + '&canonical=true&transaction_date=2026-09-24')
        assert response.status_code == 200, response.text
        sheet = load_workbook(BytesIO(response.content), data_only=True).active
        assert sheet.max_row == 4
        assert sorted(sheet.cell(row, 3).value for row in range(2, 5)) == [202000, 49250000, 54000000]
    current = http.get('/v2/revenue/period-report').json()
    assert current['end_date'] == '2026-09-21'
    assert current['total_income'] == current['total_expense'] == 0
    ident.allowed = False
    assert http.get('/v2/revenue/purchase-reconcile?preset=all&canonical=true').status_code == 403


@pytest.mark.parametrize('end',['2026-09-24','2026-09-25','2026-09-26'])
def test_period_report_keeps_manual_and_auto_sources_independent(database, client, end):
    seed(database)
    http, ident = client
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note) VALUES ('Thu',200,'2026-09-24','History'),('Chi',50,'2026-09-24','History'),('Thu',9999,'2026-09-25','Separate manual register')"))
    path=f'/v2/revenue/period-report?start=2026-09-16&end={end}'
    manual=http.get(path)
    assert manual.status_code==200,manual.text
    manual=manual.json()
    assert manual['report_version']==2 and manual['end_date']==end
    assert manual['period_tip_start']=='2026-09-16' and manual['period_tip_end']==end
    assert 'entries' not in manual,'summary must not return all historical rows'
    raw=http.get('/v2/revenue/purchase-reconcile?preset=all').json()
    assert raw['ledger_income']==10976,'manual records remain available for inspection'
    common=http.get(f'/v2/revenue/purchase-reconcile?preset=all&canonical=true&report_end={end}').json()
    assert common['ledger_income']==manual['total_income']
    assert common['ledger_expense']==manual['total_expense']
    assert all(r['date']<=end for r in common['ledger_rows'])
    assert all(not r.get('read_only', False) for r in common['ledger_rows'])
    exported=http.get(f'/v2/revenue/ledger/export.xlsx?preset=all&canonical=true&report_end={end}')
    assert exported.status_code==200
    values=list(load_workbook(BytesIO(exported.content),read_only=True,data_only=True).active.values)[1:]
    assert sum(r[2] for r in values if r[1]=='Thu')==manual['total_income']
    assert sum(r[2] for r in values if r[1]=='Chi')==manual['total_expense']
    enable(http)
    auto_report=http.get(path).json()
    assert auto_report['period_tip'] == manual['period_tip']
    income, expense = {'2026-09-24': (0,0), '2026-09-25': (1510,150.25), '2026-09-26': (1760,190.25)}[end]
    assert auto_report['total_income'] == income and auto_report['total_expense'] == expense
    assert manual['total_income'] == (977 if end=='2026-09-24' else 10976)
    assert manual['total_expense'] == 50
    assert auto_report['balance']==round(auto_report['net_income']-auto_report['period_tip'],2)
    if end=='2026-09-24':
        assert auto_report['total_income']==0 and auto_report['total_expense']==0
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar()==4
    ident.allowed=False
    assert http.get(path).status_code==403


def test_period_save_is_independent_by_mode_and_rejects_invalid_dates(database, client):
    seed(database)
    http,_=client
    assert http.get('/v2/revenue/source').json()['period_report_version']==2
    saved=http.put('/v2/revenue/report-period',json={'start_date':'2026-09-16','end_date':'2026-09-24'})
    assert saved.status_code==200,saved.text
    assert saved.json()['period_tip']==0 and saved.json()['total_income']==777
    enable(http)
    reopened=http.get('/v2/revenue/period-report').json()
    assert reopened['period_tip_end']==reopened['end_date']=='2026-09-26'
    assert reopened['period_tip']==110 and reopened['total_income']==1760
    for query in ['start=2026-09-16','start=2026-09-25&end=2026-09-24','start=2025-09-04&end=2026-09-24','start=2026-09-16&end=2026-09-27']:
        assert http.get('/v2/revenue/period-report?'+query).status_code==400
    result=http.put('/v2/revenue/report-period',json={'start_date':'2026-09-16','end_date':'2026-09-26'})
    assert result.status_code==200 and result.json()['period_tip']==110
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar()==1
        assert routes._period_tip(conn)['period_end']=='2026-09-24'
        assert routes._period_tip(conn,auto=True)['period_end']=='2026-09-26'


def test_shared_report_uses_one_database_snapshot_during_concurrent_payment_edit(database, client, monkeypatch):
    seed(database)
    http,_=client
    enable(http)
    original=auto.daily
    changed=False
    def during_read(conn,*args,**kwargs):
        nonlocal changed
        assert conn.get_isolation_level()=='REPEATABLE READ'
        assert kwargs.get('include_entries') is False,'do not aggregate historical JSON for card totals'
        result=original(conn,*args,**kwargs)
        if not changed:
            changed=True
            with database.begin() as writer:
                writer.execute(text("UPDATE vera_live_tour_report SET payload=jsonb_set(jsonb_set(payload,'{total}','400'),'{tip}','200') WHERE resource_id='period'"))
        return result
    monkeypatch.setattr(auto,'daily',during_read)
    response=http.get('/v2/revenue/period-report?start=2026-09-16&end=2026-09-26')
    assert response.status_code==200,response.text
    first=response.json()
    assert first['total_income']==1760 and first['period_tip']==110
    again=http.get('/v2/revenue/period-report?start=2026-09-16&end=2026-09-26').json()
    assert again['total_income']==1940 and again['period_tip']==290


@pytest.mark.parametrize('source', ['manual', 'auto'])
def test_production_reconcile_wrapper_preserves_cutoff_defaults_and_validation(database, client, source):
    seed(database)
    http, ident = client
    if source == 'auto':
        enable(http)
    response = http.get('/v2/revenue/purchase-reconcile?preset=all&canonical=true&report_end=2026-09-24')
    assert response.status_code == 200, response.text
    result = response.json()
    assert 'overall_status' in result, 'must exercise the production V2 wrapper'
    assert result['canonical'] is True
    assert result['end_date'] == '2026-09-24'
    assert result['ledger_income'] == (0 if source=='auto' else 777) and result['ledger_expense'] == 0
    assert all(row['date'] <= '2026-09-24' for row in result['ledger_rows'])
    legacy = http.get('/v2/revenue/purchase-reconcile?preset=all')
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()['canonical'] is False
    assert legacy.json()['ledger_income'] == (1760 if source == 'auto' else 777)
    for query in ('report_end=invalid', 'canonical=invalid'):
        assert http.get('/v2/revenue/purchase-reconcile?' + query).status_code == 422
    ident.allowed = False
    assert http.get('/v2/revenue/purchase-reconcile?preset=all&canonical=true&report_end=2026-09-24').status_code == 403


@pytest.mark.parametrize('source', ['manual', 'auto'])
def test_tip_period_matches_reports_calendar_filter_not_operational_day(database, client, source):
    # Synthetic reproduction, not a copy/diagnosis of production invoice data.
    rows = [
        {'business_date': '2026-09-16', 'effective_at': '2026-09-16T12:00:00+07:00', 'tip': 100000000},
        {'business_date': '2026-09-24', 'effective_at': '2026-09-24T23:59:59+07:00', 'tip': 130310000},
        {'business_date': '2026-09-24', 'effective_at': '2026-09-24T17:00:00Z', 'tip': 85410000},
    ]
    with database.begin() as conn:
        for index, row in enumerate(rows):
            report(conn, str(index), total=row['tip'], **row)
    http, _ = client
    if source == 'auto':
        enable(http)
    expected = sum(row['tip'] for row in rows if report_matches(row, date_from='2026-09-16', date_to='2026-09-24', invoice_dates=True))
    assert expected == 230310000
    for path in ('/v2/revenue/period-report', '/v2/revenue/tip-summary'):
        response = http.get(path + '?start=2026-09-16&end=2026-09-24')
        assert response.status_code == 200, response.text
        assert response.json()['period_tip'] == expected
    saved = http.put('/v2/revenue/report-period', json={'start_date': '2026-09-16', 'end_date': '2026-09-24'})
    assert saved.status_code == 200 and saved.json()['period_tip'] == expected
    assert http.get('/v2/revenue/period-report').json()['period_tip'] == expected
    next_day = http.get('/v2/revenue/period-report?start=2026-09-25&end=2026-09-25').json()
    assert next_day['period_tip'] == 85410000
    assert next_day['total_income'] == (315720000 if source=='auto' else 0), 'Auto cash cutoff uses the same calendar date'
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_live_tour_report')).scalar() == 3
        assert conn.execute(text("SELECT SUM((payload->>'tip')::numeric) FROM vera_live_tour_report")).scalar() == 315720000


@pytest.mark.parametrize('database_timezone', ['UTC', 'America/Los_Angeles'])
def test_tip_calendar_date_precedence_offsets_and_naive_times_match_report_list(database, database_timezone):
    rows = [
        {'business_date': '2026-09-25', 'effective_at': '2026-09-24T23:59:59', 'created_at': '2026-09-26T00:00:00Z', 'tip': 10},
        {'business_date': '2026-09-25', 'booked_at': '2026-09-24T16:59:59Z', 'created_at': '2026-09-25T00:00:00Z', 'tip': 20},
        {'business_date': '2026-09-25', 'created_at': '2026-09-24T12:00:00+07:00', 'tip': 30},
        {'business_date': '2026-09-24', 'tip': 40},
        {'business_date': '2026-09-24', 'effective_at': '2026-09-24T17:00:00Z', 'tip': 500},
        {'business_date': '2026-09-24', 'effective_at': '2026-09-23T23:59:59+07:00', 'tip': 600},
        {'recorded_at': '2026-09-24T12:00:00+07:00', 'tip': 700},
    ]
    with database.begin() as conn:
        conn.execute(text('SELECT set_config(\'TimeZone\', :zone, true)'), {'zone': database_timezone})
        for index, row in enumerate(rows):
            report(conn, str(index), total=row['tip'], **row)
        report(conn, 'deleted', '2026-09-24', total=999, tip=999, deleted=True)
        expected = sum(row['tip'] for row in rows if report_matches(row, date_from='2026-09-24', date_to='2026-09-24', invoice_dates=True))
        assert expected == 50
        assert auto.tip_total(conn, date(2026, 9, 24), date(2026, 9, 24)) == expected


def test_single_invoice_day_tip_and_purchase_reports_share_authoritative_rows(database, client):
    http, ident = client
    with database.begin() as conn:
        report(conn, 'today-a', '2026-09-24', effective_at='2026-09-25T00:01:00+07:00', total=20000000, tip=10000000)
        report(conn, 'today-b', '2026-09-25', effective_at='2026-09-25T23:59:00+07:00', total=7000000, tip=5450000)
        report(conn, 'tomorrow', '2026-09-25', effective_at='2026-09-26T00:00:00+07:00', total=999, tip=999)
        for i in range(105):
            buy(conn, '2026-09-25', i+1)
        buy(conn, '2026-09-26', 100)
        conn.execute(text("UPDATE vera_purchase_entry SET note='Nguoi dat', entered_by='Nguoi nhap'"))
    enable(http)
    day=http.get('/v2/revenue/period-report?start=2026-09-25&end=2026-09-25').json()
    assert day['period_tip']==15450000 and day['total_income']==27000000
    http.put('/v2/revenue/report-period',json={'start_date':'2026-09-25','end_date':'2026-09-25'})
    for _ in range(2):
        original=http.get('/v2/purchases?preset=custom&start=2026-09-25&end=2026-09-26').json()
        mirror=http.get('/v2/revenue/purchases?preset=custom&start=2026-09-25&end=2026-09-26').json()
        assert mirror['purchase_total']==original['total']
        assert [r['id'] for r in mirror['purchase_rows']]==[r['id'] for r in original['rows']]
        assert any(r['date']=='2026-09-26' for r in mirror['purchase_rows']), 'purchase filters are independent of TIP cutoff'
        assert all(r['buyer']=='Nguoi dat' and r['user']=='Nguoi nhap' for r in mirror['purchase_rows'])
        with database.begin() as conn:
            conn.execute(text('UPDATE vera_purchase_entry SET amount=20,revision=revision+1 WHERE id=1'))
            conn.execute(text('UPDATE vera_purchase_entry SET deleted=true,revision=revision+1 WHERE id=2'))
    with database.begin() as conn:
        conn.execute(text('UPDATE vera_purchase_entry SET deleted=true'))
    assert http.get('/v2/revenue/purchases?preset=all').json()['purchase_rows']==[]
    assert http.get('/v2/purchases?preset=all').json()['total']==0
    ident.allowed=False
    assert http.get('/v2/revenue/purchases').status_code==403


@pytest.mark.parametrize('source', ['manual', 'auto'])
def test_live_ledger_has_no_implicit_dates_and_export_keeps_explicit_filters(database, client, source):
    http, ident = client
    with database.begin() as conn:
        for key, day, amount in [('old', '2024-01-02', 100), ('selected', '2026-09-24', 200), ('latest', '2026-09-26', 300)]:
            report(conn, key, day, total=amount, tip=10)
            buy(conn, day, amount / 10)
            conn.execute(text("INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note) VALUES ('Thu',:amount,:day,:note)"),
                         {'amount': amount * 2, 'day': day, 'note': key})
        report(conn, 'undated', total=9999)
        report(conn, 'removed', '2026-09-26', total=9999, deleted=True)
        buy(conn, '2026-09-26', 9999, deleted=True)
    if source == 'auto':
        enable(http)
    saved = http.put('/v2/revenue/report-period', json={'start_date': '2026-09-16', 'end_date': '2026-09-21'})
    assert saved.status_code == 200, saved.text
    query = '?preset=all&canonical=true&live_ledger=true&report_end=2026-09-21'
    path = '/v2/revenue/purchase-reconcile'
    response = http.get(path + query)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['live_ledger'] and 'overall_status' in result, 'production wrapper must forward live_ledger'
    assert result['start_date'] == '2024-01-02' and result['end_date'] == '2026-09-26'
    assert result['ledger_income'] == (600 if source == 'auto' else 1200)
    assert result['ledger_expense'] == (60 if source == 'auto' else 0)
    assert {row['date'] for row in result['ledger_rows']} == {'2024-01-02', '2026-09-24', '2026-09-26'}
    for suffix, expected in [(query, result['ledger_income']),
                             (query + '&transaction_date=2026-09-24', 200 if source == 'auto' else 400)]:
        exported = http.get('/v2/revenue/ledger/export.xlsx' + suffix)
        assert exported.status_code == 200, exported.text
        values = list(load_workbook(BytesIO(exported.content), read_only=True, data_only=True).active.values)[1:]
        assert sum(row[2] for row in values if row[1] == 'Thu') == expected
    filtered = http.get(path + '?preset=custom&start=2026-09-24&end=2026-09-24&live_ledger=true').json()
    assert {row['date'] for row in filtered['ledger_rows']} == {'2026-09-24'}
    before = http.get('/v2/revenue/revision').json()
    with database.begin() as conn:
        report(conn, 'new', '2026-09-27', total=400)
        conn.execute(text("INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note) VALUES ('Thu',800,'2026-09-27','new')"))
    assert http.get('/v2/revenue/revision').json() != before
    latest = http.get(path + query).json()
    assert latest['end_date'] == '2026-09-27'
    assert latest['ledger_income'] == (1000 if source == 'auto' else 2000)
    assert http.get('/v2/revenue/period-report').json()['end_date'] == '2026-09-21'
    assert http.get(path + '?live_ledger=invalid').status_code == 422
    ident.allowed = False
    assert http.get(path + query).status_code == 403
    assert http.get('/v2/revenue/ledger/export.xlsx' + query).status_code == 403


def test_live_empty_ledger_and_revision_advance_on_vietnam_midnight(database, client, monkeypatch):
    http, _ = client
    path = '/v2/revenue/purchase-reconcile?preset=all&live_ledger=true'
    before = http.get('/v2/revenue/revision').json()
    empty = http.get(path).json()
    assert empty['ledger_rows'] == [] and empty['ledger_income'] == empty['ledger_expense'] == 0
    assert empty['start_date'] == empty['end_date'] == '2026-09-26'
    class NextDay(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 27, 0, 0, 1, tzinfo=auto.VN_TZ)
    monkeypatch.setattr(auto, 'datetime', NextDay)
    monkeypatch.setattr(reconcile, 'datetime', NextDay)
    assert http.get('/v2/revenue/revision').json() != before
    assert http.get(path).json()['end_date'] == '2026-09-27'
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar() == 0

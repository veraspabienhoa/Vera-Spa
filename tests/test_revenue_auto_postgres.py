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
from vera_web_v2_purchase_reconcile import install_purchase_reconcile_routes


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
        report(conn, 'before', '2026-09-04', total=999999)
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
        assert result == dict(service_revenue=1650, tip_revenue=110, historical_income=777, total_revenue=2537,
                              total_income=2537, total_expense=190.25, net_income=2346.75)
        assert auto.tip_total(conn, date(2026, 9, 16), date(2026, 9, 26), auto=True) == 110
        assert auto.daily(conn, date(2026, 8, 1), date(2026, 9, 4)) == []
        entries = auto.ledger_rows(days)
        assert all(row['date'] >= '2025-09-05' and row['read_only'] for row in entries)
        assert len(entries) == 5
        assert sum(row['amount'] for row in entries if row['type'] == 'Thu') == 2537
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
        assert summary['total_income'] == 2537 and summary['total_expense'] == 190.25
        assert summary['period_tip'] == 110 and summary['balance'] == 2236.75
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
    assert refreshed['total_income'] == 1537 and refreshed['total_expense'] == 210.25


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


def test_history_and_live_periods_never_overlap_or_copy_rows(database, client):
    with database.begin() as conn:
        for day, amount, kind in [('2025-09-04',9999,'Thu'),('2025-09-05',100,'Thu'),
                                  ('2026-09-24',200,'Thu'),('2026-09-24',200,'Thu'),
                                  ('2026-09-24',50,'Chi'),('2026-09-25',9999,'Thu')]:
            conn.execute(text('''INSERT INTO vera_revenue_entry(transaction_date,amount,transaction_type,note)
                VALUES (:day,:amount,:kind,'History')'''),dict(day=day,amount=amount,kind=kind))
        report(conn,'old-overlap','2026-09-24',total=9999)
        report(conn,'new','2026-09-25',total=120,tip=20)
        buy(conn,'2026-09-25',30)
    http,_ = client
    enable(http)
    for _ in range(3):
        result = http.get('/v2/revenue/summary').json()
        assert result['total_income'] == 620 and result['total_expense'] == 80
        history = [r for r in result['entries'] if r.get('source') == 'manual_history']
        assert len(history) == 4 and len({r['id'] for r in history}) == 4
        assert sum(r['amount'] for r in history if r['type']=='Thu') == 500
        assert all(r['date'] <= '2026-09-24' and r['read_only'] for r in history)
    exported_response = http.get('/v2/revenue/ledger/export.xlsx?preset=all')
    assert exported_response.status_code == 200
    book = load_workbook(BytesIO(exported_response.content), read_only=True, data_only=True)
    exported = list(book.active.values)[1:]
    assert len(exported) == 6
    assert sum(r[2] for r in exported if r[1] == 'Thu') == 620
    assert sum(r[2] for r in exported if r[1] == 'Chi') == 80
    filtered = http.get('/v2/revenue/ledger/export.xlsx?preset=all&transaction_type=Thu&note=History')
    book = load_workbook(BytesIO(filtered.content), read_only=True, data_only=True)
    history_exported = list(book.active.values)[1:]
    assert len(history_exported) == 3 and sum(r[2] for r in history_exported) == 500
    with database.begin() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar() == 6
        conn.execute(text("UPDATE vera_live_tour_report SET deleted_at=NOW(),aggregate_revision=2 WHERE resource_id='new'"))
    assert http.get('/v2/revenue/summary').json()['total_income'] == 500, 'deleting Auto must not resurrect excluded Manual entries'
    older = http.get('/v2/revenue/purchase-reconcile?preset=custom&start=2025-09-05&end=2026-09-24').json()
    assert older['ledger_income'] == 500 and older['ledger_expense'] == 50


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


def test_summary_cutoff_matches_manual_history_without_changing_tip_period_or_ledger(database, client):
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
        for key in ['total_income','total_expense','net_income']:
            assert auto_summary[key] == manual[key]
        assert auto_summary['total_income'] == 977 and auto_summary['total_expense'] == 50
        assert all(row['date'] <= '2026-09-24' for row in auto_summary['entries'])
    live = http.get('/v2/revenue/summary').json()
    assert live['total_income'] == 2737 and live['total_expense'] == 240.25
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar() == 3


@pytest.mark.parametrize('end',['2026-09-24','2026-09-25','2026-09-26'])
def test_shared_period_report_has_identical_money_in_manual_and_auto(database, client, end):
    seed(database)
    http, ident = client
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note) VALUES ('Thu',200,'2026-09-24','History'),('Chi',50,'2026-09-24','History'),('Thu',9999,'2026-09-25','Separate manual register')"))
    path=f'/v2/revenue/period-report?start=2026-09-16&end={end}'
    manual=http.get(path)
    assert manual.status_code==200,manual.text
    manual=manual.json()
    assert manual['report_version']==1 and manual['end_date']==end
    assert manual['period_tip_start']=='2026-09-16' and manual['period_tip_end']==end
    assert 'entries' not in manual,'summary must not return all historical rows'
    raw=http.get('/v2/revenue/purchase-reconcile?preset=all').json()
    assert raw['ledger_income']==10976,'manual records remain available for inspection'
    common=http.get(f'/v2/revenue/purchase-reconcile?preset=all&canonical=true&report_end={end}').json()
    assert common['ledger_income']==manual['total_income']
    assert common['ledger_expense']==manual['total_expense']
    assert all(r['date']<=end for r in common['ledger_rows'])
    assert any(not r['read_only'] for r in common['ledger_rows'] if r.get('source')=='manual_history')
    assert all(r['read_only'] for r in common['ledger_rows'] if r.get('source')!='manual_history')
    exported=http.get(f'/v2/revenue/ledger/export.xlsx?preset=all&canonical=true&report_end={end}')
    assert exported.status_code==200
    values=list(load_workbook(BytesIO(exported.content),read_only=True,data_only=True).active.values)[1:]
    assert sum(r[2] for r in values if r[1]=='Thu')==manual['total_income']
    assert sum(r[2] for r in values if r[1]=='Chi')==manual['total_expense']
    enable(http)
    auto_report=http.get(path).json()
    for key in ['total_income','total_expense','total_revenue','service_revenue','tip_revenue','historical_income','net_income','period_tip','balance']:
        assert auto_report[key]==manual[key],key
    assert auto_report['balance']==round(auto_report['net_income']-auto_report['period_tip'],2)
    if end=='2026-09-24':
        assert auto_report['total_income']==977 and auto_report['total_expense']==50
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar()==4
    ident.allowed=False
    assert http.get(path).status_code==403


def test_shared_period_save_remembers_dates_across_modes_and_rejects_invalid_dates(database, client):
    seed(database)
    http,_=client
    assert http.get('/v2/revenue/source').json()['period_report_version']==1
    saved=http.put('/v2/revenue/report-period',json={'start_date':'2026-09-16','end_date':'2026-09-24'})
    assert saved.status_code==200,saved.text
    assert saved.json()['period_tip']==0 and saved.json()['total_income']==777
    enable(http)
    reopened=http.get('/v2/revenue/period-report').json()
    assert reopened['period_tip_end']==reopened['end_date']=='2026-09-24'
    assert reopened['period_tip']==0 and reopened['total_income']==777
    for query in ['start=2026-09-16','start=2026-09-25&end=2026-09-24','start=2025-09-04&end=2026-09-24','start=2026-09-16&end=2026-09-27']:
        assert http.get('/v2/revenue/period-report?'+query).status_code==400
    result=http.put('/v2/revenue/report-period',json={'start_date':'2026-09-16','end_date':'2026-09-26'})
    assert result.status_code==200 and result.json()['period_tip']==110
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar()==1
        assert routes._period_tip(conn)['period_end']=='2026-09-26'
        assert routes._period_tip(conn,auto=True)['period_end']=='2026-09-26'


def test_shared_report_uses_one_database_snapshot_during_concurrent_payment_edit(database, client, monkeypatch):
    seed(database)
    http,_=client
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
    assert first['total_income']==2537 and first['period_tip']==110
    again=http.get('/v2/revenue/period-report?start=2026-09-16&end=2026-09-26').json()
    assert again['total_income']==2717 and again['period_tip']==290


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
    assert result['ledger_income'] == 777 and result['ledger_expense'] == 0
    assert all(row['date'] <= '2026-09-24' for row in result['ledger_rows'])
    legacy = http.get('/v2/revenue/purchase-reconcile?preset=all')
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()['canonical'] is False
    assert legacy.json()['ledger_income'] == (2537 if source == 'auto' else 777)
    for query in ('report_end=invalid', 'canonical=invalid'):
        assert http.get('/v2/revenue/purchase-reconcile?' + query).status_code == 422
    ident.allowed = False
    assert http.get('/v2/revenue/purchase-reconcile?preset=all&canonical=true&report_end=2026-09-24').status_code == 403

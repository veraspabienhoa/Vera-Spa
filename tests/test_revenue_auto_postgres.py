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
            conn.execute(text('CREATE TABLE vera_live_tour_report (resource_id text PRIMARY KEY, payload jsonb, deleted_at timestamptz)'))
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
    conn.execute(text('''INSERT INTO vera_live_tour_report VALUES
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
        report(conn, 'cash-a', '2026-09-05', total=200, tip=25, subtotal=999)
        report(conn, 'cash-b', '2026-09-05', total=200, tip=25, subtotal=999)
        report(conn, 'sale', '2026-09-05', total=1000, type='combo_purchase')
        report(conn, 'use', '2026-09-06', total=30, tip=30, subtotal=700, payment_method='COMBO')
        report(conn, 'legacy', effective_at='2026-09-04T18:00:00Z', total=110, tip=10)
        report(conn, 'deleted', '2026-09-05', total=99999, deleted=True)
        report(conn, 'future', '2099-09-05', total=99999)
        report(conn, 'period', '2026-09-20', total=220, tip=20)
        buy(conn, '2026-09-04', 99999)
        buy(conn, '2026-09-05', 100)
        buy(conn, '2026-09-05', 50.25)
        buy(conn, '2026-09-06', 99999, deleted=True)
        buy(conn, '2026-09-07', 40)
        conn.execute(text("INSERT INTO vera_revenue_entry(transaction_type,amount,transaction_date,note) VALUES ('Thu',777,'2026-09-05','Manual retained')"))


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
        assert result == dict(service_revenue=1650, tip_revenue=110, total_revenue=1760,
                              total_income=1760, total_expense=190.25, net_income=1569.75)
        assert auto.tip_total(conn, date(2026, 9, 16), date(2026, 9, 26), auto=True) == 20
        assert auto.daily(conn, date(2026, 8, 1), date(2026, 9, 4)) == []
        entries = auto.ledger_rows(days)
        assert all(row['date'] >= '2026-09-05' and row['read_only'] for row in entries)
        assert len(entries) == 5
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
        assert summary['start_date_label'] == '05-09-2026'
        assert summary['total_income'] == 1760 and summary['total_expense'] == 190.25
        assert summary['period_tip'] == 20 and summary['balance'] == 1549.75
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
        ('post', '/v2/revenue/entry', {'json': {'transaction_date': '2026-09-05', 'income_amount': 1}}),
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
        routes._save_period_tip(conn, '2026-09-01', '2026-09-05', 88, 'synthetic')
    ident.role = 'quanly'
    assert http.put('/v2/revenue/source', json={'source': 'auto', 'revision': 0}).status_code == 403
    ident.role = 'admin'
    saved = enable(http)
    assert http.put('/v2/revenue/source', json={'source': 'manual', 'revision': 0}).status_code == 409
    response = http.put('/v2/revenue/tip-period', json={'start_date': '2026-09-05', 'end_date': '2026-09-06', 'amount': 999999})
    assert response.status_code == 200 and response.json()['period_tip'] == 90
    assert http.get('/v2/revenue/summary').json()['period_tip'] == 90
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
        result = http.post('/v2/revenue/entry', json={'transaction_date': '2026-09-05', 'income_amount': 2})
        assert result.status_code == 409
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_revenue_entry')).scalar() == 1

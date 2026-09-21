"""Revenue excludes TIP once; combo import follows the independent permission grant."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteEngine, RouteIdentity
from test_live_tour_invoice_permissions import post
from test_live_tour_safety import api_client, payable_state


ROOT = Path(__file__).resolve().parents[1]


def summaries(*groups, filters=None):
    revenue_module = (ROOT / 'web-v2/src/lib/liveTourRevenue.js').as_uri()
    filter_module = (ROOT / 'web-v2/src/lib/liveTourFilters.js').as_uri()
    script = f"""import {{ summarizeTourRevenue }} from {json.dumps(revenue_module)};
import {{ filterTourRows }} from {json.dumps(filter_module)};
const groups = {json.dumps(groups)};
const filters = {json.dumps(filters or {})};
console.log(JSON.stringify(groups.map(rows => summarizeTourRevenue(filterTourRows(rows, filters)))));"""
    result = subprocess.run(['node', '--input-type=module', '-e', script],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_screenshot_totals_and_empty_report():
    assert summaries([{'total': '4350000', 'tip': '600000'}], []) == [
        {'totalRevenue': 4350000, 'serviceRevenue': 3750000, 'tip': 600000},
        {'totalRevenue': 0, 'serviceRevenue': 0, 'tip': 0},
    ]


def test_invoice_and_allocated_reports_agree_after_discount_edit_and_void():
    state = payable_state()
    second = deepcopy(state['employees'][0])
    second.update(id='e2', name='Bình', stt='2')
    state['employees'].append(second)
    invoice = live._checkout(state, {'employee_ids': ['e1', 'e2'], 'discount': 21,
                                   'tip': 31, 'payment_method': 'TIỀN MẶT'}, 'admin', NOW, False)
    expected = {'totalRevenue': 210, 'serviceRevenue': 179, 'tip': 31}
    assert summaries(state['invoices'], state['reports']) == [expected, expected]
    live._apply_action(state, 'paid_invoice_update', {'invoice_id': invoice['id'],
        'reason': 'Đối soát', 'tip': 41, 'discount': 11}, 'admin', NOW)
    expected = {'totalRevenue': 230, 'serviceRevenue': 189, 'tip': 41}
    assert summaries(state['invoices'], state['reports']) == [expected, expected]
    live._apply_action(state, 'paid_invoice_delete', {'invoice_id': invoice['id'],
        'reason': 'Hủy hóa đơn'}, 'admin', NOW)
    assert summaries(state['invoices'], state['reports']) == [
        {'totalRevenue': 0, 'serviceRevenue': 0, 'tip': 0},
        {'totalRevenue': 0, 'serviceRevenue': 0, 'tip': 0},
    ]


def test_totals_use_filtered_rows_including_tip_only_and_combo_sales():
    rows = [
        {'total': 3000000, 'tip': 0, 'service': 'Combo 13', 'customer_name': 'Anh Tuấn', 'effective_at': '2026-09-10T09:00:00+07:00'},
        {'total': 200000, 'tip': 200000, 'service': 'Body', 'customer_name': 'Anh Tuấn', 'effective_at': '2026-09-10T10:00:00+07:00'},
        {'total': 9000000, 'tip': 100000, 'service': 'Body', 'customer_name': 'Khách khác', 'effective_at': '2026-09-09T10:00:00+07:00'},
    ]
    assert summaries(rows, filters={'date_from': '2026-09-10', 'customer': 'anh tuan'}) == [
        {'totalRevenue': 3200000, 'serviceRevenue': 3000000, 'tip': 200000},
    ]
    assert summaries(rows, filters={'service': 'Combo'}) == [
        {'totalRevenue': 3000000, 'serviceRevenue': 3000000, 'tip': 0},
    ]


class ImportIdentity(RouteIdentity):
    role: str = ''


def import_client(monkeypatch, role, grants=None):
    state = payable_state()
    state['combos'] = [{'id': 'import-combo', 'name': 'Combo 13', 'tickets': 13, 'price': 3000000, 'active': True}]
    _, shared = api_client(monkeypatch, state)
    app = FastAPI()
    allowed = set(grants or ({'live_tour_combo_import', 'live_tour_customers_view'} if role == 'admin' else set()))
    live.install_live_tour_routes(app, engine_instance=RouteEngine,
        current_identity=lambda: ImportIdentity(role=role), require_feature=lambda _conn, _ident, feature: None if feature in allowed else (_ for _ in ()).throw(Exception('denied')),
        feature_allowed=lambda _conn, _identity, feature: feature in allowed, identity_type=ImportIdentity)
    return TestClient(app, raise_server_exceptions=False), shared


@pytest.mark.parametrize('role', ['letan', 'quanly', 'leader', 'nhanvien', 'locker', 'tapvu', ''])
def test_combo_import_denied_without_independent_grant(monkeypatch, role):
    client, shared = import_client(monkeypatch, role, {'live_tour_customers_view'})
    before = deepcopy(shared)
    row = {'customer_name': 'Khách', 'combo_id': 'import-combo', 'remaining': 5, 'total': 5}
    response = post(client, shared, 'combo_import', row)
    assert response.status_code != 200
    assert shared == before


@pytest.mark.parametrize('role', ['letan', 'quanly', 'leader'])
def test_combo_import_allowed_when_feature_is_granted(monkeypatch, role):
    client, shared = import_client(monkeypatch, role, {'live_tour_combo_import', 'live_tour_customers_view'})
    row = {'customer_name': 'Khách', 'combo_id': 'import-combo', 'remaining': 5, 'total': 5}
    response = post(client, shared, 'combo_import', row)
    assert response.status_code == 200, response.text
    assert shared['state']['customers'][0]['combo_purchases'][0]['remaining'] == 5


def test_admin_can_import_combo_for_selected_existing_customer(monkeypatch):
    client, shared = import_client(monkeypatch, 'admin')
    existing = {'id': 'customer-1', 'name': 'Nguyễn An', 'phone': '0901234567', 'combo_purchases': []}
    shared['state']['customers'] = [existing]
    payload = {'purchases': [{'customer_id': existing['id'], 'customer_name': existing['name'],
        'customer_phone': existing['phone'], 'combo_id': 'import-combo', 'total': 4, 'used': 0}]}

    response = post(client, shared, 'combo_import', payload)

    assert response.status_code == 200, response.text
    assert len(shared['state']['customers']) == 1
    assert shared['state']['customers'][0]['combo_purchases'][0]['remaining'] == 4


def test_admin_can_import_and_retry_without_recording_new_revenue(monkeypatch):
    client, shared = import_client(monkeypatch, 'admin')
    payload = {'purchases': [{'customer_name': 'Khách nhập', 'combo_id': 'import-combo', 'total': 5, 'used': 0}]}
    response = post(client, shared, 'combo_import', payload, idempotency_key='admin-import-123')
    assert response.status_code == 200, response.text
    assert response.json()['result']['imported'] == 1
    assert shared['state']['customers'][0]['combo_purchases'][0]['remaining'] == 5
    before = deepcopy(shared)
    response = post(client, shared, 'combo_import', payload, idempotency_key='admin-import-123')
    assert response.status_code == 200
    assert shared == before
    assert not shared['state']['invoices'] and not shared['state']['reports']


def test_frontend_import_uses_independent_combo_import_grant():
    source = (ROOT / 'web-v2/src/pages/LiveTourPage.jsx').read_text()
    helper = source[source.index('const PAYMENT_ACTIONS'):source.index('function LiveTourModal')]
    script = helper + """
const cases = [
  {comboImport: false, customers: true},
  {comboImport: true, customers: false},
  {comboImport: true, customers: true},
];
console.log(JSON.stringify(cases.map(grants => canRunAction('combo_import', grants))));
"""
    result = subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [False, False, True]
    assert "live_tour_combo_import" in source

"""Revenue excludes TIP once; importing combo balances is an Admin-only action."""
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


def import_client(monkeypatch, role):
    state = payable_state()
    state['combos'] = [{'id': 'import-combo', 'name': 'Combo 13', 'tickets': 13, 'price': 3000000, 'active': True}]
    _, shared = api_client(monkeypatch, state)
    app = FastAPI()
    # Grant every feature to prove delegated Live Tour admin cannot bypass role checks.
    live.install_live_tour_routes(app, engine_instance=RouteEngine,
        current_identity=lambda: ImportIdentity(role=role), require_feature=lambda *_args: None,
        feature_allowed=lambda *_args: True, identity_type=ImportIdentity)
    return TestClient(app), shared


@pytest.mark.parametrize('role', ['letan', 'quanly', 'leader', 'nhanvien', 'locker', 'tapvu', ''])
@pytest.mark.parametrize('batch', [False, True])
def test_non_admin_cannot_import_even_with_all_features(monkeypatch, role, batch):
    client, shared = import_client(monkeypatch, role)
    before = deepcopy(shared)
    row = {'customer_name': 'Khách', 'combo_id': 'import-combo', 'remaining': 5, 'total': 5}
    response = post(client, shared, 'combo_import', {'purchases': [row]} if batch else row)
    assert response.status_code == 403
    assert response.json()['detail'] == 'Chỉ Admin được nhập combo.'
    assert shared == before


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


def test_frontend_import_requires_admin_role_as_well_as_grants():
    source = (ROOT / 'web-v2/src/pages/LiveTourPage.jsx').read_text()
    helper = source[source.index('const PAYMENT_ACTIONS'):source.index('function LiveTourModal')]
    script = helper + """
const grants = {admin: true, payment: true, customers: true};
console.log(JSON.stringify([false, true].map(isAdmin => canRunAction('combo_import', {...grants, isAdmin}))));
"""
    result = subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [False, True]

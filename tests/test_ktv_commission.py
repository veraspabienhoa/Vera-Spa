from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest

from vera_web_v2_commission import record_commission, refresh_commission, payroll_commissions
from test_hr_departments import setup


def context(enabled=True):
    return {'policy': {'enabled': enabled, 'rates': {
        'leader': {'service': 20, 'product': 10},
        'nhanvien': {'service': 10, 'product': 5}}},
        'departments': {'a': 'leader', 'b': 'nhanvien', 'c': 'locker'}}


def entry(name, price, kind='service'):
    return {'employee_name': name, 'price': price, 'service_items': [
        {'service_id': kind, 'quantity': 1, 'unit_price': price, 'revenue_kind': kind}]}


def invoice(entries, **extra):
    return {'id': 'i', 'business_date': '2026-10-07', 'entries': entries,
            'subtotal': sum(row['price'] for row in entries), 'discount': 0, 'tip': 100000, **extra}


def state(inv, purchase=None, units=None):
    return {'customers': [{'id': 'customer', 'combo_purchases': [purchase] if purchase else []}],
            'reports': [{'invoice_id': inv['id'], 'combo_units': unit} for unit in (units or [0] * len(inv['entries']))]}


def test_service_product_net_discount_tip_is_excluded_and_department_rates():
    inv = invoice([entry('a', 200000), entry('b', 100000, 'product')], discount=30000)
    record_commission(inv, state(inv), context())
    assert inv['commission']['rows'][0]['service'] == 36000
    assert inv['commission']['rows'][1]['product'] == 4500
    assert inv['tip'] == 100000
    inv['tip'] = 999999
    refresh_commission(inv)
    assert sum(row['service'] + row['product'] for row in inv['commission']['rows']) == 40500


@pytest.mark.parametrize('enabled,purchased', [(False, False), (True, True)])
def test_default_off_and_initial_combo_sale_never_accrue(enabled, purchased):
    inv = invoice([entry('a', 200000)], **({'purchased_combo_id': 'p'} if purchased else {}))
    record_commission(inv, state(inv), context(enabled))
    assert 'commission' not in inv


def test_combo_price_divided_by_original_total_tickets_not_remaining_or_list_price():
    inv = invoice([entry('a', 800000), entry('b', 400000)],
                  customer_id='customer', combo_purchase_id='p', subtotal=0)
    purchase = {'id': 'p', 'price': 1000000, 'total': 10, 'remaining': 3}
    record_commission(inv, state(inv, purchase, [2, 1]), context())
    assert [row['service'] for row in inv['commission']['rows']] == [40000, 10000]
    purchase.update(price=9000000, total=99)
    refresh_commission(inv)
    assert [row['service'] for row in inv['commission']['rows']] == [40000, 10000]


def test_combo_with_separate_product_extra_and_multiple_consumed_tickets():
    row = entry('a', 300000, 'product')
    row.update(quick_extra_subtotal=300000, commission_cash_items=deepcopy(row['service_items']))
    inv = invoice([row], customer_id='customer', combo_purchase_id='p', discount=30000)
    record_commission(inv, state(inv, {'id': 'p', 'price': 1000000, 'total': 10}, [2]), context())
    assert inv['commission']['rows'][0]['service'] == 40000
    assert inv['commission']['rows'][0]['product'] == 27000


def test_unassigned_and_other_departments_do_not_receive_commission():
    inv = invoice([entry('', 100000), entry('c', 100000)])
    record_commission(inv, state(inv), context())
    assert inv['commission']['rows'] == []


def test_correction_uses_original_rates_and_recalculates_discount():
    inv = invoice([entry('a', 200000)])
    ctx = context()
    record_commission(inv, state(inv), ctx)
    ctx['policy']['rates']['leader']['service'] = 99
    inv.update(subtotal=100000, discount=20000)
    inv['entries'][0]['price'] = 100000
    refresh_commission(inv)
    assert inv['commission']['rows'][0]['service'] == 16000


def test_payroll_uses_current_ledger_period_dedup_and_retains_accrual_after_disabled(monkeypatch):
    import vera_web_v2_payroll as payroll
    import vera_live_tour_resource_store as store
    inv = invoice([entry('a', 200000)])
    record_commission(inv, state(inv), context())
    outside = deepcopy(inv); outside.update(id='outside', business_date='2026-09-30')
    old = invoice([entry('a', 900000)]); old['id'] = 'legacy'
    monkeypatch.setattr(payroll, '_setting', lambda conn, key, default: {'commission': {'enabled': False, 'ever_enabled': True}})
    monkeypatch.setattr(store, 'enabled', lambda: True)
    conn = object()
    def read(actual, collections):
        assert actual is conn and collections == {'invoices'}
        return {'invoices': [inv, inv, outside, old]}, 0, None
    monkeypatch.setattr(store, 'read', read)
    assert payroll_commissions(conn, date(2026,10,1), date(2026,10,15), str.lower) == {'a': {'service':40000, 'product':0}}
    monkeypatch.setattr(store, 'read', lambda *args, **kwargs: ({'invoices': []}, 0, None))
    assert payroll_commissions(conn, date(2026,10,1), date(2026,10,15), str.lower) == {}


def test_admin_config_validates_percent_conflicts_and_preserves_accrual_flag(setup):
    client, saved, _, identity, _ = setup
    body = {'enabled': True, 'leader': {'service': 20, 'product': 10}, 'nhanvien': {'service': 10, 'product': 5}, 'revision': 0}
    assert client.get('/v2/hr').json()['commission']['enabled'] is False
    assert client.put('/v2/hr/commission', json=body).status_code == 200
    assert client.put('/v2/hr/commission', json=body).status_code == 409
    body.update(revision=1, enabled=False)
    assert client.put('/v2/hr/commission', json=body).status_code == 200
    assert saved['hr_registry']['commission']['ever_enabled'] is True
    body.update(revision=2); body['leader']['service'] = 101
    assert client.put('/v2/hr/commission', json=body).status_code == 422
    identity.role = 'leader'
    assert client.put('/v2/hr/commission', json=body).status_code in {403, 422}
    body['leader']['service'] = 20
    assert client.put('/v2/hr/commission', json=body).status_code == 403


@pytest.mark.parametrize('tip', [0, 100000])
def test_canonical_payroll_adds_commission_preserves_full_tip_and_deductions(monkeypatch, tip):
    import asyncio
    import vera_web_v2_payroll as payroll
    import vera_web_v2_commission as commission
    import vera_attendance_participation as participation
    from fastapi import FastAPI
    from vera_web_v2_payroll_timesoft_auto import _workbook
    person = {'username': 'a', 'full_name': 'Test', 'role': 'leader', 'email': '', 'bank_account': '', 'bank_name': '', 'employment_status': 'Đang làm việc'}
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, *args):
            rows = [person] if 'FROM employees' in str(sql) else [{'employee_name': 'a', 'amount': 1000}]
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    conn = Conn()
    monkeypatch.setattr(payroll, '_config', lambda c: {**payroll.DEFAULT_CONFIG, 'default_living_expense': 0, 'default_locker_support': 0})
    monkeypatch.setattr(payroll, '_tichluy_map', lambda *args: {})
    monkeypatch.setattr(payroll, '_obligation_map', lambda *args: {})
    monkeypatch.setattr(payroll, '_accumulation_refund_map', lambda *args: {})
    monkeypatch.setattr(participation, 'eligible', lambda people, *args, **kw: people)
    def earned(actual, *args):
        assert actual is conn
        return {'a': {'service': 20000, 'product': 5000}}
    monkeypatch.setattr(commission, 'payroll_commissions', earned)
    app = FastAPI()
    payroll.install_payroll_routes(app, engine_instance=lambda: SimpleNamespace(connect=lambda: conn), current_identity=lambda: None,
        require_feature=lambda *args: None, norm=lambda name: str(name).lower(), identity_type=SimpleNamespace, google_client=lambda: None)
    route = next(route for route in app.routes if getattr(route, 'path', '') == '/v2/payroll/calculate')
    content = _workbook([{'time': '07/10/2026', 'item': 'TIP', 'amount': tip, 'employee': 'a'}])
    result = asyncio.run(route.endpoint(month='2026-10', period_no=1, payload=content, ident=SimpleNamespace()))
    row = result['rows'][0]
    assert row['Tiền Lương'] == tip + 25000
    assert row['Số tiền thực nhận'] == tip + 24000
    assert row['__earnings'] == {'tip': tip, 'service': 20000, 'product': 5000}
    assert result['source_summary']['commission_total'] == 25000


def test_checkout_route_snapshots_once_and_replay_does_not_accrue_twice(monkeypatch):
    from datetime import datetime, timedelta
    import vera_web_v2_live_tour as live
    import vera_web_v2_hr as hr
    from test_live_tour_quick_booking import scenario
    from test_live_tour_safety import api_client
    from test_live_tour_backend import RouteConnection
    st, payload = scenario()
    payload['quick_booking']['booked_at'] = live._iso(datetime.now(live.VN_TZ) - timedelta(minutes=1))
    monkeypatch.setattr(hr, 'registry', lambda conn: {'commission': context()['policy']})
    execute = RouteConnection.execute
    def query(self, sql, *args, **kw):
        if 'AS department FROM employees' in str(sql):
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [{'username': 'An', 'department': 'leader'}]))
        return execute(self, sql, *args, **kw)
    monkeypatch.setattr(RouteConnection, 'execute', query)
    client, shared = api_client(monkeypatch, st)
    body = {'action': 'quick_checkout', 'payload': payload, 'idempotency_key': 'commission-replay', 'expected_revision': 1}
    first = client.post('/v2/live-tour/action', json=body)
    assert first.status_code == 200, first.text
    second = client.post('/v2/live-tour/action', json=body)
    assert second.status_code == 200, second.text
    assert len(shared['state']['invoices']) == 1
    inv = shared['state']['invoices'][0]
    assert inv['commission']['rows'][0]['service'] > 0
    assert first.json()['result']['invoice']['commission'] == second.json()['result']['invoice']['commission']


def test_paid_correction_and_void_change_commission_in_same_ledger(monkeypatch):
    import vera_web_v2_live_tour as live
    from test_live_tour_invoice_permissions import paid_state
    from test_live_tour_backend import NOW
    st, inv = paid_state()
    name = inv['entries'][0]['employee_name']
    ctx = context(); ctx['departments'][name] = 'leader'
    record_commission(inv, st, ctx)
    result = live._apply_action(st, 'paid_invoice_update', {'invoice_id': inv['id'], 'reason': 'Test correction', 'discount': 0, 'entries': [{'index': 0, 'price': 100000}]}, 'admin', NOW, admin_invoice_override=True)
    assert result['invoice']['commission']['rows'][0]['service'] == 20000
    assert st['invoice_changes'][-1]['after']['commission'] == result['invoice']['commission']
    result = live._apply_action(st, 'paid_invoice_delete', {'invoice_id': inv['id'], 'reason': 'Test void'}, 'admin', NOW, admin_invoice_override=True)
    assert result['voided'] is True
    assert st['invoices'] == []

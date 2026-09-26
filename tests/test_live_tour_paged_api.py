from copy import deepcopy
import json

import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_server_only import SettingsDatabase, app_client


def sample():
    state = state_with(employee('e1','An'))
    state['customers'] = [{'id':f'c{i}','name':f'Khách {i}','phone':f'090{i:07}','combo_purchases':[]} for i in range(125)]
    state['invoices'] = [{'id':f'i{i}','bill_no':f'HD{i}','total':100,'tip':10,'created_at':NOW.isoformat(),'entries':[]} for i in range(125)]
    state['reports'] = [{'id':f'r{i}','invoice_id':f'i{i}','employee_name':'An','service':'Body','total':100,'tip':10,'created_at':NOW.isoformat()} for i in range(125)]
    return state


def test_board_omits_ledger_and_keeps_capabilities():
    state = sample()
    _,client=app_client(SettingsDatabase(state))
    full=client.get('/v2/live-tour').json()
    board=client.get('/v2/live-tour?view=board').json()
    assert board['records'] == full['records']
    assert board['capabilities'] == full['capabilities']
    assert board['customers'] == board['report_rows'] == board['state']['invoices'] == []
    assert len(json.dumps(board)) < len(json.dumps(full)) / 2


def test_customer_pages_and_search_are_filtered_before_slicing():
    _,client=app_client(SettingsDatabase(sample()))
    first=client.get('/v2/live-tour/collections/customers?page_size=50').json()
    second=client.get('/v2/live-tour/collections/customers?page_size=50&page=2').json()
    assert first['total']==125 and first['pages']==3
    assert len(first['data']['customers'])==50
    assert not {row['id'] for row in first['data']['customers']} & {row['id'] for row in second['data']['customers']}
    exact=client.get('/v2/live-tour/collections/customers?customer_id=c0').json()
    assert [row['id'] for row in exact['data']['customers']]==['c0']
    assert client.get('/v2/live-tour/collections/customers?page_size=1000').status_code==422


def test_reports_total_covers_all_matching_pages_and_receipts_stay_available():
    _,client=app_client(SettingsDatabase(sample()))
    result=client.get('/v2/live-tour/collections/reports?page_size=10').json()
    assert result['data']['report_totals']=={'totalRevenue':12500,'tip':1250,'serviceRevenue':11250,'invoiceCount':125}
    assert len(result['data']['report_rows'])==10
    assert len(result['data']['state']['invoices'])==10


def test_paid_invoice_total_is_64_across_50_and_14_row_pages_using_invoice_date():
    state = sample()
    for key in ('invoices', 'reports'):
        state[key] = state[key][:65]
        for index, row in enumerate(state[key]):
            row.update(effective_at='2026-09-26T10:00:00+07:00' if index < 64 else '2026-09-25T10:00:00+07:00',
                       business_date='2026-09-24', created_at='2026-09-24T10:00:00+07:00')
    # A second employee line belongs to the same invoice, not an extra bill.
    state['reports'].append(dict(state['reports'][0], id='second-line', total=20, tip=5))
    state['invoices'][0].update(total=120, tip=15)
    _, client = app_client(SettingsDatabase(state))
    query = '?date_from=2026-09-26&date_to=2026-09-26'
    first = client.get('/v2/live-tour/collections/invoices' + query).json()
    second = client.get('/v2/live-tour/collections/invoices' + query + '&page=2').json()
    assert first['total'] == second['total'] == 64
    assert first['pages'] == second['pages'] == 2
    rows = first['data']['state']['invoices'] + second['data']['state']['invoices']
    assert len(first['data']['state']['invoices']) == 50
    assert len(second['data']['state']['invoices']) == 14
    assert len({row['id'] for row in rows}) == 64
    summary = client.get('/v2/live-tour/collections/reports' + query).json()['data']['report_totals']
    assert summary['invoiceCount'] == 64
    assert summary['totalRevenue'] == sum(row['total'] for row in rows)
    empty = client.get('/v2/live-tour/collections/invoices?date_from=2026-09-24&date_to=2026-09-24').json()
    assert empty['total'] == 0 and empty['data']['state']['invoices'] == []


def test_combo_index_matches_reference_and_does_not_mutate_ledger():
    state=sample()
    purchase={'id':'p1','remaining':10,'component_balances':[{'service_id':'s','remaining':10}]}
    state['employees'][0].update(service='Body',customer_id='c0',combo_purchase_id='p1',combo_reserved_units=2,combo_reserved_components=[{'service_id':'s','units':2}])
    state['pending']=[{'id':'pending','customer_id':'c0','entries':[{'combo_purchase_id':'p1','combo_reserved_units':3,'combo_reserved_components':[{'service_id':'s','units':3}]}]}]
    original=deepcopy(state)
    assert live._available_combo(state,'c0',purchase)==live._available_combo(state,'c0',purchase,reservation_index=live._combo_reservations(state))
    assert state==original
    assert purchase['remaining']==10


def test_name_search_preserves_phrase_and_formatted_phone_semantics():
    from vera_live_tour_lists import customer_matches
    assert customer_matches({'name':'An An','phone':'0901234567'},'an an 090 123')
    assert not customer_matches({'name':'Vân Anh'},'An An')
    assert customer_matches({'name':'Ngọc Anh','phone':'+84901234567'},'ngoc a 090123')


def test_relational_panels_match_legacy_without_reading_unrelated_ledgers(monkeypatch):
    state = sample()
    state['idempotency'] = {'private-response': {'large': 'cached action'}}
    state['audit'] = [{'id': 'audit1', 'created_at': NOW.isoformat()}]
    state['backups'] = [{'id': 'backup1', 'created_at': NOW.isoformat()}]
    _, client = app_client(SettingsDatabase(state))
    panels = ('customers', 'pending', 'invoices', 'reports', 'history')
    expected = {panel: client.get(f'/v2/live-tour/collections/{panel}?page_size=10').json() for panel in panels}
    reads = []
    def scoped_read(conn, collections=None):
        assert collections is not None
        reads.append(set(collections))
        value = deepcopy(state)
        value.pop('idempotency')
        for key in live.relational_store.RESOURCE_COLLECTIONS:
            if key not in collections:
                value[key] = []
        return value, 7, {}
    monkeypatch.setattr(live.resource_store, 'enabled', lambda: True)
    monkeypatch.setattr(live.resource_store, 'read', scoped_read)
    for panel in panels:
        response = client.get(f'/v2/live-tour/collections/{panel}?page_size=10')
        assert response.status_code == 200, response.text
        assert response.json() == expected[panel]
    assert 'pending' in reads[0]
    assert {'reports', 'invoices'} <= reads[3]
    assert all('backups' not in scope and 'audit' not in scope for scope in reads[:4])
    assert all('customers' not in scope for scope in reads[1:])

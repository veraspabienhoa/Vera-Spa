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

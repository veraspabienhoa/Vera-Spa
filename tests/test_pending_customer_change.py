from copy import deepcopy
import pytest
from fastapi import HTTPException
import vera_web_v2_live_tour as live
import vera_live_tour_resource_store as store
from test_live_tour_combo_booking import setup, booking
from test_service_catalog import action
from test_live_tour_invoice_permissions import scoped_client, post, ALL
from test_live_tour_backend import NOW


def cash_pending():
    state,skin,body,customer,owned=setup()
    action(state,'booking',{**booking(customer,owned,skin),'customer_id':'','combo_purchase_id':''})
    action(state,'start',{'employee_id':'e1'})
    pending=action(state,'finish_to_pending',{'employee_id':'e1'})['pending']
    # finish_to_pending commits a deep-copy transaction; return the live fixture.
    customer=next(row for row in state['customers'] if row['id']==customer['id'])
    owned=next(row for row in customer['combo_purchases'] if row['id']==owned['id'])
    return state,pending,customer,owned


def test_pending_cash_combo_cash_preserves_completed_work_and_releases_reservations():
    state,pending,customer,owned=cash_pending()
    before=deepcopy(state)
    args={'pending_id':pending['id'],'reason':'Correct customer','customer_id':customer['id'],'combo_purchase_id':owned['id']}
    result=action(state,'pending_update',args)['pending']
    assert result['customer_id']==customer['id'] and result['combo_purchase_id']==owned['id']
    assert result['entries'][0]['combo_reserved_units']==1
    assert live._available_combo(state,customer['id'],owned)['remaining']==2
    assert state['employees']==before['employees'] and state['customers']==before['customers']
    assert state['invoices']==before['invoices'] and state['reports']==before['reports']
    changed=action(state,'pending_update',{**args,'customer_id':'','combo_purchase_id':''})['pending']
    assert changed['customer_id']==changed['customer_name']==changed['customer_phone']==changed['combo_purchase_id']==''
    assert all(not row['combo_purchase_id'] and row['combo_reserved_units']==0 and row['combo_reserved_components']==[] for row in changed['entries'])
    assert changed['entries'][0]['price']==pending['entries'][0]['price']
    assert live._available_combo(state,customer['id'],owned)['remaining']==3
    assert state['pending_changes'][-1]['before']==result


@pytest.mark.parametrize('problem',['wrong_customer','exhausted','expired','multiple_entries','other_reservation'])
def test_invalid_pending_retarget_rolls_back_without_consuming_tickets(problem):
    state,pending,customer,owned=cash_pending()
    customer_id=customer['id']
    if problem=='wrong_customer':
        state['customers'].append({'id':'other','name':'Other','combo_purchases':[]});customer_id='other'
    elif problem=='exhausted':owned['remaining']=0
    elif problem=='expired':owned['unlimited']=False;owned['expires_on']='2026-09-04'
    elif problem=='multiple_entries':pending['entries'].append({**deepcopy(pending['entries'][0]),'employee_id':'e2'})
    else:
        skin=next(row for row in state['services'] if row['id']==pending['entries'][0]['service_items'][0]['service_id'])
        action(state,'booking',booking(customer,owned,skin,worker='e2'))
    before=deepcopy(state)
    with pytest.raises(HTTPException):action(state,'pending_update',{'pending_id':pending['id'],'reason':'Test','customer_id':customer_id,'combo_purchase_id':owned['id']})
    assert state==before


def test_pending_retarget_http_permissions_replay_and_both_customer_locks(monkeypatch):
    state,pending,customer,owned=cash_pending()
    payload={'pending_id':pending['id'],'reason':'Correct','customer_id':customer['id'],'combo_purchase_id':owned['id']}
    client,shared=scoped_client(monkeypatch,state,ALL-{'live_tour_customers_view'})
    assert post(client,shared,'pending_update',payload).status_code==403
    client,shared=scoped_client(monkeypatch,state,ALL)
    result=post(client,shared,'pending_update',payload,idempotency_key='retarget-once-123')
    assert result.status_code==200,result.text
    before=deepcopy(shared)
    assert post(client,shared,'pending_update',payload,idempotency_key='retarget-once-123',expected_revision=1).json()['duplicate']
    assert shared==before
    resources=store.action_resources(shared['state'],'pending_update',{**payload,'customer_id':'another'},'new-key')
    assert ('live_tour_customer',customer['id']) in resources and ('live_tour_customer','another') in resources
    assert ('live_tour_pending',pending['id']) in resources
    paid=post(client,shared,'checkout',{'pending_id':pending['id'],'payment_method':'COMBO','combo_purchase_id':owned['id']},idempotency_key='retarget-pay-once')
    assert paid.status_code==200,paid.text
    assert shared['state']['customers'][0]['combo_purchases'][0]['remaining']==2
    assert post(client,shared,'checkout',{'pending_id':pending['id'],'payment_method':'COMBO','combo_purchase_id':owned['id']},idempotency_key='retarget-pay-once').json()['duplicate']
    assert shared['state']['customers'][0]['combo_purchases'][0]['remaining']==2

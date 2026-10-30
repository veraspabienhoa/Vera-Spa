from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from vera_web_v2_live_tour_invoice import change_paid_invoice
from vera_web_v2_live_tour_payment import payment_values


def snapshot(extra=200000, total=700000):
    invoice = dict(id='synthetic', payment_method='COMBO', combo_purchase_id='ticket', customer_id='customer',
                   entries=[dict(price=550000, combo_extra_subtotal=extra, service='Covered + extra')],
                   subtotal=extra, combo_extra_subtotal=extra, combo_covered_amount=550000-extra,
                   discount=0, tip=500000, total=total, combo_units=1,
                   combo_component_debits=[dict(service_id='covered', units=1)])
    return dict(invoices=[invoice], reports=[dict(invoice_id='synthetic',total=total,tip=500000)],
                customers=[dict(id='customer',combo_purchases=[dict(id='ticket',remaining=4,used=1)])],
                employees=[],pending=[],combo_usage=[dict(invoice_id='synthetic',units=1)])


def update(state, **changes):
    return change_paid_invoice(state, 'paid_invoice_update', {'invoice_id':'synthetic','reason':'Synthetic correction',**changes},
        'synthetic', datetime(2026,10,30,tzinfo=timezone.utc), money=lambda value,**kwargs:int(value or 0),
        payment_values=payment_values,canonical_method=lambda value,**kwargs:value,available_combo=lambda *args: {},
        iso=lambda value:value.isoformat(),max_money=10_000_000_000)['invoice']


@pytest.mark.parametrize('changes,expected', [({'note':'Updated note'},700000),({'tip':600000},800000),({'tip':0},200000)])
def test_paid_combo_correction_keeps_extra_services_in_total_and_reports(changes, expected):
    state=snapshot();before=deepcopy(state)
    invoice=update(state,**changes)
    assert invoice['total']==expected
    assert invoice['subtotal']==invoice['combo_extra_subtotal']==200000
    assert invoice['combo_covered_amount']==350000
    assert state['reports'][0]['total']==expected
    for key in ('customers','combo_usage','employees','pending'):
        assert state[key]==before[key]
    assert invoice['combo_component_debits']==before['invoices'][0]['combo_component_debits']
    assert state['invoice_changes'][-1]['before']==before['invoices'][0]


def test_legacy_prepaid_combo_stays_tip_only_without_extra_snapshot():
    state=snapshot(extra=0,total=500000)
    del state['invoices'][0]['combo_extra_subtotal']
    assert update(state,tip=600000)['total']==600000


def test_existing_wrong_total_is_corrected_only_by_explicit_audited_update():
    state=snapshot(total=500000)
    original=deepcopy(state)
    invoice=update(state,note='Synthetic explicit correction')
    assert invoice['total']==700000
    assert state['invoice_changes'][-1]['before']['total']==500000
    assert state['invoice_changes'][-1]['reports_before']==original['reports']


def test_combo_discount_is_still_rejected_atomically():
    state=snapshot();before=deepcopy(state)
    with pytest.raises(HTTPException):update(state,discount=10000)
    assert state==before

from copy import deepcopy

import pytest
import vera_live_tour_lists as lists
import vera_live_tour_query as query
from test_live_tour_backend import NOW, state_with
from test_live_tour_invoice_permissions import scoped_client, ALL


INVOICES = [
    dict(id='a', bill_no='VERA-A', effective_at='2026-10-01T12:00:00+07:00',
         entries=[dict(name='Thảo Linh', service='Body', room='6.1'),
                  dict(employee_name='An An', service='Foot', room='6.2')]),
    dict(id='b', bill_no='VERA-B', effective_at='2026-10-01T12:00:00+07:00',
         employee_name='Bình Minh', room='16.1', entries=[dict(service='VIP')]),
    dict(id='c', bill_no='COMBO', effective_at='2026-10-01T12:00:00+07:00',
         customer_name='Thảo Linh', entries=[dict(type='combo_purchase', service='Combo')]),
]


@pytest.mark.parametrize('filters,ids', [
    ({'employee': 'thao li'}, ['a']), ({'employee': 'an an'}, ['a']),
    ({'room': 'Phòng 6.1'}, ['a']), ({'room': '6'}, ['a']),
    ({'employee': 'binh', 'room': 'P.16.1'}, ['b']),
    ({'employee': 'binh', 'room': '6'}, []), ({'employee': 'khong co'}, []),
])
def test_invoice_search_uses_assignment_snapshots_and_room_tokens(filters, ids):
    original = deepcopy(INVOICES)
    assert [r['id'] for r in INVOICES if lists.matches(r, invoice=True, **filters)] == ids
    assert INVOICES == original
    for row in INVOICES:
        entries = query.project('invoices', row)['invoice_entries']
        assert [e['employee'] for e in entries] == [lists.normalize(e['employee_name']) for e in lists.invoice_entries(row)]
        assert [e['room'] for e in entries] == [lists.room_search(e['room']) for e in lists.invoice_entries(row)]


def test_http_filters_before_count_and_pagination_without_mutating_invoices(monkeypatch):
    state = state_with()
    state['invoices'] = deepcopy(INVOICES)
    client, _ = scoped_client(monkeypatch, state, ALL)
    for filters in ({'employee': 'thao li'}, {'room': 'Phòng 6.1'}, {'employee': 'binh', 'room': '16.1'}):
        response = client.get('/v2/live-tour/collections/invoices', params={'preset': 'all', 'page_size': 1, **filters})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['total'] == 1 and result['pages'] == 1
        rows = result['data']['state']['invoices']
        expected = [r for r in INVOICES if lists.matches(r, invoice=True, **filters)]
        assert [r['id'] for r in rows] == [r['id'] for r in expected]
        assert rows[0]['entries'] == expected[0]['entries']


def test_indexed_invoice_predicate_uses_versioned_normalized_assignment_projection():
    params = {}
    sql = query.predicate('invoices', {'employee': 'Thảo Linh', 'room': 'Phòng 6.1'}, params, prefix='x_')
    assert "->'invoice_entries'" in sql
    assert params['x_employee'] == '(^| )thao linh'
    assert params['x_room'] == '(^| )6 1'
    assert query.VERSION == 2

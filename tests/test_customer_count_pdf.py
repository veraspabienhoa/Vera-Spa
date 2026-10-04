from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

import pytest
from pypdf import PdfReader

from vera_customer_count_pdf import customer_counts, customer_count_pdf
from test_live_tour_invoice_permissions import ALL, paid_state, scoped_client


def test_one_invoice_one_visit_sorted_vietnam_dates_zero_days_and_missing_ids():
    rows = [dict(invoice_id='a', effective_at='2026-09-30T18:00:00Z'),
            dict(invoice_id='a', effective_at='2026-09-30T18:00:00Z', service='second'),
            dict(bill_no='b', business_date='2026-10-03'), dict(invoice_id='c'), dict(service='missing')]
    result = customer_counts(rows, date_from='2026-10-01', date_to='2026-10-03')
    assert result['total'] == 3
    assert result['daily'] == [('2026-10-01', 1), ('2026-10-02', 0), ('2026-10-03', 1), ('', 1)]
    assert result['missing_id_rows'] == 1


def test_a4_landscape_unicode_dates_total_empty_and_multi_page():
    rows = [dict(invoice_id=str(i), business_date=(date(2026, 10, 1) + timedelta(days=i)).isoformat()) for i in range(31)]
    summary = customer_counts(rows)
    pdf = customer_count_pdf(summary, {'date_from':'2026-10-01', 'date_to':'2026-10-31', 'employee':'Mạnh Đạt', 'total_amount':0}, generated_at=datetime(2026, 10, 4, tzinfo=timezone.utc))
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == 3
    assert all(abs(float(page.mediabox.width) - 841.89) < 1 and abs(float(page.mediabox.height) - 595.28) < 1 for page in reader.pages)
    text = ''.join(page.extract_text() for page in reader.pages)
    assert 'Mạnh Đạt' in text and '31-10-2026' in text and 'Tổng tiền: 0' in text
    assert 'Trang 3 / 3' in text
    empty = PdfReader(BytesIO(customer_count_pdf(customer_counts([]), {})))
    assert len(empty.pages) == 1 and 'Không có hóa đơn' in empty.pages[0].extract_text()


@pytest.mark.parametrize('removed', ['live_tour_export', 'live_tour_reports_view'])
def test_endpoint_enforces_both_existing_grants(monkeypatch, removed):
    state, _ = paid_state()
    client, shared = scoped_client(monkeypatch, state, ALL - {removed})
    before = deepcopy(shared)
    assert client.get('/v2/live-tour/customer-count.pdf').status_code == 403
    assert shared == before


def test_endpoint_whole_filtered_snapshot_no_writes(monkeypatch):
    import vera_customer_count_pdf as pdf
    state, invoice = paid_state()
    client, shared = scoped_client(monkeypatch, state, ALL)
    captured = []
    def render(summary, filters, **_kwargs):
        captured.append((summary, filters))
        return b'%PDF-1.4\n'
    monkeypatch.setattr(pdf, 'customer_count_pdf', render)
    before = deepcopy(shared)
    response = client.get('/v2/live-tour/customer-count.pdf', params={'bill_no':invoice['bill_no'], 'total_amount':state['reports'][0]['total']})
    assert response.status_code == 200 and response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert captured[-1][0]['total'] == 1
    assert client.get('/v2/live-tour/customer-count.pdf', params={'bill_no':'NONMATCH'}).status_code == 200
    assert captured[-1][0]['total'] == 0
    assert client.get('/v2/live-tour/customer-count.pdf', params={'date':'2026-02-30'}).status_code == 400
    assert client.get('/v2/live-tour/customer-count.pdf', params={'date_from':'2026-10-04','date_to':'2026-10-01'}).status_code == 400
    assert shared == before


def test_customer_filter_does_not_bypass_report_redaction(monkeypatch):
    import vera_customer_count_pdf as pdf
    state, invoice = paid_state()
    invoice['customer_name'] = 'Private customer'
    for row in state['reports']:
        row['customer_name'] = 'Private customer'
    client, _ = scoped_client(monkeypatch, state, ALL - {'live_tour_customers_view', 'live_tour_paid_invoice_view'})
    summaries = []
    monkeypatch.setattr(pdf, 'customer_count_pdf', lambda summary, *_a, **_k: summaries.append(summary) or b'%PDF-1.4')
    assert client.get('/v2/live-tour/customer-count.pdf', params={'customer':'Private customer'}).status_code == 200
    assert summaries[-1]['total'] == 0

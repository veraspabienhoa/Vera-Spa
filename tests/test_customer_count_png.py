from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from PIL import Image, ImageDraw
import pytest

import vera_customer_count_pdf as pdf
import vera_customer_count_png as png
import vera_web_v2_live_tour as live
from test_live_tour_backend import RouteConnection, RouteEngine
from test_live_tour_invoice_permissions import ALL, paid_state, scoped_client


PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def record_drawn_text(monkeypatch):
    recorded = []
    original = ImageDraw.ImageDraw.text

    def text(draw, xy, value, *args, **kwargs):
        recorded.append((str(value), draw.textbbox(xy, value, font=kwargs['font'], anchor=kwargs.get('anchor'))))
        return original(draw, xy, value, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, 'text', text)
    return recorded


def test_real_png_all_chart_and_table_dates_unicode_and_deduplicated_visits(monkeypatch):
    drawn = record_drawn_text(monkeypatch)
    rows = [dict(invoice_id='a', effective_at='2026-09-30T18:00:00Z'),
            dict(invoice_id='a', effective_at='2026-09-30T18:00:00Z', service='Second service'),
            dict(bill_no='b', business_date='2026-10-03'), dict(invoice_id='undated'), dict(service='Missing ID')]
    summary = pdf.customer_counts(rows, date_from='2026-10-01', date_to='2026-10-31')
    filters = {'date_from': '2026-10-01', 'date_to': '2026-10-31', 'employee': 'Mạnh Đạt', 'total_amount': 0}
    before = deepcopy((summary, filters))
    content = png.customer_count_png(summary, filters, generated_at=datetime(2026, 10, 10, 18, tzinfo=timezone.utc))
    assert content.startswith(PNG_SIGNATURE)
    assert (summary, filters) == before
    assert summary['total'] == 3 and summary['daily'][1] == ('2026-10-02', 0)
    with Image.open(BytesIO(content)) as image:
        image.load()
        assert image.format == 'PNG' and image.size == (1600, 3048)
        assert all(0 <= x0 <= x1 <= image.width and 0 <= y0 <= y1 <= image.height
                   for _, (x0, y0, x1, y1) in drawn)
        assert image.getpixel((64, 190)) != image.getpixel((0, 0))
    texts = [value for value, _ in drawn]
    for day in range(1, 32):
        # Each date is actually drawn in both the chart and the complete table.
        assert texts.count(f'{day:02d}-10-2026') == 2
    assert 'Không rõ ngày' in texts and 'Không rõ' in texts
    assert 'Có 1 dòng thiếu mã hóa đơn, không đưa vào số khách.' in texts
    assert 'Nhân viên: Mạnh Đạt | Tổng tiền: 0' in texts
    assert 'Lập lúc 11-10-2026 01:00 | Theo dữ liệu đã thanh toán' in texts
    assert 'Phần 3 / 3' in texts


def test_empty_and_undated_reports_render_without_losing_explanation(monkeypatch):
    drawn = record_drawn_text(monkeypatch)
    content = png.customer_count_png(pdf.customer_counts([]), {})
    with Image.open(BytesIO(content)) as image:
        assert image.size == (1600, 1000)
    assert 'Không có hóa đơn khớp bộ lọc.' in [value for value, _ in drawn]
    drawn.clear()
    png.customer_count_png(pdf.customer_counts([{'invoice_id': 'no-date'}]), {})
    assert 'Không rõ ngày' in [value for value, _ in drawn]
    assert 'Không có hóa đơn khớp bộ lọc.' not in [value for value, _ in drawn]


def test_undated_header_and_full_dates_fit_inside_dense_table_cells(monkeypatch):
    drawn = record_drawn_text(monkeypatch)
    rows = [dict(invoice_id=str(index), business_date=f'2026-10-{index:02d}') for index in range(1, 14)]
    rows.append({'invoice_id': 'undated'})
    png.customer_count_png(pdf.customer_counts(rows), {})
    width = (png.WIDTH - 128 - 196) / 14
    for column, label in enumerate([f'{day:02d}-10-2026' for day in range(1, 14)] + ['Không rõ ngày']):
        _, (x0, _, x1, _) = next((value, bounds) for value, bounds in drawn if value == label and bounds[1] > 773)
        left = 64 + 108 + column * width
        assert x0 >= left + 6 and x1 <= left + width - 6


def test_full_leap_year_is_one_complete_image_including_zero_days(monkeypatch):
    drawn = record_drawn_text(monkeypatch)
    summary = pdf.customer_counts([], date_from='2024-01-01', date_to='2024-12-31')
    content = png.customer_count_png(summary, {'date_from': '2024-01-01', 'date_to': '2024-12-31'})
    with Image.open(BytesIO(content)) as image:
        assert image.size == (1600, 27624)
        assert image.width * image.height <= png.MAX_IMAGE_PIXELS
    texts = [value for value, _ in drawn]
    for index in range(366):
        assert texts.count((date(2024, 1, 1) + timedelta(days=index)).strftime('%d-%m-%Y')) == 2
    assert 'Phần 27 / 27' in texts


def test_complete_long_filter_values_wrap_inside_image(monkeypatch):
    drawn = record_drawn_text(monkeypatch)
    filters = {'date_from': '2026-10-01', 'date_to': '2026-10-01', 'date': '2026-10-01',
               'employee': 'Đ' * 200, 'customer': 'Khách hàng ' * 18,
               'service': 'Dịch vụ ' * 25, 'bill_no': 'X' * 100, 'total_amount': 0}
    content = png.customer_count_png(pdf.customer_counts([], date_from='2026-10-01', date_to='2026-10-01'), filters)
    with Image.open(BytesIO(content)) as image:
        assert image.height > png.SECTION_HEIGHT
        assert all(0 <= x0 <= x1 <= image.width and 0 <= y0 <= y1 <= image.height
                   for _, (x0, y0, x1, y1) in drawn)
    assert 'Đ' * 200 in ''.join(value for value, _ in drawn)
    assert 'X' * 100 in ''.join(value for value, _ in drawn)
    assert any('Ngày: 01-10-2026' in value for value, _ in drawn)


@pytest.mark.parametrize('filters', [
    {'date_from': '2000-01-01', 'date_to': '2026-10-01'},
    {'date_from': '2024-01-01', 'date_to': '2026-10-01'},
])
def test_oversized_ranges_fail_before_image_allocation_never_truncate(monkeypatch, filters):
    def unexpected(*_args, **_kwargs):
        pytest.fail('An oversized report must not allocate a partial image')
    summary = pdf.customer_counts([], **filters)
    monkeypatch.setattr(png.Image, 'new', unexpected)
    with pytest.raises(png.CustomerCountImageTooLarge, match='PNG đầy đủ'):
        png.customer_count_png(summary, filters)


def test_pixel_limit_and_render_slot_are_bounded_and_released(monkeypatch):
    with monkeypatch.context() as context:
        context.setattr(png, 'MAX_IMAGE_PIXELS', 1)
        with pytest.raises(png.CustomerCountImageTooLarge):
            png.customer_count_png(pdf.customer_counts([]), {})
    assert png.RENDER_SLOT.acquire(blocking=False)
    try:
        with pytest.raises(RuntimeError, match='đang tạo ảnh PNG khác'):
            png.customer_count_png(pdf.customer_counts([]), {})
    finally:
        png.RENDER_SLOT.release()
    with monkeypatch.context() as context:
        def no_memory(*_args, **_kwargs):
            raise MemoryError()
        context.setattr(png.Image, 'new', no_memory)
        with pytest.raises(RuntimeError, match='Không thể tạo ảnh PNG đầy đủ'):
            png.customer_count_png(pdf.customer_counts([]), {})
    assert png.customer_count_png(pdf.customer_counts([]), {}).startswith(PNG_SIGNATURE)


@pytest.mark.parametrize('removed', ['live_tour_export', 'live_tour_reports_view'])
def test_png_enforces_both_existing_grants_before_snapshot(monkeypatch, removed):
    state, _ = paid_state()
    client, shared = scoped_client(monkeypatch, state, ALL - {removed})
    before = deepcopy(shared)
    def unexpected(*_args, **_kwargs):
        pytest.fail('Unauthorized PNG export must not read the ledger or render')
    monkeypatch.setattr(live, '_read_state', unexpected)
    monkeypatch.setattr(png, 'customer_count_png', unexpected)
    response = client.get('/v2/live-tour/customer-count.png')
    assert response.status_code == 403 and shared == before


def test_png_endpoint_reads_whole_unpaged_ledger_and_releases_connection_before_render(monkeypatch):
    state, _ = paid_state()
    template = deepcopy(state['reports'][0])
    state['reports'] = [dict(template, invoice_id=f'invoice-{i}', bill_no=f'B-{i}',
                             effective_at='2026-10-01T10:00:00+07:00') for i in range(1201)]
    state['reports'].append(deepcopy(state['reports'][0]))
    client, shared = scoped_client(monkeypatch, state, ALL)
    before = deepcopy((state, shared))
    reads, captured, active = [], [], []

    @contextmanager
    def begin(_engine):
        assert not active, 'No nested connection acquisition'
        active.append(True)
        try:
            yield RouteConnection()
        finally:
            active.pop()

    def read(_conn, *, collections):
        assert active
        reads.append(set(collections))
        return deepcopy(state), 1, None

    def render(summary, filters, **kwargs):
        assert not active, 'Rendering must never hold a DB transaction'
        captured.append((summary, filters))
        return PNG_SIGNATURE

    def unexpected(*_args, **_kwargs):
        pytest.fail('PNG export must not write or take the board lock')

    monkeypatch.setattr(RouteEngine, 'begin', begin)
    monkeypatch.setattr(live.resource_store, 'enabled', lambda: True)
    monkeypatch.setattr(live.resource_store, 'read', read)
    monkeypatch.setattr(live, '_write_state', unexpected)
    monkeypatch.setattr(live, 'acquire_state_lock', unexpected)
    monkeypatch.setattr(png, 'customer_count_png', render)
    response = client.get('/v2/live-tour/customer-count.png', params={'page': 2, 'page_size': 5})
    assert response.status_code == 200 and response.content.startswith(PNG_SIGNATURE)
    assert response.headers['content-type'] == 'image/png'
    assert response.headers['content-disposition'] == 'attachment; filename=VERA_SoLuongKhach.png'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert captured[0][0]['total'] == 1201
    assert captured[0][0]['daily'] == [('2026-10-01', 1201)]
    assert reads == [{'reports', 'invoices'}]
    assert (state, shared) == before


@pytest.mark.parametrize('visible_grant', [None, 'live_tour_invoice_view', 'live_tour_paid_invoice_view', 'live_tour_customers_view'])
def test_customer_name_phone_filter_respects_report_redaction(monkeypatch, visible_grant):
    state, _ = paid_state()
    for row in state['reports']:
        row.update(customer_name='Private customer', customer_phone='0901234567')
    grants = ALL - {'live_tour_customers_view', 'live_tour_paid_invoice_view', 'live_tour_invoice_view'}
    if visible_grant:
        grants.add(visible_grant)
    client, shared = scoped_client(monkeypatch, state, grants)
    before, captured = deepcopy(shared), []
    monkeypatch.setattr(png, 'customer_count_png', lambda summary, *_a, **_k: captured.append(summary) or PNG_SIGNATURE)
    for query in ('Private customer', '0901234567'):
        assert client.get('/v2/live-tour/customer-count.png', params={'customer': query}).status_code == 200
        assert captured[-1]['total'] == (1 if visible_grant else 0)
    assert shared == before


def test_png_and_pdf_share_all_filter_semantics_without_mutating_financial_data(monkeypatch):
    state, _ = paid_state()
    template = dict(state['reports'][0], effective_at='2026-09-30T18:00:00Z', business_date='2026-09-30',
                    employee_name='Mạnh Đạt', customer_name='Nguyễn An', customer_phone='0901234567',
                    service='Body 90', invoice_id='same', bill_no='TEST-1', total=0)
    state['reports'] = [template, deepcopy(template), dict(template, invoice_id='other', total=10),
                        dict(template, invoice_id='later', effective_at='2026-10-02T10:00:00+07:00')]
    client, shared = scoped_client(monkeypatch, state, ALL)
    before, captured = deepcopy(shared), []
    def render(summary, filters, **kwargs):
        captured.append(deepcopy((summary, filters)))
        return PNG_SIGNATURE
    monkeypatch.setattr(png, 'customer_count_png', render)
    monkeypatch.setattr(pdf, 'customer_count_pdf', render)
    filters = {'date_from': '2026-10-01', 'date_to': '2026-10-03', 'date': '2026-10-01',
               'employee': 'Manh', 'customer': 'Nguyen An 0901234567', 'service': 'Body', 'bill_no': 'TEST', 'total_amount': 0}
    for suffix in ('png', 'pdf'):
        assert client.get(f'/v2/live-tour/customer-count.{suffix}', params=filters).status_code == 200
    assert captured[0] == captured[1]
    assert captured[0][0]['total'] == 1 and captured[0][0]['daily'] == [('2026-10-01', 1)]
    assert captured[0][1]['date_from'] == captured[0][1]['date_to'] == '2026-10-01'
    assert captured[0][1]['total_amount'] == 0
    assert shared == before


@pytest.mark.parametrize('params,status', [({'date': '2026-02-30'}, 400),
                                         ({'date_from': '2026-10-04', 'date_to': '2026-10-01'}, 400),
                                         ({'total_amount': -1}, 422), ({'employee': 'x' * 201}, 422)])
def test_png_validates_existing_filter_bounds(monkeypatch, params, status):
    client, shared = scoped_client(monkeypatch, paid_state()[0], ALL)
    before = deepcopy(shared)
    assert client.get('/v2/live-tour/customer-count.png', params=params).status_code == status
    assert shared == before


def test_png_endpoint_real_bytes_and_graceful_render_failures(monkeypatch):
    client, shared = scoped_client(monkeypatch, paid_state()[0], ALL)
    before = deepcopy(shared)
    response = client.get('/v2/live-tour/customer-count.png')
    assert response.status_code == 200 and response.content.startswith(PNG_SIGNATURE)
    with Image.open(BytesIO(response.content)) as image:
        image.verify()
    response = client.get('/v2/live-tour/customer-count.png', params={'date_from': '2000-01-01', 'date_to': '2026-10-01'})
    assert response.status_code == 413 and 'PNG đầy đủ' in response.json()['detail']
    def unavailable(*_args, **_kwargs):
        raise RuntimeError('PNG renderer unavailable')
    monkeypatch.setattr(png, 'customer_count_png', unavailable)
    response = client.get('/v2/live-tour/customer-count.png')
    assert response.status_code == 503 and response.json()['detail'] == 'PNG renderer unavailable'
    assert shared == before

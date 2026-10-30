from io import BytesIO
import pytest
from pydantic import ValidationError
from PIL import Image
from vera_invoice_export import InvoiceExportRequest, invoice_rows, render_invoice_export

INVOICE = {'id':'i1','bill_no':'VERA-1','customer_name':'Linh Đan <test>', 'subtotal':250000,'discount':50000,'tip':100000,'total':300000,'entries':[{'service':'90 phút · Tiêu chuẩn'}]}

@pytest.mark.parametrize('service,tip,total',[(True,True,'300.000 đ'),(True,False,'200.000 đ'),(False,True,'100.000 đ')])
def test_selected_components(service,tip,total):
    headers,rows=invoice_rows([INVOICE,INVOICE],service,tip,lambda _: '25-10-2026 10:00')
    assert rows[0][0]=='1' and rows[1][0]=='2'
    assert rows[-1][-1] == {'300.000 đ':'600.000 đ','200.000 đ':'400.000 đ','100.000 đ':'200.000 đ'}[total]
    assert rows[0][-1]==total
    assert any(row[1]=='Tiền tip' for row in rows)==tip
    assert ('Dịch vụ' in headers)==service
    if not service: assert 'Tiêu chuẩn' not in str(rows)


def test_prepaid_combo_not_charged_again():
    inv={**INVOICE,'payment_method':'COMBO','combo_extra_subtotal':20000,'discount':0,'total':120000}
    headers,rows=invoice_rows([inv],True,False,lambda _: '')
    assert not any(row[1] in ('Tiền dịch vụ', 'Giảm giá') for row in rows)
    assert rows[0][-1]=='20.000 đ'

@pytest.mark.parametrize('body',[{'ids':[]},{'ids':['a','a']},{'ids':['a'],'service':False,'tip':False},{'ids':[str(i) for i in range(51)]}])
def test_invalid_export(body):
    with pytest.raises(ValidationError): InvoiceExportRequest(**body)


def test_pdf_and_png_render_vietnamese_rows():
    headers,rows=invoice_rows([INVOICE],True,True,lambda _: '25-10-2026')
    pdf=render_invoice_export(headers,rows,'pdf')
    assert pdf.startswith(b'%PDF')
    png=render_invoice_export(headers,rows,'png')
    image=Image.open(BytesIO(png))
    assert image.width==1600 and image.height>100

@pytest.mark.parametrize('role',['nhanvien','leader','locker','giamdoc'])
def test_http_export_rejects_other_roles(monkeypatch,role):
    from test_live_tour_appointments import appointment_client
    client,_=appointment_client(monkeypatch,role)
    response=client.post('/v2/live-tour/invoice-export/pdf',json={'ids':['i1']})
    assert response.status_code==403

@pytest.mark.parametrize('role',['admin','quanly','letan'])
def test_http_export_selected_ids_and_rejects_missing(monkeypatch,role):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import vera_web_v2_live_tour as live
    from test_live_tour_backend import RouteEngine
    from test_live_tour_appointments import AppointmentIdentity
    monkeypatch.setattr(live.resource_store,'enabled',lambda:True)
    monkeypatch.setattr(live.resource_store,'read',lambda *a,**k: ({'invoices':[INVOICE]},1,{}))
    app=FastAPI()
    live.install_live_tour_routes(app,engine_instance=RouteEngine,current_identity=lambda:AppointmentIdentity(role=role),require_feature=lambda *a:None,feature_allowed=lambda *a:True,identity_type=AppointmentIdentity)
    client=TestClient(app)
    response=client.post('/v2/live-tour/invoice-export/pdf',json={'ids':['i1'],'preset':'all'})
    assert response.status_code==200
    assert response.content.startswith(b'%PDF')
    assert client.post('/v2/live-tour/invoice-export/pdf',json={'ids':['missing'],'preset':'all'}).status_code==409
    # A row outside the granted/requested day is never exported.
    assert client.post('/v2/live-tour/invoice-export/pdf',json={'ids':['i1'],'preset':'today'}).status_code==409


def test_combined_receipt_omits_private_staff_and_room():
    inv = {**INVOICE, 'employee_name':'PRIVATE STAFF', 'room':'PRIVATE ROOM', 'entries':[{'service':'VIP','employee_name':'PRIVATE STAFF','room':'PRIVATE ROOM'}]}
    headers,rows = invoice_rows([inv,inv],True,True,lambda _: '')
    assert [r[0] for r in rows if r[0]] == ['1','2']
    assert rows[-1] == ['', 'Tổng tiền', '600.000 đ']
    assert 'PRIVATE' not in str(rows)


def test_invoice_date_label_uses_vietnam_calendar_and_selected_date_range():
    from vera_invoice_export import invoice_date_label
    assert invoice_date_label([{'effective_at':'2026-10-28T18:00:00Z'}]) == 'Ngày 29-10-2026'
    assert invoice_date_label([{'business_date':'2026-10-29'}, {'business_date':'2026-10-30'}]) == 'Ngày 29-10-2026 – 30-10-2026'
    assert invoice_date_label([{'created_at':'2026-10-30T00:00:00Z'}]) == 'Ngày —'


def test_receipt_pdf_header_spacing_and_signature_alignment():
    pdfplumber = pytest.importorskip('pdfplumber')
    headers, rows = invoice_rows([INVOICE], True, True, lambda _: '')
    content = render_invoice_export(headers, rows, 'pdf', date_label='Ngày 29-10-2026')
    with pdfplumber.open(BytesIO(content)) as pdf:
        page = pdf.pages[0]
        lines = page.extract_text_lines()
        find = lambda text: next(line for line in lines if line['text'] == text)
        address = find('193 Trương Định, Tam Hiệp, Đồng Nai')
        title = find('HÓA ĐƠN DỊCH VỤ')
        day = find('Ngày 29-10-2026')
        signature = find('Vera Spa')
        hint = find('Ký ghi rõ họ tên')
        assert title['top'] - address['bottom'] >= 12
        assert day['top'] > title['bottom']
        money_header = next(line for line in page.crop((page.width*.6, 0, page.width, page.height)).extract_text_lines() if line['text'] == 'Thành tiền')
        center = lambda line: (line['x0'] + line['x1']) / 2
        assert center(signature) == pytest.approx(center(money_header), abs=1)
        assert center(hint) == pytest.approx(center(money_header), abs=1)
        assert hint['top'] > signature['bottom']
        chars = [char for char in page.chars if hint['top'] <= char['top'] <= hint['bottom']]
        assert chars and all('Oblique' in char['fontname'] and 'Bold' not in char['fontname'] for char in chars)


def test_png_table_header_has_distinct_background():
    headers, rows = invoice_rows([INVOICE], True, True, lambda _: '')
    image = Image.open(BytesIO(render_invoice_export(headers, rows, 'png', date_label='Ngày 29-10-2026')))
    vertical_margin = round(.75 * (1600 / (210 / 25.4)))
    assert image.getpixel((150, vertical_margin + 220)) == (200, 220, 209)

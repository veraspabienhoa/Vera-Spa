from io import BytesIO
import pytest
from pydantic import ValidationError
from PIL import Image
from vera_invoice_export import InvoiceExportRequest, invoice_rows, render_invoice_export

INVOICE = {'id':'i1','bill_no':'VERA-1','customer_name':'Linh Đan <test>', 'subtotal':250000,'discount':50000,'tip':100000,'total':300000,'entries':[{'service':'90 phút · Tiêu chuẩn'}]}

@pytest.mark.parametrize('service,tip,total',[(True,True,'300.000 đ'),(True,False,'200.000 đ'),(False,True,'100.000 đ')])
def test_selected_components(service,tip,total):
    headers,rows=invoice_rows([INVOICE,INVOICE],service,tip,lambda _: '25-10-2026 10:00')
    assert len(rows)==2
    assert rows[0][-1]==total
    assert ('Tiền tip' in headers)==tip
    assert ('Dịch vụ' in headers)==service
    if not service: assert 'Tiêu chuẩn' not in str(rows)


def test_prepaid_combo_not_charged_again():
    inv={**INVOICE,'payment_method':'COMBO','combo_extra_subtotal':20000,'discount':0,'total':120000}
    headers,rows=invoice_rows([inv],True,False,lambda _: '')
    assert rows[0][headers.index('Tiền dịch vụ')]=='20.000 đ'
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

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from contextlib import contextmanager
import zipfile
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import vera_purchase_store as store
from vera_web_v2_purchases import install_purchase_routes, PurchaseRow, PurchaseEdit, row_values


def workbook(monkeypatch, rows):
    """Synthetic XLSB reader records: no business workbook in the repository."""
    class Sheet:
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def rows(self):
            for i,row in enumerate([['title'],['Ngày nhập','Chi tiết hàng hóa','Số lượng','Đơn giá','Thành Tiền']]+rows):
                yield [SimpleNamespace(v=value,r=i) for value in row]
    class Book(Sheet):
        def get_sheet(self,name):
            assert name=='Input'
            return Sheet()
    monkeypatch.setattr('pyxlsb.open_workbook',lambda _:Book())
    output=BytesIO()
    with zipfile.ZipFile(output,'w') as z: z.writestr('xl/workbook.bin',b'fixture')
    return output.getvalue()


def test_import_preserves_history_amount_missing_metadata_and_duplicate_rows(monkeypatch):
    source=[46287,'Hàng thử','2,5%',10000,777,'Ghi chú',None,None,None]
    rows=store.parse_workbook(workbook(monkeypatch,[source,source]))
    assert len(rows)==2
    assert rows[0]['quantity']=='2,5%'
    assert rows[0]['amount']==777
    assert rows[0]['entered_at'] is None
    assert rows[0]['entered_by']==''
    assert rows[0]['source_key']!=rows[1]['source_key']
    assert rows==store.parse_workbook(workbook(monkeypatch,[source,source]))


def test_import_vietnam_timestamp(monkeypatch):
    row=store.parse_workbook(workbook(monkeypatch,[[46287,'Hàng',1,100,100,'',46287,.5,'NV']]))[0]
    assert row['entered_at'].isoformat()=='2026-09-22T12:00:00+07:00'


@pytest.mark.parametrize('value',['NaN','Infinity','abc','1e20'])
def test_invalid_money_rejected(value):
    with pytest.raises(ValueError): store.decimal_value(value)


def test_bad_source_row_fails_instead_of_silent_skip(monkeypatch):
    with pytest.raises(ValueError,match='Dòng 3'):
        store.parse_workbook(workbook(monkeypatch,[[None,'Hàng',1,100,100]]))


def test_batch_calculates_decimal_amount():
    row=PurchaseRow(purchase_date='2026-09-23',item=' Hàng ',quantity='3.5',unit_price='28000')
    assert row_values(row)['amount']==Decimal('98000.00')
    assert row_values(row)['item']=='Hàng'


def test_historical_edit_keeps_authoritative_total():
    row=PurchaseEdit(purchase_date='2026-09-23',item='Hàng',quantity='2,5%',unit_price='10000',amount='777',revision=0)
    assert row_values(row)['amount']==777


def test_permission_vietnam_day_and_admin_override():
    row=dict(deleted=False,revision=2,entered_at=datetime(2026,9,22,17,tzinfo=timezone.utc))
    store.require_editable(row,'letan',2,date(2026,9,23))
    with pytest.raises(PermissionError): store.require_editable(row,'letan',2,date(2026,9,22))
    store.require_editable(row,'admin',2,date(2026,9,24))
    row['entered_at']=None
    with pytest.raises(PermissionError): store.require_editable(row,'letan',2,date(2026,9,23))
    store.require_editable(row,'admin',2,date(2026,9,23))


def test_stale_revision_and_deleted_rows_rejected():
    row=dict(deleted=False,revision=2,entered_at=None)
    with pytest.raises(ValueError): store.require_editable(row,'admin',1)
    row['deleted']=True
    with pytest.raises(KeyError): store.require_editable(row,'admin',2)


@pytest.mark.parametrize('method,path,payload',[
    ('get','/v2/purchases',None),
    ('post','/v2/purchases',{'request_id':'c8ca9b91-8b28-4ffb-91b3-a9a4487124e7','rows':[{'purchase_date':'2026-09-23','item':'Hàng','quantity':1,'unit_price':100}]}),
    ('patch','/v2/purchases/1',{'purchase_date':'2026-09-23','item':'Hàng','quantity':'1','unit_price':100,'amount':100,'revision':0}),
    ('delete','/v2/purchases/1?revision=0',None),
    ('get','/v2/purchases/export.xlsx',None),
    ('get','/v2/purchases/audit',None),
    ('post','/v2/purchases/import?request_id=c8ca9b91-8b28-4ffb-91b3-a9a4487124e7',None),
])
def test_api_enforces_permissions_before_data_access(method,path,payload):
    class Engine:
        @contextmanager
        def begin(self): yield object()
    def deny(*_): raise HTTPException(403,'denied')
    app=FastAPI()
    install_purchase_routes(app,engine_instance=Engine,current_identity=lambda:SimpleNamespace(role='nhanvien',employee_username='test'),
                            require_feature=deny,feature_allowed=lambda *_:False)
    with TestClient(app) as client:
        response=client.request(method,path,**({'json':payload} if payload else {}))
        assert response.status_code==403

from io import BytesIO
from types import SimpleNamespace
from contextlib import contextmanager
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from openpyxl import Workbook
import vera_web_v2_attendance_codes as codes

EMPLOYEES = [dict(username='test-a', full_name='Test Alpha', phone='0901000001'), dict(username='test-b', full_name='Test Beta', phone='0901000002')]

def workbook():
    wb = Workbook()
    ws = wb.active
    ws.append(['Tên nhân viên', 'Số điện thoại', 'Mã chấm công', 'Mã nhân viên'])
    ws.append(['Test Alpha', '0901000001', 123, 'EMP001'])
    ws.cell(2,3).number_format = '00000'
    stream = BytesIO(); wb.save(stream); wb.close()
    return stream.getvalue()


def test_excel_codes_are_text_and_employee_code_is_never_a_facegate_id():
    rows = codes.workbook_codes(workbook())
    assert rows[0]['attendance_code'] == '00123'
    assert rows[0]['employee_code'] == 'EMP001'
    result = codes.match_codes(EMPLOYEES, rows + rows)
    assert result['matched_count'] == 1 and result['record_count'] == 1
    assert result['employees'][1]['status'] == 'missing'
    assert 'profile_id' not in str(result)
    with pytest.raises(HTTPException):
        codes.workbook_codes(b'not-an-xlsx')


def test_conflicting_names_phones_codes_are_not_automatically_selected():
    def row(name, number, code):
        return dict(name=name, phone=number, attendance_code=code)
    mismatch = codes.match_codes(EMPLOYEES, [row('Test Alpha','0901000002','123')])
    assert mismatch['matched_count'] == 0 and mismatch['unmatched'][0]['status'] == 'ambiguous'
    duplicate = codes.match_codes(EMPLOYEES, [row('Test Alpha','','123'), row('Test Beta','','123')])
    assert duplicate['matched_count'] == 0
    assert all(r['status'] == 'conflict' for r in duplicate['employees'])
    multi = codes.match_codes(EMPLOYEES, [row('Test Alpha','','123'), row('Test Alpha','','456')])
    assert multi['employees'][0]['status'] == 'conflict'
    unknown = codes.match_codes(EMPLOYEES, [row('Test Alpha','','123'), row('Someone else','','123')])
    assert unknown['matched_count'] == 0


def test_preview_and_catalogue_are_read_only_and_require_mapping_permission(monkeypatch):
    class Engine:
        @contextmanager
        def connect(self):
            yield self
        def execute(self, *args):
            raise AssertionError('No direct writes or attendance projection')
    ident = SimpleNamespace(role='admin')
    app = FastAPI()
    monkeypatch.setattr(codes,'read_employees',lambda conn: EMPLOYEES)
    monkeypatch.setattr(codes,'saved_codes',lambda conn: codes.workbook_codes(workbook()))
    codes.install_attendance_code_routes(app,engine_instance=Engine,current_identity=lambda: ident,identity_type=SimpleNamespace,
        require_feature=lambda conn, who, feature: None if who.role == 'admin' else (_ for _ in ()).throw(HTTPException(403)))
    api = TestClient(app)
    assert api.get('/v2/devices/attendance-codes').json()['matched_count'] == 1
    assert api.post('/v2/devices/attendance-codes/preview',content=workbook()).json()['matched_count'] == 1
    ident.role = 'letan'
    assert api.get('/v2/devices/attendance-codes').status_code == 403
    assert api.post('/v2/devices/attendance-codes/preview',content=workbook()).status_code == 403

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


@pytest.mark.parametrize('declared_dimension', ['A1:D2', 'A1:A1', 'A1:XFD1048576'])
def test_timesoft_incorrect_dimension_does_not_hide_rows_or_columns(declared_dimension):
    import re
    from zipfile import ZipFile, ZIP_DEFLATED
    wb = Workbook()
    ws = wb.active
    ws.append(['Tên nhân viên', 'Số điện thoại', 'Mã chấm công', 'Mã nhân viên'])
    ws.append(['Test Alpha', '0901000001', '00123', 'EMP001'])
    ws.append(['Test Beta', '0901000002', '00456', 'EMP002'])
    original = BytesIO(); wb.save(original); wb.close()
    malformed = BytesIO()
    with ZipFile(BytesIO(original.getvalue())) as source, ZipFile(malformed, 'w', ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                data = re.sub(rb'<dimension ref="[^"]+"', f'<dimension ref="{declared_dimension}"'.encode(), data, count=1)
            target.writestr(item, data)
    rows = codes.workbook_codes(malformed.getvalue())
    assert [row['attendance_code'] for row in rows] == ['00123', '00456']
    assert codes.match_codes(EMPLOYEES, rows)['matched_count'] == 2


def test_actual_row_limit_still_applies_when_dimension_is_ignored(monkeypatch):
    monkeypatch.setattr(codes, 'MAX_ROWS', 1)
    with pytest.raises(HTTPException) as error:
        codes.workbook_codes(workbook())
    assert error.value.status_code == 413


def test_actual_column_limit_still_applies_when_dimension_is_ignored():
    wb = Workbook()
    wb.active.cell(1,257,'too wide')
    stream = BytesIO(); wb.save(stream); wb.close()
    with pytest.raises(HTTPException) as error:
        codes.workbook_codes(stream.getvalue())
    assert error.value.status_code == 413

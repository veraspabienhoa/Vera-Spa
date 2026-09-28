from contextlib import contextmanager
from datetime import date, datetime, timezone
from inspect import getclosurevars, signature
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pytest

import vera_web_v2_staff as staff
import vera_leave_quota_alerts as quota
from vera_web_v2_excel_export_style import style_workbook_bytes


@pytest.fixture
def staff_app():
    app = FastAPI()
    dependencies = {name: (lambda *args, **kwargs: None)
                    for name in signature(staff.install_staff_routes).parameters if name != 'app'}
    dependencies.update(identity_type=object, current_identity=lambda:SimpleNamespace(role='admin'), vn_tz=ZoneInfo('Asia/Ho_Chi_Minh'), leave_sheet_id='', norm=staff.shift_key)
    staff.install_staff_routes(app, **dependencies)
    return app


@pytest.fixture
def workbook_builder(staff_app):
    app = staff_app
    route = next(r for r in app.routes if r.path == '/v2/staff/export.xlsx')
    return getclosurevars(route.endpoint).nonlocals['build_staff_workbook']


def test_export_reads_directory_once_and_never_fetches_identity_images(staff_app):
    endpoint = next(r.endpoint for r in staff_app.routes if r.path == '/v2/staff/export.xlsx')
    cells = dict(zip(endpoint.__code__.co_freevars, endpoint.__closure__))
    calls = []
    class Connection:
        def execute(self, *args, **kwargs):
            raise AssertionError('Export must not query identity documents')
    class Engine:
        @contextmanager
        def connect(self):
            yield Connection()
    row = staff._public_employee({'username':'Test','role':'nhanvien'}, 'Đang làm việc')
    def directory(conn, ident):
        calls.append('directory')
        return {'employees':[row], 'shifts_by_department':{}}
    cells['engine_instance'].cell_contents = Engine
    cells['staff_result'].cell_contents = directory
    response = TestClient(staff_app).get('/v2/staff/export.xlsx')
    assert response.status_code == 200, response.text
    assert calls == ['directory']
    with ZipFile(BytesIO(response.content)) as archive:
        assert not any(path.startswith('xl/media/') for path in archive.namelist())


def test_export_contains_only_employee_data_after_style_middleware(workbook_builder):
    employee = staff._public_employee({'username': 'Test', 'role': 'nhanvien', 'phone': '0123456789'}, 'Đang làm việc')
    payload = workbook_builder([employee], {})
    styled = style_workbook_bytes(payload)
    workbook = load_workbook(BytesIO(styled))
    ws = workbook['DanhSachNhanSu']
    assert not ws._images
    assert 'Ảnh nhân viên' not in [cell.value for cell in ws[1]]
    assert ws['A2'].value == 1
    assert ws['B2'].value == 'Test'
    assert ws.cell(2, staff.STAFF_EXPORT_COLUMNS.index('Điện thoại') + 1).value == '0123456789'
    with ZipFile(BytesIO(styled)) as archive:
        media = [p for p in archive.namelist() if p.startswith('xl/media/')]
        assert not media
        assert not any('/drawings/' in path for path in archive.namelist())


def test_staff_export_retains_text_and_dates_without_portrait_column(workbook_builder):
    employee = staff._public_employee({'username': 'Test', 'role': 'nhanvien'}, 'Đang làm việc')
    payload = workbook_builder([employee], {})
    workbook = load_workbook(BytesIO(payload))
    sheet = workbook['DanhSachNhanSu']
    assert sheet['A2'].value == 1
    assert sheet['B2'].value == 'Test'
    assert sheet.row_dimensions[2].height == 22
    assert sheet.cell(2, staff.STAFF_EXPORT_COLUMNS.index('Ngày sinh') + 1).number_format == 'dd-mm-yyyy'


def leave(day, reason, days=0):
    return dict(employee_name='Test', leave_date=date.fromisoformat(day), leave_reason=reason,
                leave_type='Phát sinh' if 'PHÁT SINH' in reason else 'Có phép', calculated_days=days)


def test_quota_includes_older_zero_day_and_excluded_months():
    rows = [leave('2026-07-01', 'Quay video'), leave('2026-08-01', 'Nghỉ PHÉP NĂM', 1),
            leave('2026-09-01', 'Nghỉ CÓ phép', 6)]
    items = quota.summarize(rows)
    assert [(i['month'], i['days'], i['exceeded']) for i in items] == [('2026-09', 6, ['days'])]


def test_quota_reports_older_generated_month_even_without_ordinary_leave():
    rows = [leave('2026-08-01', 'Đi trễ PHÁT SINH') for _ in range(3)]
    rows += [leave('2026-09-01', 'Quay video')]
    items = quota.summarize(rows)
    assert len(items) == 1
    assert items[0]['month'] == '2026-08'
    assert items[0]['generated'] == 3
    assert items[0]['exceeded'] == ['generated']


def test_quota_endpoint_selected_month_handles_older_excluded_history():
    rows = [leave('2026-08-01', 'Quay video'), leave('2026-09-01', 'Nghỉ CÓ phép', 6)]
    class Connection:
        def execute(self, sql, params):
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    class Engine:
        @contextmanager
        def connect(self):
            yield Connection()
    app = FastAPI()
    quota.install(app, engine_instance=Engine, current_identity=lambda: SimpleNamespace(role='admin'), identity_type=object)
    response = TestClient(app).get('/v2/leave/quota-check?start=2026-09-25&end=2026-09-25')
    assert response.status_code == 200
    assert response.json()['items'][0]['month'] == '2026-09'
    assert response.json()['items'][0]['days'] == 6


def test_optional_portrait_export_has_exact_3_by_4_cm_after_global_styling(workbook_builder):
    from test_face_id_photos import png
    from vera_staff_photo_export import with_portraits
    rows = [staff._public_employee({'username': name, 'role':'nhanvien'}, 'Đang làm việc') for name in ('Test','No photo','Broken')]
    original = png(120,80)
    output = with_portraits(workbook_builder(rows, {}), rows, {'Test':original,'Broken':b'invalid'})
    sheet = load_workbook(BytesIO(style_workbook_bytes(output)))['DanhSachNhanSu']
    assert len(sheet._images) == 1
    anchor = sheet._images[0].anchor
    assert (anchor.ext.cx,anchor.ext.cy) == (1080000,1440000)
    assert anchor._from.row == 1
    assert sheet.row_dimensions[2].height >= 4 / 2.54 * 72
    assert sheet.cell(1,sheet.max_column).value == 'Ảnh nhân viên (3 × 4 cm)'
    assert sheet.cell(4,sheet.max_column).value == 'Ảnh không đọc được'


def test_photo_export_rejects_non_admin_before_database(staff_app):
    dependency = next(r for r in staff_app.routes if r.path == '/v2/staff/export.xlsx').dependant.dependencies[0].call
    staff_app.dependency_overrides[dependency] = lambda: SimpleNamespace(role='quanly')
    result = TestClient(staff_app).get('/v2/staff/export.xlsx?include_photos=true')
    assert result.status_code == 403


@pytest.mark.parametrize('include_photos', [False, True])
@pytest.mark.parametrize('count', [0, 3])
def test_export_all_headers_sequence_and_shift_column_survive_styling(workbook_builder, include_photos, count):
    from vera_staff_photo_export import with_portraits
    rows = [staff._public_employee({'username': name, 'role': 'nhanvien'}, 'Đang làm việc')
            for name in ('Bình', 'An', 'Chi')[:count]]
    for row in rows:
        row['current_week_shift'] = 'Ca 2'
        row['work_shift'] = 'Ca 1'
    data = workbook_builder(rows, {})
    if include_photos:
        data = with_portraits(data, rows, {})
    sheet = load_workbook(BytesIO(style_workbook_bytes(data)))['DanhSachNhanSu']
    headers = [cell.value for cell in sheet[1]]
    assert all(isinstance(label, str) and label.strip() for label in headers)
    assert headers[:2] == ['STT', 'Tên nhân viên']
    assert headers[23:29] == ['Phép năm', 'Ca làm việc', 'Ngày bắt đầu ca',
                              'Chu kỳ', 'Ca tuần hiện tại', 'Khóa đăng nhập']
    assert len(set(headers)) == len(headers)
    assert sheet.freeze_panes == 'A2'
    for column in (1, 10, *range(18, 25), 28, 29):
        assert sheet.cell(2, column).alignment.horizontal == 'center'
    assert sheet.auto_filter.ref.startswith('A1:AD' if include_photos else 'A1:AC')
    for number, row in enumerate(rows, start=1):
        assert sheet.cell(number + 1, 1).value == number
        assert sheet.cell(number + 1, 2).value == row['username']
        assert sheet.cell(number + 1, 25).value == 'Ca 1'
        assert sheet.cell(number + 1, 28).value == 'Ca 2'
    validations = {validation.formula1: str(validation.sqref)
                   for validation in sheet.data_validations.dataValidation}
    assert validations['=DanhMuc!$C$1:$C$2'].startswith('AA2')
    assert validations['=DanhMuc!$D$1:$D$2'].startswith('AC2')


@pytest.mark.parametrize('utc_day,cycle,start,assigned,expected', [
    ('2026-09-21T16:00:00', 'Theo chu kỳ Tuần', '15/09/2026', 'Ca 1', 'Ca 1'),
    ('2026-09-21T18:00:00', 'Theo chu kỳ Tuần', '15/09/2026', 'Ca 1', 'Ca 2'),
    ('2026-09-28T18:00:00', 'Theo chu kỳ Tuần', '15/09/2026', 'Sáng', 'Ca 1'),
    ('2026-09-21T18:00:00', 'Cố định (Không đổi)', '15/09/2026', 'Ca 1', 'Ca 1'),
    ('2026-09-21T18:00:00', 'Theo chu kỳ Tuần', '23/09/2026', 'Ca 1', ''),
    ('2026-09-21T18:00:00', 'Theo chu kỳ Tuần', '15/09/2026', '', ''),
])
def test_export_shift_uses_existing_vera_definitions_and_vietnam_day(
        staff_app, monkeypatch, utc_day, cycle, start, assigned, expected):
    instant = datetime.fromisoformat(utc_day).replace(tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    monkeypatch.setattr(staff, 'datetime', Clock)
    row = dict(username='An', full_name='An', role='nhanvien', work_shift=assigned,
               shift_start_date=start, rotation_cycle=cycle)
    monkeypatch.setattr(staff, '_select_staff_rows', lambda conn: [row])
    monkeypatch.setattr(staff, '_shift_catalog', lambda *args: {})
    monkeypatch.setattr(staff, '_cycle_options', lambda *args: [])
    endpoint = next(r.endpoint for r in staff_app.routes if r.path == '/v2/staff/export.xlsx')
    cells = dict(zip(endpoint.__code__.co_freevars, endpoint.__closure__))
    result_fn = cells['staff_result'].cell_contents
    inner = dict(zip(result_fn.__code__.co_freevars, result_fn.__closure__))
    inner['permissions'].cell_contents = lambda *args: {}
    inner['allowed_roles'].cell_contents = lambda *args: []
    calls = []
    class Connection:
        def execute(self, sql, *args):
            calls.append(str(sql))
            assert 'shift_definitions' in str(sql)
            return SimpleNamespace(scalar_one_or_none=lambda: [{'Tên ca': 'Sáng', 'Ca chính': 'Ca 1'}])
    result = result_fn(Connection(), SimpleNamespace(role='admin'))
    assert len(calls) == 1
    assert result['employees'][0]['current_week_shift'] == expected
    payload = cells['build_staff_workbook'].cell_contents(result['employees'], {})
    sheet = load_workbook(BytesIO(style_workbook_bytes(payload)))['DanhSachNhanSu']
    assert (sheet['AB2'].value or '') == expected


def test_new_display_columns_are_ignored_on_reimport(staff_app, workbook_builder):
    employee = staff._public_employee({'username': 'An', 'role': 'nhanvien', 'work_shift': 'Ca 1'}, 'Đang làm việc')
    employee['current_week_shift'] = 'Ca 2'
    endpoint = next(r.endpoint for r in staff_app.routes if r.path == '/v2/staff/import.xlsx')
    helpers = getclosurevars(endpoint).nonlocals
    imported = helpers['parse_import'](workbook_builder([employee], {}))[0]
    baseline = helpers['import_values'](imported)
    imported.update({'STT': 999, 'Ca tuần hiện tại': 'Ca không hợp lệ'})
    assert helpers['import_values'](imported) == baseline
    assert baseline['work_shift'] == 'Ca 1'
    assert 'current_week_shift' not in baseline


@pytest.mark.parametrize('include_photos', [False, True])
def test_export_excludes_director_before_numbering_and_photo_read(staff_app, monkeypatch, include_photos):
    import vera_staff_photo_export as photos
    endpoint = next(r.endpoint for r in staff_app.routes if r.path == '/v2/staff/export.xlsx')
    cells = dict(zip(endpoint.__code__.co_freevars, endpoint.__closure__))
    rows = [staff._public_employee({'username': name, 'role': role}, 'Đang làm việc')
            for name, role in [('Director', 'giamdoc'), ('Manager', 'quanly'), ('Staff', 'nhanvien')]]
    class Engine:
        @contextmanager
        def connect(self):
            yield object()
    cells['engine_instance'].cell_contents = Engine
    cells['staff_result'].cell_contents = lambda *args: {'employees': rows, 'shifts_by_department': {}}
    photo_reads = []
    def read(conn, names):
        photo_reads.append(names)
        return {}
    monkeypatch.setattr(photos, 'read_portraits', read)
    response = TestClient(staff_app).get(f'/v2/staff/export.xlsx?include_photos={str(include_photos).lower()}')
    assert response.status_code == 200, response.text
    sheet = load_workbook(BytesIO(style_workbook_bytes(response.content)))['DanhSachNhanSu']
    assert [(sheet.cell(i, 1).value, sheet.cell(i, 2).value) for i in (2, 3)] == [(1, 'Manager'), (2, 'Staff')]
    assert sheet.max_row == 3
    assert photo_reads == ([['Manager', 'Staff']] if include_photos else [])
    assert rows[0]['role'] == 'giamdoc'  # No change to the shared staff directory.

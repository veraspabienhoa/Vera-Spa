from contextlib import contextmanager
from datetime import date
from inspect import getclosurevars, signature
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image
import pytest

import vera_web_v2_staff as staff
import vera_leave_quota_alerts as quota
from vera_web_v2_excel_export_style import style_workbook_bytes


@pytest.fixture
def workbook_builder():
    app = FastAPI()
    dependencies = {name: (lambda *args, **kwargs: None)
                    for name in signature(staff.install_staff_routes).parameters if name != 'app'}
    dependencies.update(identity_type=object, vn_tz=ZoneInfo('Asia/Ho_Chi_Minh'), leave_sheet_id='')
    staff.install_staff_routes(app, **dependencies)
    route = next(r for r in app.routes if r.path == '/v2/staff/export.xlsx')
    return getclosurevars(route.endpoint).nonlocals['build_staff_workbook']


@pytest.mark.parametrize('image_format', ['WEBP', 'PNG', 'JPEG'])
def test_export_embeds_supported_image_and_survives_style_middleware(workbook_builder, image_format):
    photo = BytesIO()
    Image.new('RGB', (30, 40), 'green').save(photo, format=image_format)
    employee = staff._public_employee({'username': 'Test', 'role': 'nhanvien', 'phone': '0123456789'}, 'Đang làm việc')
    payload = workbook_builder([employee], {}, {'Test': photo.getvalue()})
    styled = style_workbook_bytes(payload)
    workbook = load_workbook(BytesIO(styled))
    ws = workbook['DanhSachNhanSu']
    assert len(ws._images) == 1
    assert ws.cell(2, staff.STAFF_EXPORT_COLUMNS.index('Điện thoại') + 1).value == '0123456789'
    with ZipFile(BytesIO(styled)) as archive:
        media = [p for p in archive.namelist() if p.startswith('xl/media/')]
        assert len(media) == 1 and media[0].endswith('.png')


def test_invalid_portrait_does_not_prevent_staff_export(workbook_builder):
    employee = staff._public_employee({'username': 'Test', 'role': 'nhanvien'}, 'Đang làm việc')
    payload = workbook_builder([employee], {}, {'Test': b'broken image'})
    workbook = load_workbook(BytesIO(payload))
    assert workbook['DanhSachNhanSu']['A2'].value == 'Ảnh không đọc được'
    assert workbook['DanhSachNhanSu']['B2'].value == 'Test'


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

from contextlib import nullcontext
from types import SimpleNamespace
from io import BytesIO
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfReader
import vera_web_v2_residence as residence
import vera_web_v2_labor_report as labor


def test_labor_route_checks_permissions_and_selection(monkeypatch):
    actor = SimpleNamespace(role='admin')
    allowed = {'staff_list', 'staff_export'}
    def require(conn, ident, feature):
        if feature not in allowed:
            raise HTTPException(403)
    calls = []
    monkeypatch.setattr(labor, 'labor_rows', lambda conn, ident, names: calls.append(names) or [{'username': n} for n in names if n != 'missing'])
    monkeypatch.setattr(labor, 'render_labor', lambda records, fmt: b'%PDF-test')
    app = FastAPI()
    residence.install_residence_routes(app, engine_instance=lambda: SimpleNamespace(connect=lambda: nullcontext(None)), current_identity=lambda: actor, require_feature=require, identity_type=SimpleNamespace)
    client = TestClient(app)
    def export(names=['A'], fmt='pdf'):
        return client.post('/v2/staff/labor-report/export?format='+fmt, json={'usernames': names})
    response = export(['A', 'A', ' B '])
    assert response.status_code == 200 and calls[-1] == ['A', 'B']
    assert response.headers['cache-control'] == 'private, no-store'
    assert export(['missing']).status_code == 404
    assert export([]).status_code == 422
    assert export([' ']).status_code == 422
    assert export(fmt='html').status_code == 422
    allowed.remove('staff_export')
    assert export().status_code == 403
    actor.role = 'letan'
    allowed.add('staff_export')
    assert export().status_code == 403


def test_labor_uses_only_saved_values_and_preserves_requested_order(monkeypatch):
    monkeypatch.setattr(labor, 'rows', lambda conn, ident: [dict(username=n, department_code='nhanvien', department='Nhân viên') for n in ['A','B']])
    class Result:
        def __init__(self, values): self.values = values
        def mappings(self): return self.values
    class Connection:
        def execute(self, query, *args):
            if 'FROM employees' in str(query):
                return Result([dict(username='A', hourly_salary='0', contract_signed='2026-01-02')])
            return Result([dict(setting_key='contract_1', value_json={'salary_unit':'giờ','salary_amount':'25.000', 'signing_date':'2026-01-01'})])
    result = labor.labor_rows(Connection(), None, ['B','A'])
    assert [r['username'] for r in result] == ['B','A']
    assert result[0]['hourly_salary'] == '25.000'
    assert result[0]['contract_signed'] == ''
    assert result[1]['hourly_salary'] == '0'
    assert result[1]['contract_signed'] == '02-01-2026'
    assert all(r['contract_end'] == '' for r in result)


def test_labor_pdf_has_all_columns_a4_landscape_and_complete_long_roster():
    rows = [dict(username=f'Employee {n}', full_name='Nguyễn Thị Minh Anh', address='Đồng Nai '*20, contract_end='31-12-2026') for n in range(35)]
    doc = PdfReader(BytesIO(labor.render_labor(rows,'pdf')))
    assert len(doc.pages) > 1
    assert all(abs(float(p.mediabox.width)-841.89)<1 and abs(float(p.mediabox.height)-595.28)<1 for p in doc.pages)
    text = '\n'.join(p.extract_text() for p in doc.pages)
    assert 'Employee 34' in ' '.join(text.split()) and '31-12-2026' in text
    assert 'Trưởng phòng' in text and 'Xác nhận của đơn vị' in text
    assert 'Chưa có' not in text

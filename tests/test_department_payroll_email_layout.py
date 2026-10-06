from contextlib import contextmanager
from datetime import date
from html.parser import HTMLParser

from fastapi import FastAPI
from pydantic import BaseModel

import vera_web_v2_department_payroll as dep


class FirstTable(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.tables = 0; self.active = False; self.cell = None; self.row = []; self.rows = []
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.tables += 1; self.active = self.tables == 1
        if self.active and tag == 'tr': self.row = []
        if self.active and tag == 'td': self.cell = ''
    def handle_data(self, data):
        if self.cell is not None: self.cell += data
    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.row.append(self.cell); self.cell = None
        if tag == 'tr' and self.active and self.row: self.rows.append(self.row)
        if tag == 'table': self.active = False


def sample():
    return dict(employee_username='sample', employee_name='HC <Employee>', salary=5_000_000,
        full_allowance=300_000, attendance_bonus=100_000, responsibility=200_000,
        seniority=50_000, combo_sales=150_000, advance=1_000_000,
        violation_penalty=50_000, late_penalty=100_000, total_salary=5_800_000, net_salary=4_650_000,
        email='sample@example.test')


EXPECTED = [
    ['Tiền Lương', '5,000,000 VNĐ'], ['Phụ cấp Full ca', '300,000 VNĐ'],
    ['Chuyên cần', '100,000 VNĐ'], ['Trách nhiệm', '200,000 VNĐ'],
    ['Thâm niên', '50,000 VNĐ'], ['Bán combo', '150,000 VNĐ'],
    ['Tiền ứng lương', '1,000,000 VNĐ'], ['Phạt vi phạm', '50,000 VNĐ'],
    ['Phạt đi trễ', '100,000 VNĐ'], ['Tổng lương', '5,800,000 VNĐ'], ['Thực nhận', '4,650,000 VNĐ'],
]


def test_hc_email_matches_reference_order_and_amounts_in_both_formats():
    row = sample(); original = dict(row)
    violations = [dict(leave_date=date(2026,9,3), leave_reason='Late <unsafe>', detail='Note & details', penalty=100_000)]
    subject, plain, html = dep._email_content(row, date(2026,9,1), date(2026,9,30), violations)
    assert subject == 'Bảng lương sample - 01-09-2026 đến 30-09-2026'
    assert FirstTable(html).rows == EXPECTED
    lines = plain.splitlines()
    summary_start = lines.index('Tiền Lương: 5,000,000 VNĐ')
    assert lines[summary_start:summary_start+11] == [f'{label}: {amount}' for label, amount in EXPECTED]
    assert 'HC &lt;Employee&gt;' in html and 'Late &lt;unsafe&gt;' in html
    assert 'Note &amp; details' in html
    assert '03-09-2026' in plain and '03-09-2026' in html
    assert 'Tổng vi phạm: 150,000 VNĐ' in html
    for content in [plain, html]:
        for irrelevant in ['Tích lũy', 'Phí sinh hoạt', 'Tiền hỗ trợ Locker', 'Vi phạm kỳ trước', 'Hỗ trợ/Hoàn tiền']:
            assert irrelevant not in content
    assert row == original


def test_zero_summary_keeps_every_reference_item():
    _, plain, html = dep._email_content({}, date(2026,9,1), date(2026,9,30), [])
    assert FirstTable(html).rows == [[label, '0 VNĐ'] for label, _ in EXPECTED]
    assert 'Chi tiết vi phạm trong kỳ:' not in html
    assert 'Phụ cấp Full ca: 0 VNĐ' in plain


def test_negative_net_is_displayed_without_clamping_or_rededuction():
    row = sample(); row.update(advance=6_000_000, net_salary=-350_000)
    _, plain, html = dep._email_content(row, date(2026,9,1), date(2026,9,30), [])
    assert FirstTable(html).rows[-1] == ['Thực nhận', '-350,000 VNĐ']
    assert 'Thực nhận: -350,000 VNĐ' in plain
    assert FirstTable(html).rows[-2] == ['Tổng lương', '5,800,000 VNĐ']


def test_email_route_uses_hc_layout_for_selected_employee_outside_database(monkeypatch):
    class Identity(BaseModel):
        employee_username: str = 'admin'
        role: str = 'admin'
    class Database:
        active = False
        @contextmanager
        def connect(self):
            self.active = True
            try: yield self
            finally: self.active = False
        def execute(self, *args):
            return self
        def mappings(self): return self
        def all(self): return []
    database = Database(); app = FastAPI(); messages = []
    class SMTP:
        closed = False
        def send_message(self, message):
            assert not database.active
            messages.append(message)
        def quit(self): self.closed = True
    smtp = SMTP()
    def open_smtp(*args):
        assert not database.active
        return smtp
    monkeypatch.setenv('SMTP_APP_PASSWORD', 'test-secret')
    monkeypatch.setattr(dep, '_settings', lambda *args: {'config': {}})
    monkeypatch.setattr(dep, '_clean_rows', lambda *args, **kwargs: [sample(), {**sample(), 'employee_username':'other', 'email':'other@example.test'}])
    monkeypatch.setattr(dep, '_require_complete_attendance', lambda *args: None)
    monkeypatch.setattr(dep.payroll, '_open_payroll_smtp', open_smtp)
    monkeypatch.setattr(dep, '_workbook', lambda rows, department, label: b'test-xlsx')
    dep.install_department_payroll_routes(app, engine_instance=lambda: database, current_identity=lambda: Identity(),
        require_feature=lambda conn, ident, feature: None, identity_type=Identity, norm=lambda value: str(value or '').strip().casefold())
    endpoint = next(r.endpoint for r in app.routes if r.path == '/v2/department-payroll/email')
    result = endpoint(dep.DepartmentEmail(department='letan', month='2026-09', rows=[sample()], employees=['sample']), Identity())
    assert result['ok'] and len(messages) == 1 and smtp.closed
    message = messages[0]
    assert message['To'] == 'sample@example.test'
    assert FirstTable(message.get_body(preferencelist=('html',)).get_content()).rows == EXPECTED
    assert 'Phụ cấp Full ca: 300,000 VNĐ' in message.get_body(preferencelist=('plain',)).get_content()
    assert [item.get_filename() for item in message.iter_attachments()] == ['Bang_luong_sample_2026-09.xlsx']
    assert message['Subject'] == 'Bảng lương sample - 01-09-2026 đến 30-09-2026'

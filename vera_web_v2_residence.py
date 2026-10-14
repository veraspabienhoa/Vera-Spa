"""Persistent residence roster, projected from employee profiles without bank data."""
from datetime import datetime
from io import BytesIO

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_web_v2_hr import registry, department_code
from vera_auto_check import _norm

COLUMNS = [
    ('username', 'Tên nhân viên'), ('full_name', 'Họ và tên'), ('department', 'Bộ phận'),
    ('birth_date', 'Ngày sinh'), ('gender', 'Giới tính'), ('ethnicity', 'Dân tộc'),
    ('phone', 'Số điện thoại'), ('email', 'Email'), ('cccd_number', 'Số CCCD'),
    ('cccd_issue_date', 'Ngày cấp CCCD'), ('cccd_issue_place', 'Nơi cấp CCCD'),
    ('address', 'Địa chỉ'), ('province', 'Tỉnh/Thành phố'), ('district', 'Quận/Huyện'),
    ('ward', 'Xã/Phường'), ('address_detail', 'Địa chỉ chi tiết'),
    ('employment_status', 'Trạng thái làm việc'), ('employment_start_date', 'Ngày bắt đầu làm'),
    ('employment_end_date', 'Ngày nghỉ việc'), ('work_shift', 'Ca làm việc'),
    ('shift_start_date', 'Ngày bắt đầu ca'), ('rotation_cycle', 'Chu kỳ ca'),
    ('monthly_generated', 'Phép phát sinh tháng'), ('monthly_leave', 'Phép tháng'),
    ('annual_leave', 'Phép năm'),
]
PAYLOAD_FIELDS = {
    'gender': 'Giới tính', 'ethnicity': 'Dân tộc', 'cccd_number': 'Số CCCD',
    'cccd_issue_date': 'Ngày cấp CCCD', 'cccd_issue_place': 'Nơi cấp CCCD',
    'province': 'Tỉnh/Thành phố', 'district': 'Quận/Huyện', 'ward': 'Xã/Phường',
    'address_detail': 'Địa chỉ chi tiết', 'employment_end_date': 'Ngày nghỉ việc',
}
DATE_FIELDS = {'birth_date', 'cccd_issue_date', 'employment_start_date', 'employment_end_date', 'shift_start_date'}


class Membership(BaseModel):
    username: str = Field(min_length=1, max_length=300)
    included: bool = True


def display_date(value):
    raw = str(value or '')
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw[:10], fmt).strftime('%d-%m-%Y')
        except ValueError:
            pass
    return raw


def rows(conn, ident):
    state = registry(conn)
    # Explicit SQL allowlist: neither bank fields nor credentials are loaded.
    fields = ', '.join('payload->>\'' + label + '\' AS ' + key for key, label in PAYLOAD_FIELDS.items())
    records = conn.execute(text('''SELECT username, full_name, role, birth_date, phone, email, address,
        employment_start_date, work_shift, shift_start_date, rotation_cycle,
        monthly_generated, monthly_leave, annual_leave,
        COALESCE(payload->>'Trạng thái làm việc', payload->>'employment_status', 'Đang làm việc') AS employment_status,
        COALESCE(payload->>'vera_residence', 'false') = 'true' AS included,
        COALESCE(payload->>'Ẩn nhân viên', '') AS profile_hidden, ''' + fields + '''
        FROM employees WHERE COALESCE(payload->>'__deleted','false') <> 'true'
        ORDER BY COALESCE(stt,2147483647), username''')).mappings()
    output = []
    for record in records:
        row = dict(record)
        if str(row.get('role') or '').lower() == 'admin':
            continue
        if ident.role != 'admin' and (row.get('role') == 'quanly' or _norm(row.get('profile_hidden')) in {'true','1','yes','co','x'}):
            continue
        code = department_code(row, state)
        row['department'] = state['departments'].get(code, {}).get('name', code)
        projected = {key: row.get(key) if row.get(key) is not None else '' for key, _ in COLUMNS}
        for field in DATE_FIELDS:
            projected[field] = display_date(projected[field])
        output.append({**projected, 'department_code': code, 'included': bool(row['included'])})
    return output


def filtered(records, department='', search=''):
    needle = _norm(search)
    return [row for row in records if row['included']
            and (not department or row['department_code'] == department)
            and (not needle or needle in _norm(row['username'] + ' ' + row['full_name']))]


def workbook(records):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Tạm trú'
    ws.append(['STT'] + [label for _, label in COLUMNS])
    for index, row in enumerate(records, 1):
        ws.append([index] + [row[key] for key, _ in COLUMNS])
        # Preserve identity/phone leading zeroes and disable formula interpretation.
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = 's'
                cell.number_format = '@'
            cell.alignment = Alignment(vertical='top', wrap_text=True)
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='14645F')
        ws.column_dimensions[cell.column_letter].width = 23 if cell.column > 1 else 7
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def install_residence_routes(app, *, engine_instance, current_identity, require_feature, identity_type):
    @app.get('/v2/residence')
    def overview(ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, 'residence_view')
            records = rows(conn, ident)
        departments = {r['department_code']: r['department'] for r in records}
        return {'columns': [{'key': k, 'label': label} for k, label in COLUMNS],
                'records': [r for r in records if r['included']],
                'employees': [{k: r[k] for k in ('username','full_name','department_code','department','included')} for r in records],
                'departments': [{'code': k, 'name': v} for k, v in sorted(departments.items())]}

    @app.put('/v2/residence')
    def membership(body: Membership, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'residence_view')
            require_feature(conn, ident, 'residence_manage')
            # Serialize with staff profile row writes; change only the roster flag.
            conn.execute(text("SELECT username FROM employees WHERE username=:username FOR UPDATE"), {'username': body.username})
            if body.username not in {r['username'] for r in rows(conn, ident)}:
                raise HTTPException(404, 'Không tìm thấy nhân viên phù hợp.')
            changed = conn.execute(text('''UPDATE employees SET
                payload=jsonb_set(COALESCE(payload,'{}'::jsonb), '{vera_residence}', CAST(:value AS jsonb)),
                updated_at=NOW() WHERE username=:username AND COALESCE(payload->>'__deleted','false') <> 'true'
                RETURNING username'''), {'username': body.username, 'value': 'true' if body.included else 'false'}).first()
            if not changed:
                raise HTTPException(409, 'Hồ sơ đã thay đổi. Vui lòng tải lại.')
        return {'ok': True, 'message': 'Đã thêm nhân viên vào bảng tạm trú.' if body.included else 'Đã bỏ nhân viên khỏi bảng tạm trú.'}

    @app.get('/v2/residence/export.xlsx')
    def export(department: str = '', search: str = '', ident: identity_type = Depends(current_identity)):
        with engine_instance().connect() as conn:
            require_feature(conn, ident, 'residence_view')
            require_feature(conn, ident, 'residence_export')
            records = filtered(rows(conn, ident), department, search)
        return StreamingResponse(workbook(records),
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename="VERA_TamTru.xlsx"'})

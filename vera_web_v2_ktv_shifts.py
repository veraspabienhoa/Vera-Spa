"""Permission-scoped KTV shift catalog backed by the existing shift settings."""
from copy import deepcopy
from hashlib import sha256
import re
from typing import Literal
from uuid import uuid4

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_web_v2_live_tour_roster import key, shift_label, display_shift_label
from vera_web_v2_shift_break_admin import _put_setting

DEPARTMENT = 'Nhân viên + Leader'
CATALOG_LOCK = 'vera:shift:shift_definitions'


class KtvShiftSave(BaseModel):
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=100)
    main_shift: Literal['Ca 1', 'Ca 2']
    start: str
    end: str
    fixed: bool = False


class KtvCycleSave(BaseModel):
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=80)
    days: int = Field(ge=1, le=365)


def identifier(row):
    return str(row.get('ID') or 'legacy-' + sha256(display_shift_label(row).encode()).hexdigest()[:20])


def is_ktv(row):
    return key(row.get('Bộ phận') or DEPARTMENT) == key(DEPARTMENT)


def active(row):
    return key(row.get('Trạng thái')) != 'da xoa'


def public_rows(definitions):
    return [{'id': identifier(row), 'name': row.get('Tên ca', ''),
             'main_shift': row.get('Ca chính') or shift_label(row.get('Tên ca')),
             'start': row.get('Giờ bắt đầu', ''), 'end': row.get('Giờ kết thúc', ''),
             'fixed': key(row.get('Ghi chú')) == 'khong doi'}
            for row in definitions if is_ktv(row) and active(row)]


def change_definition(definitions, body, shift_id=None, delete=False):
    result = deepcopy(definitions)
    row = next((r for r in result if identifier(r) == shift_id and is_ktv(r) and active(r)), None) if shift_id else None
    if shift_id and row is None:
        raise HTTPException(404, 'Ca không còn tồn tại trong danh mục Leader / Nhân viên.')
    before = deepcopy(row)
    if delete:
        row['Trạng thái'] = 'Đã xóa'
        return result, before, row
    name = body.name.strip()
    if not name or any(ord(c) < 32 for c in name):
        raise HTTPException(400, 'Nhập tên ca hợp lệ.')
    if any(not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value) for value in (body.start, body.end)) or body.start == body.end:
        raise HTTPException(400, 'Giờ bắt đầu/kết thúc cần dạng HH:MM và không trùng nhau.')
    if any(is_ktv(r) and active(r) and identifier(r) != shift_id and key(r.get('Tên ca')) == key(name) for r in result):
        raise HTTPException(409, 'Tên ca đã tồn tại. Ca chính có thể giống nhau, tên ca cần khác nhau.')
    if row is None:
        row = {'ID': 'KTV-' + str(uuid4()), 'Bộ phận': DEPARTMENT, 'Thứ tự': len(result) + 1}
        result.append(row)
    row.setdefault('ID', identifier(row))
    note = 'Không đổi' if body.fixed else '' if key(row.get('Ghi chú')) == 'khong doi' else row.get('Ghi chú', '')
    row.update({'Tên ca': name, 'Ca chính': body.main_shift, 'Giờ bắt đầu': body.start,
                'Giờ kết thúc': body.end, 'Ghi chú': note, 'Trạng thái': 'Đang dùng'})
    return result, before, row


def read_catalog(conn):
    row = conn.execute(text("SELECT value_json, revision FROM vera_app_setting WHERE category='shift' AND setting_key='shift_definitions'")).mappings().first()
    return (deepcopy(row['value_json']), int(row.get('revision') or 0)) if row else ([], 0)


def install_ktv_shift_routes(app, *, engine_instance, current_identity, require_feature, feature_allowed):
    def grants(conn, ident):
        return {action: bool(feature_allowed(conn, ident, f'ktv_shift_{action}')) for action in ('view', 'create', 'edit', 'delete')}

    @app.get('/v2/staff/ktv-shifts')
    def get_catalog(ident=Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'ktv_shift_view')
            rows, revision = read_catalog(conn)
            return {'shifts': public_rows(rows), 'revision': revision, 'permissions': grants(conn, ident)}

    def mutate(ident, expected_revision, body=None, shift_id=None, delete=False):
        permission = 'delete' if delete else 'edit' if shift_id else 'create'
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'ktv_shift_view')
            require_feature(conn, ident, f'ktv_shift_{permission}')
            conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': CATALOG_LOCK})
            definitions, revision = read_catalog(conn)
            if expected_revision != revision:
                raise HTTPException(409, 'Danh mục ca đã thay đổi. Hãy làm mới trước khi lưu.')
            updated, before, after = change_definition(definitions, body, shift_id, delete)
            if before:
                params = {'label': display_shift_label(before), 'name': str(before.get('Tên ca') or '')}
                predicate = "lower(btrim(COALESCE(role,''))) IN ('leader','nhanvien') AND (lower(btrim(work_shift))=lower(:label) OR lower(btrim(work_shift))=lower(:name))"
                if delete:
                    if conn.execute(text('SELECT username FROM employees WHERE ' + predicate + ' LIMIT 1'), params).first():
                        raise HTTPException(409, 'Ca đang được phân cho nhân viên. Hãy chuyển nhân viên sang ca khác trước khi xóa.')
                else:
                    conn.execute(text("UPDATE employees SET work_shift=:new_label, payload=jsonb_set(COALESCE(payload,'{}'::jsonb), '{Ca làm việc}', to_jsonb(CAST(:new_label AS text)), true), updated_at=NOW() WHERE " + predicate), {**params, 'new_label': display_shift_label(after)})
            _put_setting(conn, 'shift_definitions', updated, str(ident.employee_username))
            return {'shifts': public_rows(updated), 'revision': revision + 1, 'permissions': grants(conn, ident)}

    @app.post('/v2/staff/ktv-shifts')
    def create_shift(body: KtvShiftSave, ident=Depends(current_identity)):
        return mutate(ident, body.expected_revision, body)

    @app.put('/v2/staff/ktv-shifts/{shift_id}')
    def edit_shift(shift_id: str, body: KtvShiftSave, ident=Depends(current_identity)):
        return mutate(ident, body.expected_revision, body, shift_id)

    @app.delete('/v2/staff/ktv-shifts/{shift_id}')
    def delete_shift(shift_id: str, expected_revision: int = Query(ge=0), ident=Depends(current_identity)):
        return mutate(ident, expected_revision, shift_id=shift_id, delete=True)

    def cycle_catalog(conn):
        row = conn.execute(text("SELECT value_json, revision FROM vera_app_setting WHERE category='shift' AND setting_key='rotation_cycles'")).mappings().first()
        items = deepcopy(row['value_json']) if row and isinstance(row['value_json'], list) else []
        return items, int(row.get('revision') or 0) if row else 0

    def cycle_public(items):
        base = [{'id': 'weekly', 'name': 'Theo chu kỳ Tuần', 'days': 7, 'label': 'Theo chu kỳ Tuần', 'system': True},
                {'id': 'fixed', 'name': 'Cố định', 'days': 0, 'label': 'Cố định (Không đổi)', 'system': True}]
        return base + [dict(item, system=False) for item in items if isinstance(item, dict) and item.get('active', True)]

    def admin_only(ident):
        if str(getattr(ident, 'role', '') or '').strip().lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được thêm/sửa/xóa chu kỳ.')

    @app.get('/v2/staff/ktv-cycles')
    def get_cycles(ident=Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'ktv_shift_view')
            items, revision = cycle_catalog(conn)
            return {'cycles': cycle_public(items), 'revision': revision}

    def save_cycle_value(ident, body, cycle_id=None, delete=False):
        admin_only(ident)
        with engine_instance().begin() as conn:
            conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'vera:shift:rotation_cycles'})
            items, revision = cycle_catalog(conn)
            if body.expected_revision != revision:
                raise HTTPException(409, 'Danh mục chu kỳ đã thay đổi. Hãy làm mới.')
            current = next((item for item in items if str(item.get('id')) == str(cycle_id)), None) if cycle_id else None
            if cycle_id and not current:
                raise HTTPException(404, 'Không tìm thấy chu kỳ.')
            if delete:
                label = str(current.get('label') or '')
                if conn.execute(text("SELECT username FROM employees WHERE lower(btrim(rotation_cycle))=lower(:label) LIMIT 1"), {'label': label}).first():
                    raise HTTPException(409, 'Chu kỳ đang được nhân viên sử dụng. Hãy đổi chu kỳ trước khi xóa.')
                current['active'] = False
            else:
                name = body.name.strip()
                label = 'Theo chu kỳ Tuần' if body.days == 7 and key(name) in {'theo chu ky tuan', 'tuan'} else f'{name} ({body.days} ngày)'
                if current is None:
                    current = {'id': 'CYCLE-' + str(uuid4())}
                    items.append(current)
                current.update({'name': name, 'days': body.days, 'label': label, 'active': True})
            _put_setting(conn, 'rotation_cycles', items, str(ident.employee_username))
            return {'cycles': cycle_public(items), 'revision': revision + 1}

    @app.post('/v2/staff/ktv-cycles')
    def create_cycle(body: KtvCycleSave, ident=Depends(current_identity)):
        return save_cycle_value(ident, body)

    @app.put('/v2/staff/ktv-cycles/{cycle_id}')
    def edit_cycle(cycle_id: str, body: KtvCycleSave, ident=Depends(current_identity)):
        return save_cycle_value(ident, body, cycle_id)

    @app.delete('/v2/staff/ktv-cycles/{cycle_id}')
    def delete_cycle(cycle_id: str, expected_revision: int = Query(ge=0), ident=Depends(current_identity)):
        return save_cycle_value(ident, KtvCycleSave(expected_revision=expected_revision, name='delete', days=1), cycle_id, True)


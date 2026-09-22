"""Department and payroll classification, independent of authorization roles."""

import json
from copy import deepcopy
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

KEY = 'hr_registry'
DEFAULT_DEPARTMENTS = {
    code: {'name': name, 'salary_mode': mode, 'active': True}
    for code, name, mode in [
        ('admin', 'Admin', 'monthly'), ('giamdoc', 'Giám đốc', 'monthly'),
        ('quanly', 'Quản lý', 'hourly'), ('letan', 'Lễ tân', 'hourly'),
        ('thungan', 'Thu ngân', 'hourly'), ('locker', 'Locker', 'hourly'),
        ('support', 'Support', 'hourly'), ('tapvu', 'Tạp vụ', 'monthly'),
        ('leader', 'Leader', 'tip'), ('nhanvien', 'Nhân viên', 'tip'),
    ]
}
# Constant SQL only; names/values supplied by users are never interpolated.
REGISTRY_SQL = "(SELECT value_json FROM vera_app_setting WHERE category='payroll' AND setting_key='hr_registry' LIMIT 1)"
DEPARTMENT_SQL = f"COALESCE({REGISTRY_SQL}->'assignments'->>username, lower(COALESCE(role,'')))"
_DEFAULT_SQL = json.dumps(DEFAULT_DEPARTMENTS, ensure_ascii=False).replace("'", "''")
DEFINITION_SQL = f"COALESCE({REGISTRY_SQL}->'departments'->({DEPARTMENT_SQL}), CAST('{_DEFAULT_SQL}' AS jsonb)->({DEPARTMENT_SQL}))"
MODE_SQL = f"(CASE WHEN COALESCE(({DEFINITION_SQL})->>'active','true') = 'true' THEN ({DEFINITION_SQL})->>'salary_mode' ELSE NULL END)"
TIP_SQL = f"{MODE_SQL} = 'tip'"
ADMIN_PAY_SQL = f"{MODE_SQL} IN ('hourly','monthly')"


def registry(conn):
    from vera_web_v2_payroll import _setting
    saved = _setting(conn, KEY, {})
    return {
        'departments': {**deepcopy(DEFAULT_DEPARTMENTS), **saved.get('departments', {})},
        'assignments': dict(saved.get('assignments', {})),
        'revision': int(saved.get('revision', 0)),
    }


def departments(conn, modes=None):
    return {code: item for code, item in registry(conn)['departments'].items()
            if item.get('active', True) and (modes is None or item['salary_mode'] in modes)}


def department_code(employee, state):
    return state['assignments'].get(employee['username'], str(employee.get('role') or '').lower())


def admin_departments(conn):
    return departments(conn, {'hourly', 'monthly'})


class DepartmentWrite(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r'^[a-z][a-z0-9_]*$')
    name: str = Field(min_length=1, max_length=100)
    salary_mode: Literal['monthly', 'hourly', 'tip']
    revision: int = Field(ge=0)
    creating: bool = False


class EmployeeDepartmentWrite(BaseModel):
    department: str = Field(min_length=1, max_length=50)
    revision: int = Field(ge=0)


class DepartmentDelete(BaseModel):
    revision: int = Field(ge=0)


def checked_revision(state, revision):
    if state['revision'] != revision:
        raise HTTPException(409, 'Nhân sự đã được thay đổi. Hãy làm mới rồi thử lại.')


def validate_definition(state, body):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, 'Tên bộ phận không được để trống.')
    if any(code != body.code and item.get('active', True) and item['name'].casefold() == name.casefold()
           for code, item in state['departments'].items()):
        raise HTTPException(409, 'Tên bộ phận đã tồn tại.')
    return {'name': name, 'salary_mode': body.salary_mode, 'active': True}


def install_hr_routes(app, *, engine_instance, current_identity, identity_type):
    from vera_web_v2_payroll import _put_setting

    def admin(ident):
        if str(ident.role).lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được quản lý Nhân sự.')

    def lock(conn):
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:hr:registry'))"))

    def employees(conn):
        return [dict(row) for row in conn.execute(text("""
            SELECT username, COALESCE(full_name,'') AS full_name, role,
                   COALESCE(payload->>'Trạng thái làm việc',payload->>'employment_status','Đang làm việc') AS employment_status
            FROM employees WHERE COALESCE(payload->>'__deleted','false') <> 'true'
            ORDER BY COALESCE(stt,2147483647), username
        """)).mappings().all()]

    def persist(conn, state, ident):
        state['revision'] += 1
        _put_setting(conn, KEY, state, ident.employee_username)

    @app.get('/v2/hr')
    def get_hr(ident: identity_type = Depends(current_identity)):
        admin(ident)
        with engine_instance().connect() as conn:
            state = registry(conn)
            people = employees(conn)
            for person in people:
                person['department'] = department_code(person, state)
            return {'ok': True, **state, 'employees': people}

    @app.put('/v2/hr/departments')
    def save_department(body: DepartmentWrite, ident: identity_type = Depends(current_identity)):
        admin(ident)
        with engine_instance().begin() as conn:
            lock(conn)
            state = registry(conn)
            checked_revision(state, body.revision)
            old = state['departments'].get(body.code)
            if body.creating and old:
                raise HTTPException(409, 'Mã bộ phận đã tồn tại. Hãy chọn Sửa hoặc dùng mã mới.')
            if old and not old.get('active', True):
                raise HTTPException(409, 'Mã bộ phận đã xóa không được tái sử dụng. Hãy chọn mã mới.')
            state['departments'][body.code] = validate_definition(state, body)
            # Freeze legacy assignments before changing payroll classification.
            for person in employees(conn):
                state['assignments'].setdefault(person['username'], str(person['role'] or '').lower())
            persist(conn, state, ident)
        return {'ok': True, 'revision': state['revision']}

    @app.delete('/v2/hr/departments/{code}')
    def delete_department(code: str, body: DepartmentDelete, ident: identity_type = Depends(current_identity)):
        admin(ident)
        with engine_instance().begin() as conn:
            lock(conn)
            state = registry(conn)
            checked_revision(state, body.revision)
            item = state['departments'].get(code)
            if not item or not item.get('active', True):
                raise HTTPException(404, 'Không tìm thấy bộ phận.')
            if any(department_code(person, state) == code for person in employees(conn)):
                raise HTTPException(409, 'Hãy chuyển toàn bộ nhân viên (kể cả đã nghỉ việc) sang bộ phận khác trước khi xóa.')
            item['active'] = False
            persist(conn, state, ident)
        return {'ok': True, 'revision': state['revision']}

    @app.put('/v2/hr/employees/{username}/department')
    def assign_department(username: str, body: EmployeeDepartmentWrite, ident: identity_type = Depends(current_identity)):
        admin(ident)
        with engine_instance().begin() as conn:
            lock(conn)
            state = registry(conn)
            checked_revision(state, body.revision)
            if not state['departments'].get(body.department, {}).get('active', False):
                raise HTTPException(400, 'Bộ phận không tồn tại hoặc đã xóa.')
            if not any(person['username'] == username for person in employees(conn)):
                raise HTTPException(404, 'Không tìm thấy nhân viên.')
            state['assignments'][username] = body.department
            persist(conn, state, ident)
        return {'ok': True, 'revision': state['revision']}


def preserve_employee_department(conn, username, old_role, actor):
    """Pin a legacy department before an authorization-role edit, in its transaction."""
    from vera_web_v2_payroll import _put_setting
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:hr:registry'))"))
    state = registry(conn)
    if username not in state['assignments']:
        state['assignments'][username] = str(old_role or '').lower()
        state['revision'] += 1
        _put_setting(conn, KEY, state, actor)

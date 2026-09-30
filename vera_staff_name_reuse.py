"""Separate a retired directory identity before a new person reuses its name.

Reuse never revives the old auth profile. Unknown business references fail
closed; this path is for retired identities with only auth/device remnants.
"""
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from vera_employee_names import previous_names
from vera_web_v2_local_auth import revoke_local_sessions, SESSION_CATEGORY, ATTEMPT_CATEGORY

AUTH_TABLES = {'vera_v2_user_profile', 'vera_v2_active_device',
               'vera_v2_active_device_session', 'vera_v2_push_subscription'}
IDENTITY_COLUMNS = ('username', 'employee_username', 'employee_name', 'trainer_username',
                    'evaluator_username', 'recipient_username')


def retired(row, norm):
    payload = row.get('payload') or {}
    return str(payload.get('__deleted', '')).lower() == 'true' or norm(
        payload.get('Trạng thái làm việc') or payload.get('employment_status')) == norm('Đã nghỉ việc')


def contains_name(value, wanted, norm):
    if isinstance(value, str):
        return norm(value) == wanted
    if isinstance(value, list):
        return any(contains_name(v, wanted, norm) for v in value)
    if isinstance(value, dict):
        return any(norm(k) == wanted or contains_name(v, wanted, norm) for k, v in value.items())
    return False


def prepare_reuse(conn, directory, username, norm, actor):
    wanted = norm(username)
    matches = [row for row in directory if wanted in {norm(row['username']), *(norm(a) for a in previous_names(row))}]
    if not matches:
        return None
    if any(str(row.get('role') or '').lower() in {'admin', 'giamdoc'} for row in matches):
        raise HTTPException(409, 'Không tự động tái sử dụng tên tài khoản quản trị.')
    if any(not retired(row, norm) for row in matches):
        raise HTTPException(409, 'Tên nhân viên trùng với tài khoản đang làm việc hoặc tạm nghỉ (kể cả tên cũ đang liên kết).')
    if any(norm(row['username']) != wanted for row in matches):
        raise HTTPException(409, 'Tên này còn liên kết lịch sử đổi tên. Cần tách lịch sử trước khi cấp cho người mới.')
    quote = conn.dialect.identifier_preparer.quote
    columns = conn.execute(text('''SELECT table_name,column_name FROM information_schema.columns
        WHERE table_schema=current_schema() AND column_name=ANY(:columns)
        AND data_type IN ('text','character varying') ORDER BY table_name,column_name'''),
        {'columns': list(IDENTITY_COLUMNS)}).mappings().all()
    for row in matches:
        old = row['username']
        for column in columns:
            table, field = column['table_name'], column['column_name']
            if table == 'employees' or table in AUTH_TABLES:
                continue
            linked = conn.execute(text(f'SELECT 1 FROM {quote(table)} WHERE lower(btrim({quote(field)}))=lower(btrim(:name)) LIMIT 1'), {'name': old}).first()
            if linked:
                raise HTTPException(409, 'Hồ sơ cũ còn lịch sử nghiệp vụ. Chưa tái sử dụng tên để tránh gán dữ liệu cũ cho người mới.')
        json_columns = conn.execute(text("""SELECT table_name,column_name FROM information_schema.columns
            WHERE table_schema=current_schema() AND data_type IN ('json','jsonb')
            ORDER BY table_name,column_name""")).mappings().all()
        for column in json_columns:
            table, field = column['table_name'], column['column_name']
            if table in AUTH_TABLES or table in {'employees', 'vera_app_setting'}:
                continue
            linked = conn.execute(text(f"SELECT 1 FROM {quote(table)} WHERE jsonb_path_exists(CAST({quote(field)} AS jsonb), '$.** ? (@ == $name)', CAST(:vars AS jsonb)) LIMIT 1"),
                                  {'vars': json.dumps({'name': old})}).first()
            if linked:
                raise HTTPException(409, 'Hồ sơ cũ còn dữ liệu lịch sử dạng JSON. Chưa tái sử dụng tên để tránh gán nhầm dữ liệu.')
        # Settings can hold FaceGate mappings, Live Tour state, salary settings,
        # or other identity-bearing JSON. Never transfer them to a new person.
        settings = conn.execute(text('SELECT category,setting_key,value_json FROM vera_app_setting')).mappings().all()
        for setting in settings:
            if setting['category'] in {SESSION_CATEGORY, ATTEMPT_CATEGORY, 'staff_retired_identity'}:
                continue
            if setting['category'] == 'authorization' and setting['setting_key'] == 'feature_permissions':
                continue  # Moved explicitly below under its existing write lock.
            if contains_name(setting['value_json'], wanted, norm):
                raise HTTPException(409, 'Hồ sơ cũ còn liên kết cấu hình/Face ID hoặc lịch sử. Cần tách liên kết trước khi tái sử dụng tên.')
        archived = 'retired-' + str(uuid4())
        revoke_local_sessions(conn, old, 'employee_name_reused')
        payload = dict(row.get('payload') or {})
        payload.update(__deleted=True, __retired_username=old,
                       __retired_by=actor, **{'Tên hệ thống': archived, 'Tên nhân viên': archived})
        # The profile FK may cascade; the explicit update also covers older
        # installations without it. Keep the old auth UUID, but inactive.
        conn.execute(text('''UPDATE employees SET username=:archived,login_locked=true,
            remember_token_hash='',remember_token_expiry='',payload=CAST(:payload AS jsonb),updated_at=NOW()
            WHERE username=:old'''), {'archived': archived, 'old': old, 'payload': json.dumps(payload, ensure_ascii=False)})
        for table in sorted(AUTH_TABLES):
            if not any(c['table_name'] == table and c['column_name'] == 'employee_username' for c in columns):
                continue
            conn.execute(text(f'UPDATE {quote(table)} SET employee_username=:archived WHERE lower(btrim(employee_username))=lower(btrim(:old))'), {'archived': archived, 'old': old})
        if any(c['table_name'] == 'vera_v2_user_profile' for c in columns):
            conn.execute(text('UPDATE vera_v2_user_profile SET is_active=false,updated_at=NOW() WHERE employee_username=:archived'), {'archived': archived})
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:v2:feature_permissions'))"))
        setting = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='authorization' AND setting_key='feature_permissions' FOR UPDATE")).scalar()
        if isinstance(setting, dict):
            for item in setting.get('accounts', []) or []:
                if isinstance(item, dict) and norm(item.get('target')) == wanted:
                    item['target'] = archived
            conn.execute(text("UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb),revision=revision+1,updated_at=NOW() WHERE category='authorization' AND setting_key='feature_permissions'"), {'value': json.dumps(setting, ensure_ascii=False)})
    # A fresh auth UUID prevents deterministic username-based UUID reuse.
    return str(uuid4())

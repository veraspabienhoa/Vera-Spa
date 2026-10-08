import json
from uuid import UUID
import pytest
from fastapi import HTTPException
from sqlalchemy import text
import vera_staff_name_reuse as reuse
from vera_web_v2_system_name import _name_key as norm
from vera_web_v2_local_auth import local_auth_user_id, SESSION_RECORD_KIND, STORE_VERSION
from test_live_tour_resource_postgres import database


def person(status='Đã nghỉ việc', deleted=True):
    return {'username': 'New', 'payload': {'__deleted': deleted, 'Trạng thái làm việc': status}}


@pytest.mark.parametrize('status', ['Đang làm việc', 'Tạm thời nghỉ việc'])
def test_active_and_temporary_names_still_block(status):
    with pytest.raises(HTTPException) as exc:
        reuse.prepare_reuse(None, [person(status, False)], 'NEW', norm, 'Admin')
    assert exc.value.status_code == 409


def test_unoccupied_name_needs_no_identity_replacement():
    assert reuse.prepare_reuse(None, [], 'New', norm, 'Admin') is None


def setup(database):
    row = person()
    with database.begin() as conn:
        conn.execute(text('''ALTER TABLE employees ADD PRIMARY KEY(username);
            ALTER TABLE employees ADD COLUMN payload jsonb, ADD COLUMN login_locked boolean,
                ADD COLUMN remember_token_hash text, ADD COLUMN remember_token_expiry text,
                ADD COLUMN updated_at timestamptz;
            ALTER TABLE vera_app_setting ADD COLUMN source text, ADD COLUMN updated_by text;
            CREATE TABLE vera_v2_user_profile(employee_username text REFERENCES employees(username) ON UPDATE CASCADE,
                auth_user_id uuid PRIMARY KEY,is_active boolean,updated_at timestamptz);
            CREATE TABLE vera_v2_active_device(employee_username text,device_id text);'''))
        conn.execute(text("INSERT INTO employees(username,payload,login_locked) VALUES('New',CAST(:payload AS jsonb),true)"), {'payload': json.dumps(row['payload'])})
        conn.execute(text("INSERT INTO vera_v2_user_profile VALUES('New',CAST(:id AS uuid),false,NOW())"), {'id': local_auth_user_id('New')})
        conn.execute(text("INSERT INTO vera_v2_active_device VALUES('New','old-device')"))
        conn.execute(text("INSERT INTO vera_app_setting(category,setting_key,value_json,revision) VALUES('authorization','feature_permissions',CAST(:value AS jsonb),1)"), {'value': json.dumps({'accounts':[{'target':'New','feature':'permission_admin','allowed':True}]})})
        # Prior local session must not become usable if the new password matches.
        conn.execute(text("INSERT INTO vera_app_setting(category,setting_key,value_json,revision) VALUES(:category,'old-session',CAST(:value AS jsonb),1)"),
            {'category': reuse.SESSION_CATEGORY, 'value': json.dumps({'kind':SESSION_RECORD_KIND,'version':str(STORE_VERSION),'employee_username':'New'})})
    return row


def test_reuse_separates_old_profile_device_and_permissions(database, monkeypatch):
    row = setup(database)
    # Exercise the real revocation SQL against this test's isolated schema.
    monkeypatch.setattr('vera_web_v2_local_auth.SESSION_STORE_TABLE', 'vera_app_setting')
    with database.begin() as conn:
        identity = reuse.prepare_reuse(conn, [row], 'New', norm, 'Admin')
        assert str(UUID(identity)) == identity and identity != local_auth_user_id('New')
        old = conn.execute(text("SELECT username,payload FROM employees WHERE payload->>'__retired_username'='New'")).mappings().one()
        assert old['username'].startswith('retired-') and old['payload']['__deleted']
        conn.execute(text("INSERT INTO employees(username,payload,login_locked) VALUES('New',CAST(:payload AS jsonb),false)"), {'payload':json.dumps({'__auth_identity_id':identity})})
        profile = conn.execute(text('SELECT * FROM vera_v2_user_profile')).mappings().one()
        assert profile['employee_username'] == old['username'] and not profile['is_active']
        assert str(profile['auth_user_id']) == local_auth_user_id('New')
        assert conn.execute(text('SELECT employee_username FROM vera_v2_active_device')).scalar() == old['username']
        grants = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='authorization'")).scalar()
        assert grants['accounts'][0]['target'] == old['username']
        session = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE setting_key='old-session'")).scalar()
        assert session['revoked_at'] and session['revoke_reason'] == 'employee_name_reused'


def test_failed_create_rolls_back_retirement(database, monkeypatch):
    row = setup(database)
    monkeypatch.setattr(reuse, 'revoke_local_sessions', lambda *a: None)
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            reuse.prepare_reuse(conn, [row], 'New', norm, 'Admin')
            raise RuntimeError('create validation failed')
    with database.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM employees WHERE username='New'")).scalar() == 1
        assert conn.execute(text('SELECT employee_username FROM vera_v2_user_profile')).scalar() == 'New'


def test_linked_business_history_is_not_reassigned(database, monkeypatch):
    row = setup(database)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE historical_payroll(employee_username text,amount int)'))
        conn.execute(text("INSERT INTO historical_payroll VALUES('New',123)"))
    with pytest.raises(HTTPException) as exc:
        with database.begin() as conn:
            reuse.prepare_reuse(conn, [row], 'New', norm, 'Admin')
    assert exc.value.status_code == 409
    with database.connect() as conn:
        assert conn.execute(text("SELECT amount FROM historical_payroll WHERE employee_username='New'")).scalar() == 123
        assert conn.execute(text("SELECT count(*) FROM employees WHERE username='New'")).scalar() == 1


def test_nested_settings_block_unsafe_facegate_inheritance(database):
    row = setup(database)
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_app_setting(category,setting_key,value_json) VALUES('facegate','mapping_test','[{\"username\":\"New\"}]')"))
    with pytest.raises(HTTPException) as exc:
        with database.begin() as conn:
            reuse.prepare_reuse(conn, [row], 'New', norm, 'Admin')
    assert exc.value.status_code == 409


def test_permission_cache_reloads_when_another_worker_retires_name():
    import ast
    import threading
    import time
    from pathlib import Path
    tree = ast.parse(Path('vera_web_v2_api.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_permission_payload')
    cache = {'loaded_at': time.monotonic(), 'revision': 1,
             'payload': {'accounts': [{'target': 'New', 'allowed': True}]}}
    namespace = {'Any': object, 'time': time, 'text': text,
                 '_permission_cache_lock': threading.Lock(),
                 '_permission_cache': cache, '_PERMISSION_CACHE_SECONDS': 60}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<permission-cache>', 'exec'), namespace)

    class Connection:
        calls = 0
        def execute(self, statement):
            self.calls += 1
            value = 2 if 'SELECT revision' in str(statement) else {'accounts': [{'target': 'retired-old', 'allowed': True}]}
            class Result:
                def scalar_one_or_none(self):
                    return value
            return Result()

    conn = Connection()
    result = namespace['_permission_payload'](conn)
    assert result['accounts'][0]['target'] == 'retired-old'
    assert conn.calls == 2
    namespace['_permission_payload'](conn)
    assert conn.calls == 3  # Same revision reuses the payload, but verifies revision.


@pytest.mark.parametrize('table', ['vera_dataset_cache', 'vera_primary_dataset', 'vera_source_row'])
def test_deleted_name_can_be_reused_despite_frozen_credentials_mirror(database, monkeypatch, table):
    row = setup(database)
    monkeypatch.setattr('vera_web_v2_local_auth.SESSION_STORE_TABLE', 'vera_app_setting')
    snapshot = [{'Tên nhân viên': 'New', 'username': 'New', 'annual_leave': 99}]
    with database.begin() as conn:
        conn.execute(text(f'CREATE TABLE {table}(dataset_key text,payload jsonb,checksum text)'))
        conn.execute(text(f"INSERT INTO {table} VALUES('credentials',CAST(:payload AS jsonb),'original-checksum')"),
                     {'payload': json.dumps(snapshot)})
        identity = reuse.prepare_reuse(conn, [row], 'new', norm, 'Admin')
        conn.execute(text("INSERT INTO employees(username,payload,login_locked) VALUES('new',CAST(:payload AS jsonb),false)"),
                     {'payload': json.dumps({'__auth_identity_id': identity, 'annual_leave': 0})})
        assert conn.execute(text(f'SELECT payload FROM {table}')).scalar_one() == snapshot
        assert conn.execute(text(f'SELECT checksum FROM {table}')).scalar_one() == 'original-checksum'
        fresh = conn.execute(text("SELECT payload FROM employees WHERE username='new'")).scalar_one()
        assert fresh['annual_leave'] == 0 and identity != local_auth_user_id('New')
        assert not conn.execute(text('SELECT is_active FROM vera_v2_user_profile')).scalar_one()
        assert conn.execute(text('SELECT employee_username FROM vera_v2_active_device')).scalar_one().startswith('retired-')


@pytest.mark.parametrize('table', ['vera_dataset_cache', 'vera_primary_dataset', 'vera_source_row'])
@pytest.mark.parametrize('dataset', ['payroll_history', 'leave_primary', 'violation_debt'])
def test_directory_mirror_exception_never_ignores_other_business_datasets(database, table, dataset):
    row = setup(database)
    history = [{'employee_name': 'New', 'amount': 123456}]
    with database.begin() as conn:
        conn.execute(text(f'CREATE TABLE {table}(dataset_key text,payload jsonb)'))
        conn.execute(text(f'INSERT INTO {table} VALUES(:dataset,CAST(:payload AS jsonb))'),
                     {'dataset': dataset, 'payload': json.dumps(history)})
    with pytest.raises(HTTPException) as exc:
        with database.begin() as conn:
            reuse.prepare_reuse(conn, [row], 'new', norm, 'Admin')
    assert exc.value.status_code == 409
    with database.connect() as conn:
        assert conn.execute(text(f'SELECT payload FROM {table}')).scalar_one() == history
        assert conn.execute(text("SELECT count(*) FROM employees WHERE username='New'")).scalar_one() == 1


def test_unrecognized_json_history_stays_protected(database):
    row = setup(database)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE unknown_history(payload jsonb)'))
        conn.execute(text('INSERT INTO unknown_history VALUES(CAST(:payload AS jsonb))'),
                     {'payload': json.dumps({'owner': {'name': 'New'}, 'amount': 400})})
    with pytest.raises(HTTPException):
        with database.begin() as conn:
            reuse.prepare_reuse(conn, [row], 'new', norm, 'Admin')


def financial_history(database):
    payroll = [{'Tên Hệ thống': 'New', 'Họ và tên': 'Người cũ', 'Mã bản lưu': 'Kỳ cũ',
                'Tích lũy': 250000, 'Tiền Lương': 2000000, 'Số tiền thực nhận': 1750000}]
    savings = [{'Tên nhân viên': 'New', 'Đã tích lũy': 750000,
                '__sheet_header': ['Tên nhân viên', 'Đã tích lũy', 'Ghi chú'],
                '__raw_values': ['New', 750000, 'giữ nguyên']}]
    audit = {'ID': 'old-leave-event', 'Tên nhân viên': 'New', 'Phạt sau': 12345,
             'JSON trước': '{"Tên nhân viên":"New"}'}
    with database.begin() as conn:
        for table in ('vera_dataset_cache', 'vera_primary_dataset'):
            conn.execute(text(f'''CREATE TABLE {table}(dataset_key text PRIMARY KEY,payload jsonb,
                checksum text,row_count int,revision bigint,updated_at timestamptz)'''))
            for dataset, payload in [('payroll_history', payroll), ('tichluy', savings)]:
                conn.execute(text(f'INSERT INTO {table} VALUES(:key,CAST(:payload AS jsonb),\'original\',1,7,NOW())'),
                             {'key': dataset, 'payload': json.dumps(payload)})
        conn.execute(text('CREATE TABLE vera_phase16_record(dataset text,logical_id text,payload jsonb)'))
        conn.execute(text("INSERT INTO vera_phase16_record VALUES('leave_activity_log','old-leave-event',CAST(:payload AS jsonb))"), {'payload': json.dumps(audit)})
    return payroll, savings, audit


def test_reuse_archives_production_financial_shapes_without_transferring_balances(database, monkeypatch):
    from vera_staff_retired_history import CATEGORY, guard_legacy_snapshot, preserve_retired_audit
    from vera_web_v2_payroll_personal import _accumulation_balance
    from vera_web_v2_payroll import _visible
    from types import SimpleNamespace
    row = setup(database)
    payroll, savings, audit = financial_history(database)
    monkeypatch.setattr('vera_web_v2_local_auth.SESSION_STORE_TABLE', 'vera_app_setting')
    with database.begin() as conn:
        identity = reuse.prepare_reuse(conn, [row], 'new', norm, 'Admin')
        assert identity != local_auth_user_id('New')
        archive = conn.execute(text('SELECT value_json FROM vera_app_setting WHERE category=:category'), {'category': CATEGORY}).scalar_one()
        archived = archive['archived_username']
        assert len(archive['originals']) == 5
        assert archive['originals'][0]['rows'] == payroll
        assert archive['originals'][1]['rows'] == savings
        assert archive['originals'][-1]['rows'] == [audit]
        for table in ('vera_dataset_cache', 'vera_primary_dataset'):
            records = {r.dataset_key: r.payload for r in conn.execute(text(f'SELECT dataset_key,payload FROM {table}'))}
            old_payroll = records['payroll_history'][0]
            old_savings = records['tichluy'][0]
            assert old_payroll['Tên Hệ thống'] == archived
            assert old_payroll['Tiền Lương'] == 2000000 and old_payroll['Tích lũy'] == 250000
            assert old_savings['Tên nhân viên'] == old_savings['__raw_values'][0] == archived
            assert old_savings['__raw_values'][1:] == [750000, 'giữ nguyên']
            # Even a new employee with the old full name cannot see/inherit it.
            fresh = {'username': 'new', 'full_name': 'Người cũ'}
            balance = _accumulation_balance(fresh, records['payroll_history'], records['tichluy'], [], norm)
            assert balance['paid_total'] == 0 and not balance['periods']
            assert _visible(records['payroll_history'], SimpleNamespace(role='nhanvien', employee_username='new', full_name='Người cũ'), norm) == []
            old_balance = _accumulation_balance({'username': archived}, records['payroll_history'], records['tichluy'], [], norm)
            assert old_balance['paid_total'] == 750000
            assert conn.execute(text(f'SELECT min(revision) FROM {table}')).scalar_one() == 8
            assert conn.execute(text(f"SELECT count(*) FROM {table} WHERE row_count=1 AND checksum<>'original'")).scalar_one() == 2
        audit_after = conn.execute(text('SELECT payload FROM vera_phase16_record')).scalar_one()
        assert audit_after['Tên nhân viên'] == archived
        assert audit_after['Phạt sau'] == audit['Phạt sau'] and audit_after['JSON trước'] == audit['JSON trước']
        for dataset, payload in [('payroll_history', payroll), ('tichluy', savings)]:
            with pytest.raises(HTTPException) as exc:
                guard_legacy_snapshot(conn, dataset, payload)
            assert exc.value.status_code == 409
        normalized = [{'logical_id': 'old-leave-event', 'payload': json.dumps(audit)},
                      {'logical_id': 'new-leave-event', 'payload': json.dumps(audit)}]
        preserve_retired_audit(conn, 'leave_activity_log', normalized)
        assert json.loads(normalized[0]['payload'])['Tên nhân viên'] == archived
        assert json.loads(normalized[1]['payload'])['Tên nhân viên'] == 'New'


def test_unknown_reference_rolls_back_all_financial_archival(database):
    row = setup(database)
    payroll, savings, audit = financial_history(database)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE unknown_history(payload jsonb)'))
        conn.execute(text('INSERT INTO unknown_history VALUES(\'{"owner":"New"}\')'))
    with pytest.raises(HTTPException):
        with database.begin() as conn:
            reuse.prepare_reuse(conn, [row], 'new', norm, 'Admin')
    with database.connect() as conn:
        for table in ('vera_dataset_cache', 'vera_primary_dataset'):
            assert conn.execute(text(f"SELECT payload FROM {table} WHERE dataset_key='payroll_history'")).scalar_one() == payroll
            assert conn.execute(text(f"SELECT payload FROM {table} WHERE dataset_key='tichluy'")).scalar_one() == savings
            assert conn.execute(text(f'SELECT min(revision) FROM {table}')).scalar_one() == 7
        assert conn.execute(text('SELECT payload FROM vera_phase16_record')).scalar_one() == audit
        assert conn.execute(text("SELECT count(*) FROM vera_app_setting WHERE category='staff_retired_identity'")).scalar_one() == 0


def test_period_replacement_keeps_retired_saved_money():
    from datetime import date
    from vera_attendance_participation import preserved_payroll
    original = {'Tên Hệ thống': 'retired-old', '__retired_identity': 'retired-old', 'Tích lũy': 500000}
    assert preserved_payroll([original], date(2026, 10, 1), date(2026, 10, 15), key='Tên Hệ thống') == [original]

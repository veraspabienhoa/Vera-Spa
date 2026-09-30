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

from copy import deepcopy
import pytest
from vera_employee_rename_sync import rename_json
from vera_facegate_enrollment import FaceGateEnrollmentClient, EnrollmentError


def test_identity_fields_and_financial_history_without_touching_customer_service_or_aliases():
    source = {'employees': [{'id': 'e1', 'name': 'An', 'booking': {'customer_name': 'An', 'service': 'An'}}],
              'invoices': [{'id': 'bill', 'entries': [{'employee_id': 'e1', 'employee_name': 'An', 'tip': 123, 'price': 456}]}],
              'accounts': [{'target': 'An', 'feature': 'staff_list', 'allowed': True}],
              'roles': [{'target': 'An'}], '__previous_usernames': ['An'],
              '__sheet_header': ['Tên nhân viên', 'Khách hàng'], '__raw_values': ['An', 'An']}
    saved = deepcopy(source)
    result = rename_json(deepcopy(source), 'An', 'Gia An')
    assert source == saved
    assert result['employees'][0]['name'] == 'Gia An'
    assert result['employees'][0]['id'] == 'e1'
    assert result['employees'][0]['booking'] == source['employees'][0]['booking']
    assert result['invoices'][0]['entries'][0] == {'employee_id': 'e1', 'employee_name': 'Gia An', 'tip': 123, 'price': 456}
    assert result['accounts'][0]['target'] == 'Gia An'
    assert result['roles'] == source['roles']
    assert result['__previous_usernames'] == ['An']
    assert result['__raw_values'] == ['Gia An', 'An']


REF = {'file_type': 0, 'file_index': 2, 'file_position': 55}
PROFILE = {'uid': '42', 'uname': 'An', 'utext': 'vera:stable', 'dwfiletype': '0',
           'dwfileindex': '2', 'dwfilepos': '55', 'uAccessID': '7'}


def test_facegate_rename_preserves_face_token_access_and_uid(monkeypatch):
    monkeypatch.setattr('vera_facegate_control_log._facegate_config', lambda: ('http://192.168.1.2', '/webs/getControl', ('test', 'test')))
    client = FaceGateEnrollmentClient()
    state = deepcopy(PROFILE)
    requests = []
    monkeypatch.setattr(client, 'profile_details', lambda uid: dict(state))
    def request(path, params):
        requests.append((path, params))
        state['uname'] = params['LIST.uname']
        return 'root.ERR.no=0'
    monkeypatch.setattr(client, 'request', request)
    client.rename_profile(42, 'An', 'Gia An', REF)
    assert requests[0][1]['LIST.uid'] == '42'
    assert requests[0][1]['LIST.utext'] == 'vera:stable'
    assert requests[0][1]['LIST.dwfilepos'] == '55'
    assert requests[0][1]['LIST.uAccessID'] == '7'
    client.rename_profile(42, 'An', 'Gia An', REF)
    assert len(requests) == 1  # Read-before-retry after a lost response.
    client.close()


def test_facegate_wrong_reference_never_written(monkeypatch):
    monkeypatch.setattr('vera_facegate_control_log._facegate_config', lambda: ('http://192.168.1.2', '/webs/getControl', ('test', 'test')))
    client = FaceGateEnrollmentClient()
    monkeypatch.setattr(client, 'profile_details', lambda uid: deepcopy(PROFILE))
    monkeypatch.setattr(client, 'request', lambda *a: pytest.fail('unexpected write'))
    with pytest.raises(EnrollmentError):
        client.rename_profile(42, 'An', 'Gia An', {**REF, 'file_position': 99})
    client.close()


from test_live_tour_resource_postgres import database
from sqlalchemy import text
import vera_live_tour_resource_store as resource_store
from vera_employee_rename_sync import migrate_references


def test_postgres_atomic_reference_migration_preserves_employee_id_and_money(database):
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE rename_business(id integer PRIMARY KEY, employee_name text, payload jsonb, checksum text, revision bigint, updated_at timestamptz)'))
        conn.execute(text("INSERT INTO rename_business VALUES(1,'An',CAST(:payload AS jsonb),'original',1,NOW())"), {'payload': '{"employee_name":"An","amount":123,"customer_name":"An"}'})
        conn.execute(text('CREATE VIEW rename_business_view AS SELECT * FROM rename_business'))
        migrate_references(conn, 'An', 'Gia An', 'admin')
    with database.begin() as conn:
        state, revision, _ = resource_store.read(conn)
        assert state['employees'][0]['id'] == 'e1'
        assert state['employees'][0]['name'] == 'Gia An'
        assert revision == 8
        row = conn.execute(text('SELECT * FROM rename_business')).mappings().one()
        assert row['employee_name'] == 'Gia An'
        assert row['payload'] == {'employee_name': 'Gia An', 'amount': 123, 'customer_name': 'An'}
        assert row['revision'] == 2
        assert row['checksum'] != 'original'
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            migrate_references(conn, 'Gia An', 'Other', 'admin')
            raise RuntimeError('rollback')
    with database.begin() as conn:
        state, revision, _ = resource_store.read(conn)
        assert state['employees'][0]['name'] == 'Gia An'
        assert revision == 8
        assert conn.execute(text('SELECT employee_name FROM rename_business')).scalar() == 'Gia An'


def test_current_salary_map_owner_rename_preserves_rates_and_other_people():
    from vera_employee_rename_sync import rename_salary_map
    from fastapi import HTTPException
    before = {'an': {'rate_ca1': 27000}, 'Bình': {'rate_ca1': 31000}}
    assert rename_salary_map(before, 'An', 'Gia An') == {'Gia An': {'rate_ca1': 27000}, 'Bình': {'rate_ca1': 31000}}
    assert before['an'] == {'rate_ca1': 27000}
    assert rename_salary_map({'An':'attendance'}, 'An', 'Gia An') == {'Gia An':'attendance'}
    with pytest.raises(HTTPException) as error:
        rename_salary_map({'An':'attendance','Gia An':'schedule'}, 'An', 'Gia An')
    assert error.value.status_code == 409


@pytest.mark.parametrize('target_value', ['attendance', {'rate_ca1': 31000}])
def test_rename_without_old_salary_override_cannot_inherit_occupied_target(target_value):
    from vera_employee_rename_sync import rename_salary_map
    from fastapi import HTTPException
    before = {'gIa aN': target_value}
    with pytest.raises(HTTPException) as error:
        rename_salary_map(before, 'An', 'Gia An')
    assert error.value.status_code == 409
    assert before == {'gIa aN': target_value}


def test_postgres_salary_source_and_rate_keys_follow_rename_atomically(database):
    import json
    with database.begin() as conn:
        for key, value in [('department_employee_salary_configs', {'an':{'rate_ca1':27000}}),
                           ('department_employee_salary_sources', {'An':'attendance','Bình':'schedule'})]:
            conn.execute(text("INSERT INTO vera_app_setting VALUES ('payroll',:key,CAST(:value AS jsonb),3,NOW())"), {'key':key,'value':json.dumps(value)})
        migrate_references(conn, 'An', 'Gia An', 'admin')
    with database.connect() as conn:
        settings = {row['setting_key']:row for row in conn.execute(text("SELECT * FROM vera_app_setting WHERE category='payroll'")).mappings()}
        assert settings['department_employee_salary_configs']['value_json'] == {'Gia An':{'rate_ca1':27000}}
        assert settings['department_employee_salary_sources']['value_json'] == {'Gia An':'attendance','Bình':'schedule'}
        assert all(row['revision'] == 4 for row in settings.values())
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            migrate_references(conn, 'Gia An', 'Other', 'admin')
            raise RuntimeError('rollback')
    with database.connect() as conn:
        assert conn.execute(text("SELECT value_json FROM vera_app_setting WHERE setting_key='department_employee_salary_sources'")).scalar()['Gia An'] == 'attendance'


def test_postgres_source_only_rename_invalidates_configuration_revision(database):
    from vera_employee_rename_sync import migrate_salary_maps
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_app_setting VALUES ('payroll','department_employee_salary_sources','{\"An\":\"attendance\"}',2,NOW())"))
        assert migrate_salary_maps(conn, 'An', 'Gia An') == 1
        result = conn.execute(text("SELECT revision,value_json FROM vera_app_setting WHERE setting_key='department_employee_salary_configs'")).mappings().one()
        assert result['revision'] == 1 and result['value_json'] == {}

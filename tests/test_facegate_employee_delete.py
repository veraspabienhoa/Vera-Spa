import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text

from vera_facegate_enrollment import FaceGateEnrollmentClient, EnrollmentError
from vera_employee_facegate_delete import queue_employee_delete, sync_employee_deletions
from test_live_tour_resource_postgres import database

REF = {'file_type': 0, 'file_index': 2, 'file_position': 55}
PROFILE = {'uid': '42', 'uname': 'An', 'utext': 'vera:old',
           'dwfiletype': '0', 'dwfileindex': '2', 'dwfilepos': '55'}


class Device:
    delete_profile = FaceGateEnrollmentClient.delete_profile
    def __init__(self, profile=None):
        self.rows = [dict(PROFILE if profile is None else profile)]
        self.calls = []
        self.lost = False
        self.ignore = False
    def profiles(self): return [dict(p) for p in self.rows]
    def profile_details(self, uid): return dict(self.rows[0])
    def request(self, path, params):
        self.calls.append((path, params))
        if not self.ignore:
            self.rows = []
        if self.lost:
            self.lost = False
            raise TimeoutError('lost delete reply')
        return 'root.ERR.no=0'
    def login(self): pass
    def close(self): pass


def test_delete_exact_profile_and_read_back_absence():
    device = Device()
    device.delete_profile(42, 'An', REF)
    assert device.rows == []
    assert device.calls == [('/webs/setWhitelist', {'action': 'del', 'group': 'LIST', 'LIST.uid': '42'})]
    device.delete_profile(42, 'An', REF)
    assert len(device.calls) == 1


@pytest.mark.parametrize('change', [{'uname': 'Other'}, {'dwfilepos': '56'}, {'uid': '43'}])
def test_reused_uid_or_moved_face_never_deletes_someone_else(change):
    device = Device({**PROFILE, **change})
    with pytest.raises(EnrollmentError):
        device.delete_profile(42, 'An', REF)
    assert device.calls == []


def test_success_reply_with_profile_remaining_is_unverified():
    device = Device()
    device.ignore = True
    with pytest.raises(EnrollmentError) as exc:
        device.delete_profile(42, 'An', REF)
    assert exc.value.code == 'unverified'


def setup(database, monkeypatch):
    import vera_web_v2_facegate_enrollment as enrollment
    import vera_facegate_control_log as protocol
    monkeypatch.setattr(protocol, 'mapping_device_id', lambda: 'test-device')
    monkeypatch.setattr(enrollment, 'target', lambda conn: '192.168.1.34')
    mapping = {'username': 'An', 'profile_id': 42, 'device_name': 'An',
               'confirmed_by': 'admin', 'device_address': '192.168.1.34', 'registration_ref': REF}
    with database.begin() as conn:
        schema = conn.execute(text('SELECT current_schema()')).scalar()
        conn.execute(text("INSERT INTO employees(username,full_name) VALUES('An','Original person')"))
        conn.execute(text("INSERT INTO vera_app_setting VALUES('facegate','mapping_test-device',CAST(:mapping AS jsonb),1,NOW())"), {'mapping': json.dumps([mapping])})
    return schema


def test_delete_job_rolls_back_with_directory_transaction(database, monkeypatch):
    setup(database, monkeypatch)
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            assert queue_employee_delete(conn, 'An')
            conn.execute(text("DELETE FROM employees WHERE username='An'"))
            raise RuntimeError('directory deletion failed')
    with database.begin() as conn:
        assert conn.execute(text("SELECT to_regclass('vera_facegate_delete_job')")).scalar() is None
        assert conn.execute(text("SELECT count(*) FROM employees WHERE username='An'")).scalar() == 1


def test_offline_lost_reply_one_connection_and_same_name_reuse(database, monkeypatch):
    import vera_facegate_enrollment as protocol
    import vera_web_v2_facegate_enrollment as enrollment
    schema = setup(database, monkeypatch)
    with database.begin() as conn:
        queue_employee_delete(conn, 'An')
        conn.execute(text("DELETE FROM employees WHERE username='An'"))
        # New person with the same account name must not inherit the old face.
        conn.execute(text("INSERT INTO employees(username,full_name) VALUES('An','New person')"))
    engine = create_engine(database.url, pool_size=1, max_overflow=0, pool_timeout=.2,
                           connect_args={'options': '-csearch_path=' + schema})
    connections = []
    @event.listens_for(engine, 'checkout')
    def checkout(dbapi, record, proxy): connections[:] = [dbapi]
    device = Device()
    device.lost = True
    offline = [True]
    class Client(Device):
        def login(self):
            assert engine.pool.checkedout() == 1
            assert connections[0].info.transaction_status.name == 'IDLE'
            if offline[0]:
                offline[0] = False
                raise TimeoutError()
        def profiles(self):
            assert connections[0].info.transaction_status.name == 'IDLE'
            return device.profiles()
        def profile_details(self, uid):
            assert connections[0].info.transaction_status.name == 'IDLE'
            return device.profile_details(uid)
        def request(self, path, params):
            assert connections[0].info.transaction_status.name == 'IDLE'
            return device.request(path, params)
    monkeypatch.setattr(protocol, 'FaceGateEnrollmentClient', Client)
    try:
        assert sync_employee_deletions(engine)['status'] == 'pending'
        assert device.calls == []
        assert sync_employee_deletions(engine)['status'] == 'pending'
        assert len(device.calls) == 1
        assert sync_employee_deletions(engine)['status'] == 'verified'
        assert len(device.calls) == 1
        with engine.begin() as conn:
            assert enrollment.mappings(conn, 'test-device') == []
            assert conn.execute(text("SELECT full_name FROM employees WHERE username='An'")).scalar() == 'New person'
            row = conn.execute(text('SELECT status,attempts FROM vera_facegate_delete_job')).one()
            assert row == ('verified', 2)
    finally:
        engine.dispose()


def test_ambiguous_mapping_rejects_before_directory_delete(database, monkeypatch):
    setup(database, monkeypatch)
    with database.begin() as conn:
        conn.execute(text("UPDATE vera_app_setting SET value_json=value_json || value_json WHERE category='facegate'"))
    with pytest.raises(HTTPException) as exc:
        with database.begin() as conn:
            queue_employee_delete(conn, 'An')
    assert exc.value.status_code == 409


def test_worker_failure_does_not_block_attendance(monkeypatch, capsys):
    import vera_facegate_auto_sync as worker
    import vera_facegate_cutover as cutover
    import vera_employee_facegate_delete as deletion
    disposed = []
    monkeypatch.setattr(cutover, 'runtime_engine', lambda: SimpleNamespace(dispose=lambda: disposed.append(True)))
    def failure(engine): raise RuntimeError('private credentials')
    monkeypatch.setattr(deletion, 'sync_employee_deletions', failure)
    worker.sync_employee_deletions()
    assert json.loads(capsys.readouterr().out) == {'employee_delete_sync': 'pending', 'error_type': 'RuntimeError'}
    assert disposed == [True]


def test_directory_route_queues_before_commit_and_reports_pending(database, monkeypatch):
    from inspect import signature
    from zoneinfo import ZoneInfo
    from fastapi import FastAPI
    import vera_web_v2_staff as staff
    import vera_employee_facegate_delete as deletion
    from vera_web_v2_face_id import ensure_table
    setup(database, monkeypatch)
    with database.begin() as conn:
        conn.execute(text('ALTER TABLE employees ADD COLUMN role text DEFAULT \'nhanvien\', ADD COLUMN payload jsonb DEFAULT \'{}\', ADD COLUMN stt integer, ADD COLUMN updated_at timestamptz'))
        ensure_table(conn)
        conn.execute(text("INSERT INTO vera_employee_face_id VALUES('An',:content,'image/png',3,'hash','admin',NOW())"), {'content': b'old'})
        conn.execute(text("INSERT INTO vera_face_id_self_update VALUES('An',true)"))
    monkeypatch.setattr(staff, '_select_staff_rows', lambda conn, **kwargs: [dict(r) for r in conn.execute(text('SELECT username,role,payload FROM employees ORDER BY username')).mappings()])
    monkeypatch.setattr(staff, 'revoke_local_sessions', lambda conn, username, reason: None)
    def sync(engine):
        assert engine.pool.checkedout() == 0
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM employees WHERE username='An'")).scalar() == 0
            assert conn.execute(text('SELECT count(*) FROM vera_employee_face_id')).scalar() == 0
            assert conn.execute(text('SELECT count(*) FROM vera_face_id_self_update')).scalar() == 0
            assert conn.execute(text('SELECT count(*) FROM vera_facegate_delete_job')).scalar() == 1
            assert conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='facegate'")).scalar() == []
        return {'status': 'pending'}
    monkeypatch.setattr(deletion, 'sync_employee_deletions', sync)
    app = FastAPI()
    dependencies = {name: (lambda *args, **kwargs: None) for name in signature(staff.install_staff_routes).parameters if name != 'app'}
    dependencies.update(engine_instance=lambda: database, norm=lambda x: str(x).casefold(),
                        identity_type=object, vn_tz=ZoneInfo('Asia/Ho_Chi_Minh'), leave_sheet_id='')
    staff.install_staff_routes(app, **dependencies)
    endpoint = next(r.endpoint for r in app.routes if r.path == '/v2/staff' and 'DELETE' in r.methods)
    result = endpoint(staff.StaffDelete(usernames=['An']), SimpleNamespace(role='admin', employee_username='admin'))
    assert result['ok'] and result['deleted'] == 1
    assert result['face_id_sync']['status'] == 'pending'
    assert 'chờ xác minh' in result['message']


def test_busy_enrollment_blocks_deletion_transaction(database, monkeypatch):
    setup(database, monkeypatch)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE vera_facegate_enrollment(status text)'))
        conn.execute(text("INSERT INTO vera_facegate_enrollment VALUES('unverified')"))
    with pytest.raises(HTTPException) as exc:
        with database.begin() as conn:
            queue_employee_delete(conn, 'An')
    assert exc.value.status_code == 409
    with database.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM employees WHERE username='An'")).scalar() == 1


def test_wrong_device_address_keeps_profile_pending_without_network(database, monkeypatch):
    import vera_facegate_enrollment as protocol
    import vera_web_v2_facegate_enrollment as enrollment
    setup(database, monkeypatch)
    with database.begin() as conn:
        queue_employee_delete(conn, 'An')
    monkeypatch.setattr(enrollment, 'target', lambda conn: '192.168.1.35')
    monkeypatch.setattr(protocol, 'FaceGateEnrollmentClient', lambda: pytest.fail('Must not connect to a changed device'))
    assert sync_employee_deletions(database)['status'] == 'pending'

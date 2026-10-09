import json
from types import SimpleNamespace

import pytest
from vera_facegate_enrollment import validate_device_name, EnrollmentError
import vera_facegate_auto_sync as auto_sync


@pytest.mark.parametrize('name', ['Assistant', 'Gia Anh', 'Đỗ An', 'A' * 47])
def test_device_name_accepts_existing_firmware_limits(name):
    assert validate_device_name(name) == name


@pytest.mark.parametrize('name', ['', 'A' * 48, 'Đ' * 16, 'A\x00B', 'A\nB'])
def test_device_name_rejects_unrepresentable_names(name):
    with pytest.raises(EnrollmentError):
        validate_device_name(name)


def test_active_facegate_schedule_retries_names_before_archive_even_if_archive_fails(monkeypatch, tmp_path):
    import vera_facegate_cutover as cutover
    import vera_employee_rename_sync as rename
    engine = SimpleNamespace(dispose=lambda: events.append('dispose'))
    events = []
    monkeypatch.setattr(cutover, 'runtime_engine', lambda: engine)
    outcomes = iter([{'status': 'pending'}, {'status': 'verified'}])
    monkeypatch.setattr(rename, 'sync_device_names', lambda e: events.append('names') or next(outcomes))
    monkeypatch.setattr(auto_sync, 'sync_employee_deletions', lambda: events.append('deletions'))
    monkeypatch.setattr(auto_sync, 'archive_days', lambda: events.append('archive') or 1)
    original_open = auto_sync.os.open
    monkeypatch.setattr(auto_sync.os, 'open', lambda path, flags, mode: original_open(str(tmp_path / 'lock'), flags, mode))
    assert auto_sync.main() == auto_sync.main() == 1
    assert events == ['deletions', 'names', 'dispose', 'archive'] * 2


def test_name_retry_failure_does_not_stop_attendance_or_expose_exception_message(monkeypatch, capsys):
    import vera_facegate_cutover as cutover
    import vera_employee_rename_sync as rename
    disposed = []
    engine = SimpleNamespace(dispose=lambda: disposed.append(True))
    monkeypatch.setattr(cutover, 'runtime_engine', lambda: engine)
    def failure(e):
        raise RuntimeError('private credential payload')
    monkeypatch.setattr(rename, 'sync_device_names', failure)
    auto_sync.sync_employee_names()
    result = json.loads(capsys.readouterr().out)
    assert result == {'employee_name_sync': 'pending', 'error_type': 'RuntimeError'}
    assert disposed == [True]


from test_live_tour_resource_postgres import database
from sqlalchemy import create_engine, event, text
from vera_employee_rename_sync import queue_device_rename, sync_device_names
from vera_facegate_enrollment import FaceGateEnrollmentClient


def test_postgres_offline_then_lost_response_recovers_once_with_one_connection(database, monkeypatch):
    import vera_web_v2_facegate_enrollment as enrollment
    import vera_facegate_control_log as device
    import vera_facegate_enrollment as protocol
    ref = {'file_type': 0, 'file_index': 2, 'file_position': 55}
    mapping = {'username': 'An', 'profile_id': 42, 'device_name': 'An',
               'confirmed_by': 'admin', 'device_address': '192.168.1.34', 'registration_ref': ref}
    monkeypatch.setattr(device, 'mapping_device_id', lambda: 'test-device')
    monkeypatch.setattr(enrollment, 'target', lambda conn: '192.168.1.34')
    with database.begin() as conn:
        schema = conn.execute(text('SELECT current_schema()')).scalar()
        conn.execute(text("INSERT INTO vera_app_setting VALUES('facegate','mapping_test-device',CAST(:mapping AS jsonb),1,NOW())"), {'mapping': json.dumps([mapping])})
        queue_device_rename(conn, 'An', 'Gia An')
        mapping['username'] = 'Gia An'
        conn.execute(text("UPDATE vera_app_setting SET value_json=CAST(:mapping AS jsonb) WHERE category='facegate'"), {'mapping': json.dumps([mapping])})
    engine = create_engine(database.url, pool_size=1, max_overflow=0, pool_timeout=.2,
                           connect_args={'options': '-csearch_path=' + schema})
    checked_out = []
    @event.listens_for(engine, 'checkout')
    def checkout(dbapi, record, proxy):
        checked_out[:] = [dbapi]
    profile = {'uid': '42', 'uname': 'An', 'utext': 'stable-token',
               'dwfiletype': '0', 'dwfileindex': '2', 'dwfilepos': '55', 'uAccessID': '7'}
    calls = []
    offline = [True]
    class Client:
        rename_profile = FaceGateEnrollmentClient.rename_profile
        def assert_network_boundary(self):
            assert engine.pool.checkedout() == 1
            assert checked_out[0].info.transaction_status.name == 'IDLE'
        def login(self):
            self.assert_network_boundary()
            if offline[0]:
                offline[0] = False
                raise TimeoutError()
        def profile_details(self, uid):
            self.assert_network_boundary()
            assert uid == 42
            return dict(profile)
        def request(self, path, params):
            self.assert_network_boundary()
            calls.append(params)
            profile['uname'] = params['LIST.uname']
            raise TimeoutError('write completed, reply lost')
        def close(self): pass
    monkeypatch.setattr(protocol, 'FaceGateEnrollmentClient', Client)
    try:
        assert sync_device_names(engine, 'Gia An')['status'] == 'pending'  # Offline.
        assert calls == []
        assert sync_device_names(engine, 'Gia An')['status'] == 'pending'  # Lost reply.
        assert len(calls) == 1
        assert sync_device_names(engine, 'Gia An')['status'] == 'verified'  # Read-back, no second write.
        assert len(calls) == 1
        with engine.begin() as conn:
            saved = enrollment.mappings(conn, 'test-device')[0]
            job = conn.execute(text('SELECT * FROM vera_facegate_rename_job')).mappings().one()
        assert saved['device_name'] == 'Gia An' and saved['profile_id'] == 42 and saved['registration_ref'] == ref
        assert job['status'] == 'verified' and job['attempts'] == 2
        assert profile['utext'] == 'stable-token' and profile['uAccessID'] == '7'
        assert calls[0]['LIST.dwfilepos'] == '55'
    finally:
        engine.dispose()

"""Failure injection for the maintenance boundary; no real service changes."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import vera_live_tour_maintenance as maintenance
import vera_web_v2_runtime_env as runtime


def settings():
    return dict(VERA_DB_ENABLED='1', VERA_DATA_BACKEND='postgres', DB_HOST='db.invalid',
                DB_PORT='5432', DB_NAME='vera', DB_USER='user', DB_PASS='test-only',
                DB_SSLMODE='require', DB_CONNECT_TIMEOUT='10', VERA_AUTH_PROVIDER='local')


@pytest.mark.parametrize('mode', [None, 'active', 'shadow', 'off', 'verify'])
def test_managed_mode_is_optional_and_loaded_atomically(tmp_path, monkeypatch, mode):
    values = settings()
    for key in values:
        monkeypatch.setenv(key, runtime.os.environ.get(key, ""))
    if mode is not None:
        values[maintenance.MODE_KEY] = mode
    monkeypatch.setattr(runtime, '_read_private_file', lambda path: '\n'.join(f'{k}={v}' for k, v in values.items()))
    monkeypatch.setenv(maintenance.MODE_KEY, 'shadow')
    assert runtime.load_managed_runtime_environment()
    assert runtime.os.environ[maintenance.MODE_KEY] == (mode or 'shadow')


@pytest.mark.parametrize('bad', ['activate', '', 'ACTIVE', 'shadow active'])
def test_invalid_managed_mode_does_not_partially_change_environment(monkeypatch, bad):
    values = {**settings(), maintenance.MODE_KEY: bad}
    monkeypatch.setattr(runtime, '_read_private_file', lambda path: '\n'.join(f'{k}="{v}"' for k, v in values.items()))
    monkeypatch.setenv('DB_HOST', 'original')
    with pytest.raises(RuntimeError):
        runtime.load_managed_runtime_environment()
    assert runtime.os.environ['DB_HOST'] == 'original'


def test_mode_change_preserves_private_configuration_and_replaces_old_flag(tmp_path):
    original = 'DB_PASS="secret with spaces"\n# note\nVERA_LIVE_TOUR_RELATIONAL_MODE=shadow\n'
    updated = maintenance.mode_configuration(original, 'active')
    assert 'DB_PASS="secret with spaces"' in updated
    assert updated.count(maintenance.MODE_KEY) == 1
    path = tmp_path / 'runtime.env'
    maintenance.write_private(path, updated)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_text() == updated


@pytest.fixture
def transition_context(tmp_path, monkeypatch):
    events = []
    monkeypatch.setenv(maintenance.MODE_KEY, "shadow")
    conn = SimpleNamespace(invalidated=False, closed=False, rollback=lambda: events.append('rollback_transaction'))
    service = SimpleNamespace(start=lambda: events.append('start'), stop=lambda: events.append('stop'),
                              verify_release=lambda: events.append('verify_release'))
    path = tmp_path / 'runtime.env'
    path.write_text('old config')
    monkeypatch.setattr(maintenance, 'api_processes', lambda: [object()])
    monkeypatch.setattr(maintenance, 'verify_fences', lambda conn: events.append('verify_fences'))
    monkeypatch.setattr(maintenance, 'migrate', lambda conn, rollback: events.append(('migrate', rollback)) or {'revision': 42})
    monkeypatch.setattr(maintenance, 'health', lambda mode, attempts: events.append(('health', mode)))
    return conn, service, path, events


def invoke(context):
    conn, service, path, _ = context
    return maintenance.transition(conn, service, path, 'old config', 'shadow', 'active', path.parent)


def test_success_checks_new_runtime_before_returning(transition_context):
    assert invoke(transition_context) == {'ok': True, 'mode': 'active', 'revision': 42}
    _, _, path, events = transition_context
    assert events == [('migrate', False), 'start', ('health', 'active'), 'verify_release', 'verify_fences']
    assert path.read_text().endswith('VERA_LIVE_TOUR_RELATIONAL_MODE=active\n')


def test_unhealthy_new_api_is_stopped_before_export_back(transition_context, monkeypatch):
    _, _, path, events = transition_context
    def health(mode, attempts):
        events.append(('health', mode))
        if mode == 'active':
            raise OSError('failed')
    monkeypatch.setattr(maintenance, 'health', health)
    with pytest.raises(RuntimeError, match='previous mode and current data restored'):
        invoke(transition_context)
    assert events.index('stop') < events.index(('migrate', True)) < events.index(('health', 'shadow'))
    assert path.read_text() == 'old config'
    assert json.loads((path.parent / 'phase.json').read_text())['phase'] == 'recovered'


def test_start_error_may_have_started_process_so_recovery_stops_it(transition_context):
    _, service, _, events = transition_context
    def start():
        events.append('start')
        if events.count('start') == 1:
            raise RuntimeError('start response lost')
    service.start = start
    with pytest.raises(RuntimeError, match='previous mode and current data restored'):
        invoke(transition_context)
    assert events.index('stop') < events.index(('migrate', True))


def test_failed_transaction_does_not_export_uncommitted_data(transition_context, monkeypatch):
    _, _, path, events = transition_context
    monkeypatch.setattr(maintenance, 'migrate', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('parity failed')))
    with pytest.raises(RuntimeError, match='previous mode and current data restored'):
        invoke(transition_context)
    assert not any(isinstance(event, tuple) and event[0] == 'migrate' for event in events)
    assert path.read_text() == 'old config'


def test_lost_database_fence_never_restarts_a_writer(transition_context, monkeypatch):
    conn, service, _, events = transition_context
    def health(mode, attempts):
        conn.invalidated = True
        raise OSError('lost database')
    monkeypatch.setattr(maintenance, 'health', health)
    with pytest.raises(RuntimeError, match='automatic recovery incomplete'):
        invoke(transition_context)
    assert events.count('start') == 1
    assert events.count('stop') >= 1
    assert ('migrate', True) not in events


def test_rollback_failure_keeps_service_stopped(transition_context, monkeypatch):
    _, _, _, events = transition_context
    def migrate(conn, rollback):
        events.append(('migrate', rollback))
        if rollback:
            raise ValueError('restore failure')
        return {'revision': 42}
    monkeypatch.setattr(maintenance, 'migrate', migrate)
    monkeypatch.setattr(maintenance, 'health', lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))
    with pytest.raises(RuntimeError, match='automatic recovery incomplete'):
        invoke(transition_context)
    assert events[-1] == 'stop' and events.count('start') == 1


def test_subprocess_error_never_exposes_captured_credentials(monkeypatch):
    monkeypatch.setattr(maintenance.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr=b'password=secret'))
    with pytest.raises(RuntimeError) as exc:
        maintenance.command(['pg_dump'])
    assert 'secret' not in str(exc.value)


@pytest.mark.parametrize('managed_mode,initial_mode,expected', [(None, None, 'shadow'), (None, 'active', 'active'), ('active', 'shadow', 'active')])
def test_schema_cli_uses_api_mode_instead_of_ssh_flag(monkeypatch, managed_mode, initial_mode, expected):
    import vera_vps_concurrency_schema as schema
    monkeypatch.setenv(maintenance.MODE_KEY, 'verify')
    for key, value in settings().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(schema, '_running_api_environment', lambda: {maintenance.MODE_KEY: initial_mode} if initial_mode else {})
    def load():
        if managed_mode:
            runtime.os.environ[maintenance.MODE_KEY] = managed_mode
        return True
    monkeypatch.setattr(schema, 'load_managed_runtime_environment', load)
    monkeypatch.setattr(schema, 'create_engine', lambda *args, **kwargs: object())
    schema._runtime_engine()
    assert runtime.os.environ[maintenance.MODE_KEY] == expected


@pytest.mark.parametrize('mode,ready,expected,passes', [
    ('shadow', False, 'shadow', True), ('active', True, 'active', True),
    ('shadow', True, 'shadow', False), ('active', False, 'active', False),
    ('shadow', False, 'active', False), ('active', None, 'active', False),
])
def test_runtime_health_requires_mode_and_database_agreement(monkeypatch, mode, ready, expected, passes):
    from io import BytesIO
    def response(url, timeout):
        payload = {'ok': True, 'provider': 'postgres-local'} if url.endswith('auth/health') else {
            'ok': True, 'live_tour_relational_mode': mode, 'live_tour_storage_ready': ready,
        }
        return BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(maintenance.urllib.request, 'urlopen', response)
    if passes:
        assert maintenance.health(expected) == expected
    else:
        with pytest.raises(maintenance.MaintenanceError):
            maintenance.health(expected)


def process_environment(tmp_path, values, pid='100'):
    proc = tmp_path / pid
    proc.mkdir()
    (proc / 'environ').write_bytes(b'\0'.join(f'{k}={v}'.encode() for k, v in values.items()))
    return (proc, tmp_path, '')


def test_process_settings_ignore_ssh_secrets_and_unrelated_keys(tmp_path, monkeypatch):
    values = {**settings(), 'UNRELATED_SECRET': 'never-copy'}
    proc = process_environment(tmp_path, values)
    monkeypatch.setattr(maintenance, 'load_managed_runtime_environment', lambda: False)
    monkeypatch.setattr(maintenance, 'api_processes', lambda: [proc])
    monkeypatch.setenv('DB_HOST', 'wrong-shell-host')
    assert maintenance.runtime_settings() == settings()


def test_process_settings_reject_disagreeing_workers(tmp_path, monkeypatch):
    processes = [process_environment(tmp_path, settings()),
                 process_environment(tmp_path, {**settings(), 'DB_HOST': 'other'}, '101')]
    monkeypatch.setattr(maintenance, 'load_managed_runtime_environment', lambda: False)
    monkeypatch.setattr(maintenance, 'api_processes', lambda: processes)
    with pytest.raises(maintenance.MaintenanceError, match='inconsistent'):
        maintenance.runtime_settings()


def test_missing_process_password_never_falls_back_to_shell(tmp_path, monkeypatch):
    values = settings()
    del values['DB_PASS']
    proc = process_environment(tmp_path, values)
    monkeypatch.setattr(maintenance, 'load_managed_runtime_environment', lambda: False)
    monkeypatch.setattr(maintenance, 'api_processes', lambda: [proc])
    monkeypatch.setenv('DB_PASS', 'shell-password')
    with pytest.raises(RuntimeError, match='missing database settings'):
        maintenance.runtime_settings()


def test_optional_mode_override_preserves_systemd_database(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_dir=str(tmp_path)))
    monkeypatch.setenv('DB_HOST', 'systemd-host')
    monkeypatch.setenv(maintenance.MODE_KEY, 'shadow')
    assert not runtime.load_managed_runtime_environment()
    assert not runtime.load_live_tour_mode_override()
    path = tmp_path / runtime.LIVE_TOUR_MODE_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    maintenance.write_private(path, maintenance.MODE_KEY + '=active\n')
    assert runtime.load_live_tour_mode_override()
    assert runtime.os.environ[maintenance.MODE_KEY] == 'active'
    assert runtime.os.environ['DB_HOST'] == 'systemd-host'


@pytest.mark.parametrize('content', [
    'DB_HOST=other\n', 'VERA_LIVE_TOUR_RELATIONAL_MODE=wrong\n',
    'VERA_LIVE_TOUR_RELATIONAL_MODE=active\nVERA_LIVE_TOUR_RELATIONAL_MODE=shadow\n',
])
def test_mode_override_rejects_invalid_content_atomically(tmp_path, monkeypatch, content):
    monkeypatch.setattr(runtime.pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_dir=str(tmp_path)))
    monkeypatch.setenv(maintenance.MODE_KEY, 'shadow')
    path = tmp_path / runtime.LIVE_TOUR_MODE_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    maintenance.write_private(path, content)
    with pytest.raises(RuntimeError, match='invalid'):
        runtime.load_live_tour_mode_override()
    assert runtime.os.environ[maintenance.MODE_KEY] == 'shadow'


def test_new_override_removed_on_failed_activation(transition_context, monkeypatch):
    conn, service, path, events = transition_context
    path.unlink()
    def health(mode, attempts):
        if mode == 'active':
            raise OSError('unhealthy')
        assert not path.exists()
    monkeypatch.setattr(maintenance, 'health', health)
    with pytest.raises(maintenance.MaintenanceError, match='previous mode'):
        maintenance.transition(conn, service, path, None, 'shadow', 'active', path.parent)
    assert not path.exists()
    assert ('migrate', True) in events


def test_new_override_created_only_after_migration(transition_context, monkeypatch):
    conn, service, path, events = transition_context
    path.unlink()
    def migrate(conn, rollback):
        assert not path.exists()
        return {'revision': 42}
    monkeypatch.setattr(maintenance, 'migrate', migrate)
    assert maintenance.transition(conn, service, path, None, 'shadow', 'active', path.parent)['ok']
    assert path.read_text().strip() == maintenance.MODE_KEY + '=active'
    assert path.stat().st_mode & 0o777 == 0o600


def test_status_works_without_managed_file_and_never_changes_service(tmp_path, monkeypatch):
    from contextlib import nullcontext
    proc = process_environment(tmp_path, settings())
    monkeypatch.setattr(maintenance, 'load_managed_runtime_environment', lambda: False)
    monkeypatch.setattr(maintenance, 'api_processes', lambda: [proc])
    monkeypatch.setattr(maintenance, 'Service', lambda sha: object())
    monkeypatch.setattr(maintenance, 'activation_preflight', lambda service: {'ok': True})
    monkeypatch.setattr(maintenance, 'health', lambda: 'shadow')
    monkeypatch.setattr(maintenance.relational, 'resource_ready', lambda conn: False)
    conn = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(maintenance, 'create_engine', lambda *a, **kw:
                        SimpleNamespace(connect=lambda: nullcontext(conn)))
    monkeypatch.setattr(maintenance, 'write_private', lambda *a: pytest.fail('status wrote configuration'))
    assert maintenance._run('status', 'a' * 40) == {
        'ok': True, 'mode': 'shadow', 'resource_ready': False, 'changed': False,
        'activation_preflight': {'ok': True},
    }


def test_schema_cli_honors_separate_override(monkeypatch):
    import vera_vps_concurrency_schema as schema
    monkeypatch.setattr(schema, '_running_api_environment', lambda: settings())
    monkeypatch.setattr(schema, 'load_managed_runtime_environment', lambda: False)
    monkeypatch.setattr(schema, 'load_live_tour_mode_override',
                        lambda: monkeypatch.setenv(maintenance.MODE_KEY, 'active'))
    monkeypatch.setattr(schema, 'create_engine', lambda *a, **kw: object())
    schema._runtime_engine()
    assert runtime.os.environ[maintenance.MODE_KEY] == 'active'


def test_sudo_check_failure_identifies_exact_command_without_stderr(monkeypatch):
    service = maintenance.Service.__new__(maintenance.Service)
    service.scope, service.unit = 'system', 'vera-api.service'
    service.ctl = ['/usr/bin/systemctl']
    monkeypatch.setattr(maintenance.os, 'getuid', lambda: 1000)
    monkeypatch.setattr(maintenance, 'command', lambda *a, **kw:
                        (_ for _ in ()).throw(maintenance.MaintenanceError('secret stderr')))
    with pytest.raises(maintenance.MaintenanceError) as exc:
        service.authorize()
    assert '/usr/bin/systemctl stop vera-api.service' in str(exc.value)
    assert 'secret' not in str(exc.value)


def test_preflight_reports_all_missing_requirements_without_stopping(monkeypatch):
    service = SimpleNamespace(unit='vera-api.service', scope='system',
        authorize=lambda: (_ for _ in ()).throw(maintenance.MaintenanceError('sudo check failed')))
    monkeypatch.setattr(maintenance.shutil, 'which', lambda binary: None)
    monkeypatch.setenv('DB_PORT', '6543')
    result = maintenance.activation_preflight(service)
    assert not result['ok']
    assert len(result['errors']) == 4
    assert result['service'] == 'vera-api.service'


def test_authorization_checks_both_actions_without_running_them(monkeypatch):
    service = maintenance.Service.__new__(maintenance.Service)
    service.scope, service.unit = 'system', 'vera-api.service'
    service.ctl = ['/usr/bin/systemctl']
    calls = []
    monkeypatch.setattr(maintenance.os, 'getuid', lambda: 1000)
    monkeypatch.setattr(maintenance, 'command', lambda args: calls.append(args))
    service.authorize()
    assert calls == [ ['sudo', '-n', '-l', '/usr/bin/systemctl', action, 'vera-api.service']
                     for action in ('stop', 'start') ]


@pytest.mark.parametrize('missing', [None, 'definition', 'data', 'empty'])
def test_cutover_backup_excludes_scheduler_but_requires_board_data(tmp_path, monkeypatch, missing):
    for key, value in settings().items():
        monkeypatch.setenv(key, value)
    required = {'vera_app_setting', maintenance.relational.META_TABLE,
                maintenance.relational.MUTATION_TABLE, maintenance.relational.CLAIM_TABLE,
                *maintenance.relational.RESOURCE_TABLES.values()}
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[0] == 'pg_dump':
            assert '--exclude-schema=cron' in args
            assert '--exclude-extension=pg_cron' in args
            assert '--schema-only' not in args and '--enable-row-security' not in args
            assert settings()['DB_PASS'] not in args
            assert kwargs['env']['PGPASSWORD'] == settings()['DB_PASS']
            (tmp_path / 'database.dump').write_bytes(b'' if missing == 'empty' else b'archive')
            return ''
        lines = []
        for name in sorted(required):
            if not (missing == 'definition' and name == 'vera_app_setting'):
                lines.append(f'1; 1259 123 TABLE public {name} owner')
            if not (missing == 'data' and name == 'vera_app_setting'):
                lines.append(f'2; 0 123 TABLE DATA public {name} owner')
        return '\n'.join(lines)
    monkeypatch.setattr(maintenance, 'command', command)
    if missing:
        with pytest.raises(maintenance.MaintenanceError):
            maintenance.backup(tmp_path, {'state': {}, 'revision': 1})
        assert not (tmp_path / 'live-tour.json').exists()
        assert not (tmp_path / 'backup-scope.json').exists()
    else:
        maintenance.backup(tmp_path, {'state': {}, 'revision': 1})
        scope = json.loads((tmp_path / 'backup-scope.json').read_text())
        assert scope['excluded_schemas'] == ['cron']
        assert set(scope['verified_live_tour_tables']) == required
        assert not scope['full_instance_disaster_recovery_backup']
        assert (tmp_path / 'database.dump').stat().st_mode & 0o777 == 0o600
        assert (tmp_path / 'backup-scope.json').stat().st_mode & 0o777 == 0o600

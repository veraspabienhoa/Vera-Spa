"""The production preflight must be inert, bounded, and data-free on failure."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host = load('phase_three_host_preflight')
runner = load('run_phase_three_preflight')


def test_private_file_refuses_symlink_and_broad_permissions(tmp_path):
    path = tmp_path / 'env'
    path.write_text('DB_PASS=private-secret')
    path.chmod(0o644)
    with pytest.raises(host.Unavailable):
        host.read_bytes(path, private=True)
    path.chmod(0o600)
    assert host.read_bytes(path, private=True) == b'DB_PASS=private-secret'
    link = tmp_path / 'link'
    link.symlink_to(path)
    with pytest.raises(OSError):
        host.read_bytes(link, private=True)


def test_bound_file_and_command_output(tmp_path):
    path = tmp_path / 'large'
    path.write_bytes(b'x' * 101)
    with pytest.raises(host.Unavailable):
        host.read_bytes(path, maximum=100)
    with pytest.raises(host.Unavailable):
        host.command([sys.executable, '-c', 'print("x" * 10000)'], maximum=50)
    with pytest.raises(host.Unavailable):
        host.command([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=0.05)


def test_command_errors_and_stderr_are_not_exposed():
    code, output = host.command([sys.executable, '-c', 'import sys; print("secret-user:secret-pass", file=sys.stderr); sys.exit(1)'])
    assert code == 1
    assert output == ''


def test_environment_is_parsed_without_shell_evaluation():
    parsed = host.parse_environment(b'DB_PASS="$(touch /bad)"\nPRIVATE_TOKEN=must-not-appear\nDB_POOL_SIZE=2\n')
    assert parsed == {'DB_PASS': '$(touch /bad)', 'DB_POOL_SIZE': '2'}
    with pytest.raises(host.Unavailable):
        host.parse_environment(b'DB_PASS=x\nDB_PASS=y')
    with pytest.raises(host.Unavailable):
        host.parse_environment(b'DB_PASS="first second" other')


def test_process_roles_override_shared_file_and_worker_default():
    combined = host.effective_environment({'VERA_SERVICE_ROLE': 'api', 'DB_POOL_SIZE': '3'}, {'VERA_SERVICE_ROLE': 'combined', 'DB_POOL_SIZE': '2'})
    assert combined['VERA_SERVICE_ROLE'] == 'api'
    assert combined['DB_POOL_SIZE'] == '2'
    assert host.pool_summary({}, 'worker')['VERA_SERVICE_ROLE'] == 'worker'
    assert host.effective_environment({}, {'VERA_SERVICE_ROLE': 'combined'}, 'worker')['VERA_SERVICE_ROLE'] == 'worker'


def test_numeric_and_modes_are_allowlisted():
    data = host.pool_summary({'DB_POOL_SIZE': 'secret-name', 'DB_PASS': 'secret-password',
                              'DB_USER': 'secret-user', 'VERA_SERVICE_ROLE': 'secret-role',
                              'VERA_WORKER_DB_MODE': 'direct', 'DB_POOL_TIMEOUT': '25'})
    encoded = json.dumps(data)
    assert 'secret' not in encoded
    assert data['configured']['DB_POOL_SIZE'] is None
    assert data['configured']['DB_POOL_TIMEOUT'] == 25
    assert data['session_affinity'] == 'unverified_requires_provider_configuration'
    assert host.numeric('123456789', maximum=10**15) == 123456789


def test_declared_budget_is_arithmetic_only_never_fleet_capacity():
    fields = {'DB_CONNECTION_BUDGET': '63', 'DB_API_POOL_INSTANCES': '3', 'DB_BACKGROUND_POOL_INSTANCES': '2',
              'DB_DEDICATED_CONNECTIONS': '1', 'DB_EXTERNAL_CONNECTION_RESERVE': '10'}
    result = host.pool_summary(fields)
    assert result['declared_demand'] == 63
    assert result['budget_status'] == 'arithmetic_only_within_declaration'
    assert result['runtime_bounds_validated'] is False
    assert result['declaration_matches_actual_fleet'] == 'unverified'
    assert host.pool_summary({**fields, 'DB_API_POOL_INSTANCES': '0', 'DB_BACKGROUND_POOL_INSTANCES': '0'})['budget_status'] == 'invalid_or_partial'
    assert host.pool_summary({'DB_CONNECTION_BUDGET': '63'})['budget_status'] == 'invalid_or_partial'


def test_deploy_body_never_returned_and_tokens_are_not_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(host, 'BASE', tmp_path)
    (tmp_path / 'deploy.sh').write_text('#!/bin/sh\n# secret-comment\nflock 9\nsystemctl restart vera-api.service\nTOKEN=private-secret\n')
    result = host.deploy_summary()
    assert result['flock_token_present'] is True
    assert result['api_service_token_present'] is True
    assert result['locking_and_lifecycle_verified'] is False
    assert 'secret' not in json.dumps(result)
    assert 'systemctl restart' not in json.dumps(result)
    assert len(result['sha256']) == 64


def test_errors_do_not_leak_host_details(monkeypatch):
    def fail(*args):
        raise RuntimeError('postgresql://private-user:private-password@private-host/customers')
    monkeypatch.setattr(host, 'managed_configuration', fail)
    result = host.run('a' * 40)
    assert result['activation_ready'] is False
    assert result['status'] == 'unknown_host_inspection_failed'
    assert 'private' not in json.dumps(result)


def test_diagnostic_and_audited_application_revisions_are_distinct(monkeypatch):
    expected = 'a' * 40
    monkeypatch.setattr(host, 'managed_configuration', lambda home: (_ for _ in ()).throw(host.Unavailable()))
    result = host.run(expected)
    assert result['expected_main_sha'] == expected
    assert result['audited_application_sha'] == '02ef3641edf1dfaf12ab048c725df03c4397af3e'


def test_ssh_is_fixed_has_no_shell_or_arbitrary_inputs():
    env = {'VPS_USER': 'deploy', 'VPS_HOST': 'example.com', 'RUNNER_TEMP': '/tmp/runner'}
    args = runner.ssh_arguments('a' * 40, env)
    assert args[-1] == 'timeout 125 /opt/vera-spa/.venv/bin/python -I -B - ' + 'a' * 40
    assert 'StrictHostKeyChecking=yes' in args
    with pytest.raises(ValueError):
        runner.ssh_arguments('a' * 40 + '; echo private-secret', env)
    with pytest.raises(ValueError):
        runner.ssh_arguments('a' * 40, {**env, 'VPS_HOST': '-oProxyCommand=bad'})


def test_transport_accepts_only_bounded_json_not_banner_or_exception():
    response = {'read_only': True, 'activation_ready': False, 'status': 'observed'}
    code = 'import sys; sys.stdin.buffer.read(); print(' + repr(json.dumps(response)) + ')'
    assert runner.bounded_exchange([sys.executable, '-c', code], b'payload', timeout=2) == response
    for output in ('private-secret banner', 'x' * (runner.MAX_OUTPUT + 1), '{"read_only":true,"activation_ready":true}'):
        code = 'import sys; sys.stdin.buffer.read(); print(' + repr(output) + ')'
        with pytest.raises((ValueError, json.JSONDecodeError)):
            runner.bounded_exchange([sys.executable, '-c', code], b'payload', timeout=2)
    with pytest.raises(ValueError):
        runner.bounded_exchange([sys.executable, '-c', 'import time; time.sleep(10)'], b'payload', timeout=0.05)


def test_sources_never_import_application_or_mutate_remote():
    path = ROOT / 'scripts/phase_three_host_preflight.py'
    tree = ast.parse(path.read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module)
    assert not any(name and name.startswith('vera_') for name in imports)
    literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assert 'w' not in literals and 'wb' not in literals and 'a' not in literals
    assert not any('systemctl restart' in value or 'systemctl stop' in value or '--activate' in value for value in literals)
    assert 'shell=True' not in path.read_text()


def test_workflow_is_manual_read_only_and_exact_sha_pinned():
    source = (ROOT / '.github/workflows/phase-three-readonly-preflight.yml').read_text()
    assert 'workflow_dispatch:' in source
    assert '  push:' not in source and '  schedule:' not in source and '  workflow_run:' not in source
    assert 'contents: read' in source
    assert 'environment: production' in source
    assert 'expected_main_sha:' in source
    assert 'test "$GITHUB_REF" = refs/heads/main' in source
    assert 'test "$SOURCE_SHA" = "$EXPECTED_SHA"' in source
    assert source.count('gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main" --jq .object.sha') == 2
    assert source.count('GH_TOKEN: ${{ github.token }}') == 2
    assert 'git fetch' not in source
    for field in ('VPS_SSH_KEY', 'VPS_KNOWN_HOSTS', 'VPS_HOST', 'VPS_USER'):
        assert '${{ secrets.' + field + ' }}' in source
    assert 'systemctl' not in source and 'deploy.sh' not in source and 'journalctl' not in source
    assert 'persist-credentials: false' in source


@pytest.fixture
def inspected_host(monkeypatch):
    import types
    env = {'DB_HOST': 'secret-host', 'DB_USER': 'secret-user', 'DB_PASS': 'secret-pass', 'DB_SSLMODE': 'require'}
    records = [{'category': 'api', 'owned': True, 'pid': 123, 'start_ticks': 10,
                'cwd': '/hidden/release', 'sha': host.AUDITED_RELEASE_SHA, 'unit': None,
                'env': env, 'initial_digest': 'b' * 64}]
    state = {'records': records, 'database_calls': 0}
    monkeypatch.setattr(host, 'managed_configuration', lambda home: ({'available': True, 'valid': True}, env, ('config-fingerprint',)))
    monkeypatch.setattr(host, 'process_inventory', lambda managed: (state['records'], 0))
    monkeypatch.setattr(host, 'host_capacity', lambda: {'cpu_logical': 2})
    monkeypatch.setattr(host, 'deploy_summary', lambda: {'sha256': 'a' * 64})
    monkeypatch.setattr(host, 'schedule_summary', lambda: {'other_user_crons': 'unknown'})
    monkeypatch.setattr(host, 'unit_summary', lambda unit: {'status': 'unknown'})
    def inspect(url):
        state['database_calls'] += 1
        assert url.password == 'secret-pass'
        return {'status': 'observed', 'parity': {'status': 'pass'}}
    monkeypatch.setitem(sys.modules, 'phase_three_db_preflight', types.SimpleNamespace(inspect_database=inspect))
    return state


def test_changed_observation_discards_otherwise_passing_database_findings(inspected_host, monkeypatch):
    calls = []
    def changing_snapshot(*args):
        calls.append(1)
        return ('path', host.AUDITED_RELEASE_SHA, 'changed-config' if len(calls) == 2 else 'initial-config')
    monkeypatch.setattr(host, 'snapshot', changing_snapshot)
    result = host.run('a' * 40)
    assert inspected_host['database_calls'] == 1
    assert result['observation_stable'] is False
    assert result['status'] == 'inconclusive'
    assert result['database'] == {'status': 'unknown_runtime_changed_during_observation'}
    assert 'secret' not in json.dumps(result)


def test_wrong_target_release_skips_database_entirely(inspected_host, monkeypatch):
    monkeypatch.setattr(host, 'snapshot', lambda *args: ('path', 'f' * 40))
    result = host.run('a' * 40)
    assert inspected_host['database_calls'] == 0
    assert result['status'] == 'target_release_moved'
    assert result['database']['status'] == 'not_inspected_unverified_release_or_configuration'
    assert result['activation_ready'] is False


def test_stable_observation_still_never_claims_activation_or_affinity(inspected_host, monkeypatch):
    monkeypatch.setattr(host, 'snapshot', lambda *args: ('path', host.AUDITED_RELEASE_SHA))
    result = host.run('a' * 40)
    assert inspected_host['database_calls'] == 1
    assert result['observation_stable'] is True
    assert result['status'] == 'observed'
    assert result['activation_ready'] is False
    assert result['all_writers_inventory_complete'] is False
    assert result['exclusive_deployment_lock_held'] is False
    assert result['session_affinity'] == 'unverified_requires_provider_configuration'
    assert 'secret' not in json.dumps(result)


def test_overall_deadline_bypasses_best_effort_catches_and_cleans_up(monkeypatch):
    assert issubclass(host.Deadline, BaseException)
    assert not issubclass(host.Deadline, Exception)
    with pytest.raises(host.Deadline):
        host.deadline_expired(None, None)
    monkeypatch.setattr(host.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(host.signal, 'alarm', lambda *args: None)
    monkeypatch.setattr(host, 'run', lambda *args: (_ for _ in ()).throw(host.Deadline()))
    assert host.main() == 2

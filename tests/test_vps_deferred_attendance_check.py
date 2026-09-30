import json
from pathlib import Path
from datetime import datetime, timedelta
import pytest
import vera_attendance_source as source
import vera_vps_deferred_attendance_check as check


def policy(tmp_path, monkeypatch, value):
    path = tmp_path / 'source.json'
    if value is not None:
        path.write_text(json.dumps(value))
    monkeypatch.setenv('VERA_ATTENDANCE_SOURCE_FILE', str(path))
    return path


def test_explicit_deferral_verifies_policy_without_claiming_freshness(tmp_path, monkeypatch):
    policy(tmp_path, monkeypatch, {'version': 1, 'source': 'facegate', 'effective_date': '2026-09-29'})
    result = check.verify_policy()
    assert result['ok'] and result['source'] == 'facegate'
    assert result['timesoft_network_enabled'] is False
    assert result['attendance_freshness_verified'] is False
    assert result['attendance_readiness_verified'] is False
    assert result['database_writes'] is False


@pytest.mark.parametrize('value', [None, {}, {'version': 1, 'source': 'timesoft'},
    {'version': 1, 'source': 'facegate', 'effective_date': 'invalid'}])
def test_missing_or_invalid_policy_fails_closed(tmp_path, monkeypatch, value, capsys):
    policy(tmp_path, monkeypatch, value)
    assert check.main() == 1
    assert json.loads(capsys.readouterr().out)['reason'] == 'active_facegate_policy_unverified'


def test_future_cutover_does_not_prove_active_facegate(tmp_path, monkeypatch):
    future = datetime.now(source.VN_TZ).date() + timedelta(days=1)
    policy(tmp_path, monkeypatch, {'version': 1, 'source': 'facegate', 'effective_date': future.isoformat()})
    assert check.main() == 1


def test_workflow_default_is_strict_and_activation_never_defers():
    workflow = Path('.github/workflows/deploy-vps.yml').read_text()
    section = workflow.split('defer_attendance_freshness:', 1)[1].split('permissions:', 1)[0]
    assert 'default: false' in section
    assert 'if: ${{ !inputs.defer_attendance_freshness || inputs.retire_timesoft }}' in workflow
    assert 'if: ${{ inputs.defer_attendance_freshness && !inputs.retire_timesoft }}' in workflow
    for gate in ['Verify exact production commit and health', 'Verify active release and production schemas', 'Verify public frontend commit and entry document']:
        assert gate in workflow

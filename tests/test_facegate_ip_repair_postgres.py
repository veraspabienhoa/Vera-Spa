"""Exercise the actual CLI transaction with a one-connection PostgreSQL pool."""
import json
import os
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

import vera_facegate_ip_repair as repair


@pytest.fixture
def database(monkeypatch):
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Real PostgreSQL required')
    schema = 'ip_repair_' + uuid4().hex
    owner = create_engine(url)
    with owner.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, pool_size=1, max_overflow=0, pool_timeout=.1,
                           connect_args={'options': f'-csearch_path={schema}'})
    mapping = {'username': 'worker', 'profile_id': 42, 'employee_code': '',
               'device_name': 'Test Worker',
               'registration_ref': {'file_type': 0, 'file_index': 0, 'file_position': 12345},
               'device_address': '192.168.1.34', 'confirmed_by': 'admin',
               'confirmed_at': '2026-09-29T04:27:00+00:00'}
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE employees(username text PRIMARY KEY,role text,payload jsonb DEFAULT '{}'::jsonb)"))
        conn.execute(text("INSERT INTO employees(username,role) VALUES ('admin','admin'),('worker','nhanvien')"))
        conn.execute(text('''CREATE TABLE vera_app_setting(category text,setting_key text,
            value_json jsonb,updated_by text,updated_at timestamptz,revision integer,
            PRIMARY KEY(category,setting_key))'''))
        conn.execute(text("INSERT INTO vera_app_setting VALUES ('facegate','mapping_test',CAST(:v AS jsonb),'admin',NOW(),1)"),
                     {'v': json.dumps([mapping])})
        conn.execute(text("INSERT INTO vera_app_setting VALUES ('devices','registry',CAST(:v AS jsonb),'admin',NOW(),1)"),
                     {'v': json.dumps({'devices': [{'id': 'facegate-current', 'address': '192.168.1.26'}]})})
        conn.execute(text("CREATE TABLE raw_evidence(payload text); INSERT INTO raw_evidence VALUES ('immutable')"))
    import vera_facegate_cutover as cutover
    import vera_facegate_control_log as device
    monkeypatch.setattr(cutover, 'verify_runtime', lambda sha: sha)
    monkeypatch.setattr(cutover, 'runtime_engine', lambda **kwargs: engine)
    monkeypatch.setenv('VERA_FACEGATE_DEVICE_ID', 'test')
    mode = {'race': None}
    def profiles():
        assert engine.pool.checkedout() == 0, 'device I/O under a pooled connection'
        if mode['race']:
            with engine.begin() as conn:
                conn.execute(text(mode['race']))
        return [{key: mapping[key] for key in ('profile_id', 'device_name', 'registration_ref')}]
    monkeypatch.setattr(device, 'fetch_registered_profiles', profiles)
    try:
        yield engine, mapping, mode
    finally:
        engine.dispose()
        with owner.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        owner.dispose()


def invoke(monkeypatch, capsys, *extra):
    monkeypatch.setattr(sys, 'argv', ['repair', '--address', '192.168.1.26',
        '--operator', 'admin', '--expected-count', '1', '--expected-commit', 'a' * 40, *extra])
    status = repair.main()
    return status, json.loads(capsys.readouterr().out.strip())


def stored(engine):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT value_json,revision FROM vera_app_setting WHERE category='facegate'")).one()
        assert conn.execute(text('SELECT payload FROM raw_evidence')).scalar_one() == 'immutable'
        return row


def test_preview_apply_readback_and_repeat(database, monkeypatch, capsys):
    engine, original, _ = database
    status, preview = invoke(monkeypatch, capsys)
    assert status == 0 and preview['applied'] is False
    assert stored(engine) == ([original], 1)
    status, applied = invoke(monkeypatch, capsys, '--apply', '--preview-digest', preview['preview_digest'])
    assert status == 0 and applied['reconfirmed_count'] == 1
    mappings, revision = stored(engine)
    assert revision == 2 and len(mappings) == 1
    assert mappings[0]['device_address'] == '192.168.1.26'
    assert mappings[0]['ip_reconfirmation']['previous_mapping'] == original
    _, preview = invoke(monkeypatch, capsys)
    status, repeated = invoke(monkeypatch, capsys, '--apply', '--preview-digest', preview['preview_digest'])
    assert status == 0 and repeated['reconfirmed_count'] == 0
    assert stored(engine) == (mappings, revision)


@pytest.mark.parametrize('extra', [[], ['--preview-digest', 'outdated']])
def test_apply_requires_matching_preview(database, monkeypatch, capsys, extra):
    engine, original, _ = database
    status, result = invoke(monkeypatch, capsys, '--apply', *extra)
    assert status == 1 and result['reason'] == 'preview_changed_or_missing'
    assert stored(engine) == ([original], 1)


@pytest.mark.parametrize('race', [
    "UPDATE employees SET role='nhanvien' WHERE username='admin'",
    "UPDATE vera_app_setting SET value_json=jsonb_set(value_json,'{0,employee_code}', '\"changed\"') WHERE category='facegate'",
    "UPDATE vera_app_setting SET value_json=jsonb_set(value_json,'{devices,0,address}', '\"192.168.1.35\"') WHERE category='devices'",
])
def test_concurrent_change_prevents_repair(database, monkeypatch, capsys, race):
    engine, _, mode = database
    _, preview = invoke(monkeypatch, capsys)
    mode['race'] = race
    status, result = invoke(monkeypatch, capsys, '--apply', '--preview-digest', preview['preview_digest'])
    assert status == 1 and result['reason'] == 'snapshot_changed'
    mappings, revision = stored(engine)
    assert revision == 1 and mappings[0]['device_address'] == '192.168.1.34'


def test_database_failure_rolls_back_and_sanitizes_log(database, monkeypatch, capsys):
    engine, original, _ = database
    _, preview = invoke(monkeypatch, capsys)
    with engine.begin() as conn:
        conn.execute(text("""CREATE FUNCTION reject_repair() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'private database payload'; END $$"""))
        conn.execute(text("CREATE TRIGGER reject_repair BEFORE UPDATE ON vera_app_setting FOR EACH ROW EXECUTE FUNCTION reject_repair()"))
    status, result = invoke(monkeypatch, capsys, '--apply', '--preview-digest', preview['preview_digest'])
    assert status == 1 and result['ok'] is False
    assert 'private' not in json.dumps(result)
    assert stored(engine) == ([original], 1)

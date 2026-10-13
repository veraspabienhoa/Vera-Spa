from copy import deepcopy
from types import SimpleNamespace
import json

from test_devices_checkin import Store, fixture


class ConfigurationStore(Store):
    def __init__(self):
        super().__init__()
        self.backup = None

    def execute(self, statement, params=None):
        sql = str(statement)
        if "'facegate_configuration'" not in sql:
            return super().execute(statement, params)
        self.calls.append(sql)
        if sql.startswith('INSERT'):
            self.backup = {'value_json': json.loads(params['value']), 'revision': (self.backup or {}).get('revision', 0) + 1}
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: deepcopy(self.backup)))


def setup(monkeypatch, role='admin'):
    monkeypatch.setattr('test_devices_checkin.Store', ConfigurationStore)
    return fixture(role)


def test_save_delete_restore_preserves_exact_configuration_and_other_devices(monkeypatch):
    client, store = setup(monkeypatch)
    current = client.get('/v2/devices/registry').json()
    machine = current['devices'][0] | {'address': '192.168.1.26', 'location': 'Lễ tân', 'notes': 'LAN', 'port': 80}
    printer = machine | {'id': 'printer', 'name': 'Printer', 'kind': 'printer', 'adapter': 'pending', 'serial': 'print-1'}
    assert client.put('/v2/devices/registry', json={'expected_revision': 0, 'devices': [machine, printer]}).status_code == 200
    saved = client.post('/v2/devices/facegate-configuration?expected_revision=1')
    assert saved.status_code == 200
    assert saved.json()['configuration']['device'] == machine
    assert client.delete('/v2/devices/registry/facegate-current?expected_revision=1').status_code == 200
    assert client.get('/v2/devices/facegate-configuration').json() == saved.json()
    restored = client.post('/v2/devices/facegate-configuration/restore?expected_revision=2&backup_revision=1')
    assert restored.status_code == 200, restored.text
    assert restored.json()['devices'] == [printer, machine]
    assert restored.json()['revision'] == 3
    assert client.post('/v2/devices/facegate-configuration/restore?expected_revision=2&backup_revision=1').status_code == 409
    assert client.post('/v2/devices/facegate-configuration?expected_revision=3').json()['revision'] == 2
    assert client.post('/v2/devices/facegate-configuration/restore?expected_revision=3&backup_revision=1').status_code == 409


def test_missing_configuration_and_stale_save(monkeypatch):
    client, store = setup(monkeypatch)
    assert client.get('/v2/devices/facegate-configuration').json()['configuration'] is None
    assert client.post('/v2/devices/facegate-configuration/restore?expected_revision=0&backup_revision=1').status_code == 404
    assert client.post('/v2/devices/facegate-configuration?expected_revision=4').status_code == 409
    assert store.backup is None
    assert client.delete('/v2/devices/registry/facegate-current?expected_revision=0').status_code == 200
    assert client.post('/v2/devices/facegate-configuration?expected_revision=1').status_code == 404


def test_non_admin_denied_before_database(monkeypatch):
    client, store = setup(monkeypatch, 'quanly')
    assert client.get('/v2/devices/facegate-configuration').status_code == 403
    assert client.post('/v2/devices/facegate-configuration?expected_revision=0').status_code == 403
    assert client.post('/v2/devices/facegate-configuration/restore?expected_revision=0&backup_revision=1').status_code == 403
    assert not store.calls


def test_restore_blocks_serial_collision_without_changing_registry(monkeypatch):
    client, store = setup(monkeypatch)
    assert client.post('/v2/devices/facegate-configuration?expected_revision=0').status_code == 200
    printer = {'id': 'printer', 'name': 'Printer', 'kind': 'printer', 'serial': '2023044'}
    assert client.put('/v2/devices/registry', json={'expected_revision': 0, 'devices': [printer]}).status_code == 200
    before = deepcopy(store.row)
    assert client.post('/v2/devices/facegate-configuration/restore?expected_revision=1&backup_revision=1').status_code == 409
    assert store.row == before

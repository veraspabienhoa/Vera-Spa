"""Changing FaceGate IP must not trust an earlier device's mapping or redirect to arbitrary hosts."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import vera_facegate_control_log as facegate
import vera_web_v2_devices as devices
from vera_web_v2_permissions import FEATURES, DEFAULT_ROLE_FEATURES


class Engine:
    @contextmanager
    def connect(self):
        yield SimpleNamespace()


def test_facegate_ip_is_restricted_and_override_is_scoped(monkeypatch):
    for address in ['127.0.0.1', '169.254.169.254', '192.168.2.4', 'http://192.168.1.26/login.asp', 'example.com']:
        with pytest.raises(ValueError):
            devices.Device(id='facegate-current', name='FaceGate', kind='faceid', adapter='facegate_server', address=address)
    devices.Device(id='facegate-current', name='FaceGate', kind='faceid', adapter='facegate_server', address='192.168.1.26')
    monkeypatch.setattr(devices, 'facegate_address', lambda conn: '192.168.1.26')
    monkeypatch.setenv('VERA_FACEGATE_BASE_URL', 'http://192.168.1.25')
    monkeypatch.setenv('VERA_FACEGATE_USERNAME', 'service')
    monkeypatch.setenv('VERA_FACEGATE_PASSWORD', 'placeholder')
    with devices.use_registered_facegate(Engine()):
        assert facegate._facegate_config()[0] == 'http://192.168.1.26'
    assert facegate._facegate_config()[0] == 'http://192.168.1.25'


def test_mapping_from_old_ip_is_never_active_on_new_ip(monkeypatch):
    monkeypatch.setattr(devices, 'facegate_address', lambda conn: '192.168.1.26')
    rows = [{'username': 'old', 'confirmed_by': 'admin'},
            {'username': 'current', 'confirmed_by': 'admin', 'device_address': '192.168.1.26'}]
    assert devices.active_facegate_mappings(None, rows) == rows[1:]


def test_device_permissions_are_separate_and_admin_default():
    keys = {'device_view', 'device_manage', 'device_station_operate', 'device_checkin_confirm',
            'device_history_view', 'device_facegate_mapping_manage', 'device_facegate_ip_manage'}
    assert keys <= FEATURES.keys()
    assert keys <= DEFAULT_ROLE_FEATURES['admin']
    assert all(not keys.intersection(features) for role, features in DEFAULT_ROLE_FEATURES.items() if role != 'admin')


def test_archived_facegate_event_records_endpoint_for_safe_mapping():
    import json
    from vera_facegate_sync import prepare_batch
    event = {'event_id': 3, 'occurred_at': '2026-09-25T08:00:00+07:00',
             'device_name': 'Worker', 'status_code': '0', 'type_code': '1', 'registration_ref': None}
    data = prepare_batch({'source': 'facegate_control_log', 'records': [event], 'total_count': 1, 'truncated': False},
                         '2026-09-25', '192.168.1.26')
    assert json.loads(data[0]['payload_json'])['device_address'] == '192.168.1.26'

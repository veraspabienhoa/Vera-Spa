from copy import deepcopy
import unittest

from vera_facegate_ip_repair import RepairError, prepare

OLD = '192.168.1.25'
NEW = '192.168.1.26'
NOW = '2026-10-02T12:30:00+00:00'
REF = {'file_type': 0, 'file_index': 0, 'file_position': 100}


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {'profile_id': 198, 'username': 'Gia Anh',
                        'device_name': 'Anh Nguyen', 'registration_ref': dict(REF),
                        'employee_code': '', 'confirmed_by': 'admin',
                        'confirmed_at': '2026-09-29T04:27:27+00:00',
                        'device_address': OLD}
        self.profile = {key: deepcopy(self.mapping[key]) for key in
                        ('profile_id', 'device_name', 'registration_ref')}
        self.staff = [{'username': 'Gia Anh', 'role': 'letan', 'deleted': False}]

    def plan(self, mappings=None, profiles=None):
        return prepare(mappings or [self.mapping], profiles or [self.profile],
                       self.staff, NEW, 'admin', NOW)

    def test_exact_old_binding_replaces_in_place_and_preserves_evidence(self):
        before = deepcopy((self.mapping, self.profile, self.staff))
        result, count = self.plan()
        self.assertEqual(count, 1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['employee_code'], '')
        self.assertEqual(result[0]['username'], 'Gia Anh')
        self.assertEqual(result[0]['device_address'], NEW)
        self.assertEqual(result[0]['ip_reconfirmation']['previous_mapping'], self.mapping)
        self.assertEqual((self.mapping, self.profile, self.staff), before)

    def test_repeat_is_noop(self):
        repaired, _ = self.plan()
        again, count = self.plan(mappings=repaired)
        self.assertEqual((again, count), (repaired, 0))

    def test_changed_reference_or_name_never_reassigns_by_name(self):
        for key, value in [('device_name', 'Other'), ('registration_ref', {**REF, 'file_position': 101}), ('profile_id', 199)]:
            with self.subTest(key=key), self.assertRaises(RepairError):
                self.plan(profiles=[{**self.profile, key: value}])

    def test_duplicate_saved_or_live_binding_rejects_whole_batch(self):
        for mappings, profiles in [([self.mapping, deepcopy(self.mapping)], [self.profile]),
                                   ([self.mapping], [self.profile, deepcopy(self.profile)]),
                                   ([self.mapping], [self.profile, {**self.profile, 'profile_id': 200}])]:
            with self.assertRaises(RepairError):
                self.plan(mappings, profiles)

    def test_missing_deleted_admin_and_unconfirmed_people_reject(self):
        for staff in [[], [{**self.staff[0], 'deleted': True}], [{**self.staff[0], 'role': 'admin'}]]:
            self.staff = staff
            with self.assertRaises(RepairError):
                self.plan()
        self.staff = [{'username': 'Gia Anh', 'role': 'letan'}]
        self.mapping['confirmed_by'] = ''
        with self.assertRaises(RepairError):
            self.plan()

    def test_invalid_target_and_time_reject(self):
        for address, stamp in [('127.0.0.1', NOW), (NEW, '2026-10-02T12:00:00'),
                               (NEW, '2026-09-28T12:00:00+00:00')]:
            with self.assertRaises((RepairError, ValueError)):
                prepare([self.mapping], [self.profile], self.staff, address, 'admin', stamp)


if __name__ == '__main__':
    unittest.main()


def test_refresh_today_publishes_with_owned_transaction(monkeypatch):
    from contextlib import contextmanager
    from datetime import datetime
    import vera_attendance_source as source
    import vera_facegate_sync as archive
    import vera_facegate_runtime as runtime
    from vera_facegate_ip_repair import refresh_today
    day = datetime.now(source.VN_TZ).date().isoformat()
    calls = []
    connection = object()
    class Engine:
        @contextmanager
        def begin(self):
            calls.append('begin')
            yield connection
            calls.append('commit')
        @contextmanager
        def connect(self):
            yield connection
    engine = Engine()
    monkeypatch.setattr(source, 'source_for', lambda _: 'facegate')
    def sync(actual_engine, actual_day, *, apply):
        assert actual_engine is engine and actual_day == day and apply
        calls.append('archive')
        return {'fetched_count': 2}
    def publish(conn, start, end):
        assert conn is connection and start == end and start.isoformat() == day
        calls.append('publish')
        return [{'mapped_scan_count': 2}]
    monkeypatch.setattr(archive, 'sync_day', sync)
    monkeypatch.setattr(runtime, 'publish', publish)
    monkeypatch.setattr(source, 'health', lambda _: {'row_count': 2})
    result = refresh_today(engine, day)
    assert calls == ['archive', 'begin', 'publish', 'commit']
    assert result['source_health']['row_count'] == 2


def test_refresh_rejects_old_date_and_inactive_source_before_io(monkeypatch):
    from datetime import datetime
    import pytest
    import vera_attendance_source as source
    from vera_facegate_ip_repair import refresh_today
    monkeypatch.setattr(source, 'source_for', lambda _: 'timesoft')
    for day in ['2000-01-01', datetime.now(source.VN_TZ).date().isoformat()]:
        with pytest.raises(RepairError, match='refresh_requires_today'):
            refresh_today(None, day)

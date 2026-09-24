import copy
from contextlib import contextmanager
import json
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, text
import vera_facegate_sync as sync

DAY = '2026-09-24'
REF = {'file_type': 0, 'file_index': 0, 'file_position': 1420}
EVENT = {'event_id': 78688, 'occurred_at': DAY+'T20:20:36+07:00',
         'device_name': 'An An', 'status_code': '1', 'type_code': '0', 'registration_ref': REF}

def log(*events):
    return {'source': 'facegate_control_log', 'total_count': len(events), 'truncated': False, 'records': list(events)}

@pytest.fixture
def engine():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        sync.ensure_schema(conn)
    yield engine
    engine.dispose()

def test_repeat_sync_deduplicates(engine):
    batch = sync.prepare_batch(log(EVENT), DAY)
    with engine.begin() as conn:
        first = sync.persist_batch(conn, '2023044', DAY, batch)
    with engine.begin() as conn:
        second = sync.persist_batch(conn, '2023044', DAY, batch)
        assert conn.execute(text('SELECT COUNT(*) FROM vera_facegate_event')).scalar() == 1
    assert first['inserted_count'] == 1
    assert second == {'inserted_count': 0, 'already_stored_count': 1, 'stored_day_count': 1}

def test_conflict_rolls_back_whole_batch(engine):
    with engine.begin() as conn:
        sync.persist_batch(conn, '2023044', DAY, sync.prepare_batch(log(EVENT), DAY))
    with pytest.raises(sync.SyncError, match='existing_event_changed'):
        with engine.begin() as conn:
            sync.persist_batch(conn, '2023044', DAY, sync.prepare_batch(log(
                {**EVENT, 'event_id': 78689}, {**EVENT, 'status_code': '2'}), DAY))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_facegate_event')).scalar() == 1
        assert conn.execute(text('SELECT last_observed_count FROM vera_facegate_sync_day')).scalar() == 1

def test_same_id_other_device_or_time_not_dropped(engine):
    with engine.begin() as conn:
        sync.persist_batch(conn, 'device1', DAY, sync.prepare_batch(log(EVENT), DAY))
        sync.persist_batch(conn, 'device2', DAY, sync.prepare_batch(log(EVENT), DAY))
        sync.persist_batch(conn, 'device1', DAY, sync.prepare_batch(log({**EVENT, 'occurred_at': DAY+'T21:20:36+07:00'}), DAY))
        assert conn.execute(text('SELECT COUNT(*) FROM vera_facegate_event')).scalar() == 3

@pytest.mark.parametrize('mutate', [
    lambda x: x.update(truncated=True), lambda x: x.update(total_count=2),
    lambda x: x.update(source='timesoft'),
    lambda x: x['records'][0].update(occurred_at='2026-09-23T20:20:36+07:00'),
    lambda x: x['records'][0].update(occurred_at='2026-09-24T20:20:36'),
    lambda x: x['records'][0].update(event_id=-1),
])
def test_invalid_fetch_rejected(mutate):
    data = copy.deepcopy(log(EVENT))
    mutate(data)
    with pytest.raises(sync.SyncError):
        sync.prepare_batch(data, DAY)

def test_duplicate_ids_rejected():
    with pytest.raises(sync.SyncError, match='duplicate_event_id'):
        sync.prepare_batch(log(EVENT, EVENT), DAY)

def test_timezone_and_no_extra_fields():
    batch = sync.prepare_batch(log({**EVENT, 'occurred_at': '2026-09-24T13:20:36+00:00', 'password': 'not-archived'}), DAY)
    assert batch[0]['occurred_at'] == EVENT['occurred_at']
    assert 'password' not in batch[0]['payload_json']

def test_preview_releases_db_before_network_and_never_writes(engine):
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE vera_app_setting(category text,setting_key text,value_json text)'))
        mapping = {'username': 'An An', 'confirmed_by': 'admin', 'registration_ref': REF}
        conn.execute(text('INSERT INTO vera_app_setting VALUES (:c,:k,:v)'),
                     {'c': 'facegate', 'k': 'mapping_2023044', 'v': json.dumps([mapping])})
    class Tracked:
        opened = False
        @contextmanager
        def connect(self):
            self.opened = True
            try:
                with engine.connect() as conn:
                    yield conn
            finally:
                self.opened = False
        def begin(self):
            raise AssertionError('preview attempted write')
    tracked = Tracked()
    def fetch(start, end):
        assert not tracked.opened
        assert start == end == DAY
        return log(EVENT, {**EVENT, 'event_id': 78689, 'registration_ref': None})
    with patch.dict('os.environ', {'VERA_FACEGATE_DEVICE_ID': '2023044'}):
        result = sync.sync_day(tracked, DAY, fetch=fetch)
    assert result['reference_match_count'] == 1
    assert result['unmatched_count'] == 1
    assert result['applied'] is False
    assert result['attendance_calculation_enabled'] is False
    with engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_facegate_event')).scalar() == 0

@pytest.mark.parametrize('busy,decreased', [(False, False), (True, False), (False, True)])
def test_apply_lock_and_decreased_count(engine, busy, decreased):
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE vera_app_setting(category text,setting_key text,value_json text)'))
        if decreased:
            sync.persist_batch(conn, '2023044', DAY, sync.prepare_batch(log(EVENT, {**EVENT, 'event_id': 78689}), DAY))
    class Result:
        def scalar(self):
            return not busy
    class Connection:
        def __init__(self, conn):
            self.conn = conn
        def execute(self, query, *args):
            if str(query).startswith('SELECT pg_try_advisory_xact_lock'):
                return Result()
            return self.conn.execute(query, *args)
    class Tracked:
        opened = False
        @contextmanager
        def connect(self):
            self.opened = True
            try:
                with engine.connect() as conn:
                    yield conn
            finally:
                self.opened = False
        @contextmanager
        def begin(self):
            self.opened = True
            try:
                with engine.begin() as conn:
                    yield Connection(conn)
            finally:
                self.opened = False
    tracked = Tracked()
    def fetch(*args):
        assert not tracked.opened
        return log(EVENT)
    with patch.dict('os.environ', {'VERA_FACEGATE_DEVICE_ID': '2023044'}):
        if busy or decreased:
            with pytest.raises(sync.SyncError, match='sync_busy' if busy else 'device_day_count_decreased'):
                sync.sync_day(tracked, DAY, apply=True, fetch=fetch)
        else:
            assert sync.sync_day(tracked, DAY, apply=True, fetch=fetch)['inserted_count'] == 1
            assert sync.sync_day(tracked, DAY, apply=True, fetch=fetch)['already_stored_count'] == 1

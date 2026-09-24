"""Archive one complete FaceGate Control Log day in VERA PostgreSQL.

Default: read-only preview. --apply saves raw evidence only, never payroll,
attendance projections, employee mappings, photos or device enrollment.
"""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
import signal

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import vera_facegate_control_log as device
from vera_facegate_readiness import runtime_device_environment, summarize


class SyncError(ValueError):
    """Safe machine-readable reason, without device or employee data."""


def prepare_batch(log, day):
    day = date.fromisoformat(day)
    records = log.get('records')
    if log.get('source') != 'facegate_control_log' or not isinstance(records, list):
        raise SyncError('invalid_log')
    if log.get('truncated') or len(records) > device.MAX_RECORDS:
        raise SyncError('incomplete_day')
    if type(log.get('total_count')) is not int or log['total_count'] != len(records):
        raise SyncError('incomplete_day')
    result, seen = [], set()
    for event in records:
        event_id = event.get('event_id')
        if type(event_id) is not int or event_id < 0 or event_id in seen:
            raise SyncError('invalid_or_duplicate_event_id')
        seen.add(event_id)
        try:
            instant = datetime.fromisoformat(event['occurred_at'])
            if instant.utcoffset() is None:
                raise ValueError()
            instant = instant.astimezone(device.VN_TZ)
            if instant.date() != day:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise SyncError('event_outside_requested_day') from None
        payload = {key: event.get(key) for key in (
            'device_name', 'status_code', 'type_code', 'registration_ref')}
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        if len(encoded.encode('utf-8')) > 4096:
            raise SyncError('event_too_large')
        result.append({'event_id': str(event_id), 'occurred_at': instant.isoformat(),
                       'work_date': day.isoformat(), 'payload_json': encoded,
                       'payload_sha256': hashlib.sha256(encoded.encode('utf-8')).hexdigest()})
    return result


def ensure_schema(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_facegate_event (
        device_id text NOT NULL, event_id text NOT NULL, occurred_at text NOT NULL,
        work_date text NOT NULL, payload_json text NOT NULL,
        payload_sha256 text NOT NULL, imported_at text NOT NULL,
        PRIMARY KEY (device_id, event_id, occurred_at))'''))
    conn.execute(text('''CREATE INDEX IF NOT EXISTS vera_facegate_event_day
        ON vera_facegate_event(device_id, work_date)'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_facegate_sync_day (
        device_id text NOT NULL, work_date text NOT NULL, last_observed_count integer NOT NULL,
        last_synced_at text NOT NULL, PRIMARY KEY(device_id, work_date))'''))


def persist_batch(conn, device_id, day, batch):
    """Caller owns one transaction; no device/network calls while it is open."""
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for event in batch:
        row = {**event, 'device_id': device_id, 'imported_at': now}
        changed = conn.execute(text('''INSERT INTO vera_facegate_event
            (device_id,event_id,occurred_at,work_date,payload_json,payload_sha256,imported_at)
            VALUES (:device_id,:event_id,:occurred_at,:work_date,:payload_json,:payload_sha256,:imported_at)
            ON CONFLICT(device_id,event_id,occurred_at) DO NOTHING'''), row)
        inserted += changed.rowcount
        existing = conn.execute(text('''SELECT payload_sha256 FROM vera_facegate_event
            WHERE device_id=:device_id AND event_id=:event_id AND occurred_at=:occurred_at'''), row).scalar_one()
        if existing != row['payload_sha256']:
            raise SyncError('existing_event_changed')
    conn.execute(text('''INSERT INTO vera_facegate_sync_day
        (device_id,work_date,last_observed_count,last_synced_at)
        VALUES (:device_id,:day,:count,:now)
        ON CONFLICT(device_id,work_date) DO UPDATE SET
        last_observed_count=excluded.last_observed_count,last_synced_at=excluded.last_synced_at'''),
        {'device_id': device_id, 'day': day, 'count': len(batch), 'now': now})
    stored = conn.execute(text('''SELECT COUNT(*) FROM vera_facegate_event
        WHERE device_id=:device_id AND work_date=:day'''), {'device_id': device_id, 'day': day}).scalar_one()
    return {'inserted_count': inserted, 'already_stored_count': len(batch)-inserted,
            'stored_day_count': stored}


def sync_day(engine, day, *, apply=False, fetch=None):
    day = date.fromisoformat(day).isoformat()
    device_id = device.mapping_device_id()
    # Release this connection before any device requests.
    with engine.connect() as conn:
        mappings = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='facegate' AND setting_key=:key"),
                                {'key': 'mapping_'+device_id}).scalar() or []
    if isinstance(mappings, str):
        mappings = json.loads(mappings)
    if not isinstance(mappings, list):
        raise SyncError('invalid_mapping_data')
    log = (fetch or device.fetch_control_log)(day, day)
    batch = prepare_batch(log, day)
    stats = summarize(log, mappings)
    result = {'ok': True, 'date': day, 'applied': apply, 'fetched_count': len(batch),
              'device_total_count': log['total_count'], 'complete_fetch': True,
              'confirmed_mapping_count': stats['confirmed_mapping_count'],
              'reference_match_count': stats['sample_reference_matches'],
              'unmatched_count': len(batch)-stats['sample_reference_matches'],
              'attendance_calculation_enabled': False, 'attendance_cutover_ready': False}
    if apply:
        with engine.begin() as conn:
            # Serialize syncs for this device, fail promptly if another is busy.
            # Do not hold this lock during device I/O.
            if not conn.execute(text('SELECT pg_try_advisory_xact_lock(hashtext(:key))'),
                                {'key': 'facegate_archive_'+device_id}).scalar():
                raise SyncError('sync_busy')
            # Prevent an older fetched snapshot from overwriting counts of a newer sync.
            ensure_schema(conn)
            prior = conn.execute(text('''SELECT last_observed_count FROM vera_facegate_sync_day
                WHERE device_id=:device_id AND work_date=:day'''), {'device_id': device_id, 'day': day}).scalar()
            if prior is not None and prior > len(batch):
                raise SyncError('device_day_count_decreased')
            result.update(persist_batch(conn, device_id, day, batch))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True, help='Vietnam day, YYYY-MM-DD')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    engine = None
    def deadline(*_):
        raise TimeoutError()
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(180)
    try:
        runtime_device_environment()
        from vera_vps_data_check import _database_url, _running_api_environment
        from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
        env = ({key: os.environ.get(key, '') for key in RUNTIME_ENV_KEYS}
               if load_managed_runtime_environment() else _running_api_environment())
        sslmode = env.get('DB_SSLMODE', 'require')
        if sslmode not in {'require', 'verify-ca', 'verify-full'}:
            sslmode = 'require'
        engine = create_engine(_database_url(env), poolclass=NullPool, connect_args={
            'connect_timeout': 5, 'sslmode': sslmode,
            'options': '-c statement_timeout=5000 -c lock_timeout=2000' +
                       ('' if args.apply else ' -c default_transaction_read_only=on')})
        print(json.dumps(sync_day(engine, args.date, apply=args.apply)))
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SyncError) else type(exc).__name__
        print(json.dumps({'ok': False, 'reason': reason, 'attendance_cutover_ready': False}))
        raise SystemExit(1) from None
    finally:
        signal.alarm(0)
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    main()

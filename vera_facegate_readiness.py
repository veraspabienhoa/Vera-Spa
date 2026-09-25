"""Bounded, read-only probe before replacing TimeSoft attendance.

Prints counts/status codes only, never photos, names, addresses or credentials.
It does not enroll faces or enable attendance calculation.
"""
import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import signal

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import vera_facegate_control_log as device

KEYS = {'VERA_FACEGATE_BASE_URL', 'VERA_FACEGATE_USERNAME', 'VERA_FACEGATE_PASSWORD',
        'VERA_FACEGATE_DEVICE_ID', 'VERA_FACEGATE_CONTROL_LOG_PATH'}


def reference(value):
    if not isinstance(value, dict):
        return None
    try:
        ref = tuple(int(value[k]) for k in ('file_type', 'file_index', 'file_position'))
        return ref if ref[0] == 0 and 0 <= ref[1] <= 65535 and 0 < ref[2] <= 2**63-1 else None
    except (KeyError, ValueError, TypeError):
        return None


def summarize(log, mappings):
    valid = [row for row in mappings if isinstance(row, dict) and row.get('confirmed_by') and row.get('username') and reference(row.get('registration_ref'))]
    references = Counter(reference(row['registration_ref']) for row in valid)
    codes = Counter()
    matched = 0
    for event in log.get('records', []):
        key = reference(event.get('registration_ref'))
        matched += bool(key and references[key] == 1)
        code = '/'.join(str(event.get(k) or '') for k in ('status_code', 'type_code'))
        codes[code if re.fullmatch(r'[0-9/-]{1,24}', code) else 'other'] += 1
    return {'sample_count': len(log.get('records', [])), 'device_total_count': log.get('total_count', 0),
            'sample_truncated': bool(log.get('truncated')), 'confirmed_mapping_count': len(valid),
            'sample_reference_matches': matched, 'raw_status_type_counts': dict(codes),
            'status_semantics_verified': False, 'device_enrollment_implemented': False,
            'attendance_cutover_ready': False}


def runtime_device_environment():
    for path in sorted((p for p in Path('/proc').iterdir() if p.name.isdigit()), key=lambda p:int(p.name), reverse=True):
        try:
            if b'vera_web_v2_api_v38:app' not in (path/'cmdline').read_bytes():
                continue
            for raw in (path/'environ').read_bytes().split(b'\0'):
                key, sep, value = raw.partition(b'=')
                name = key.decode('utf-8', 'replace')
                if sep and name in KEYS:
                    os.environ[name] = value.decode('utf-8', 'replace')
            return
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=datetime.now(device.VN_TZ).date().isoformat())
    args = parser.parse_args()
    engine = None
    def deadline(*_):
        raise TimeoutError('deadline')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(30)
    try:
        day = datetime.strptime(args.date, '%Y-%m-%d').date().isoformat()
        runtime_device_environment()
        from vera_vps_data_check import _database_url, _running_api_environment
        from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
        env = ({key: os.environ.get(key, '') for key in RUNTIME_ENV_KEYS}
               if load_managed_runtime_environment() else _running_api_environment())
        sslmode = env.get('DB_SSLMODE', 'require')
        if sslmode not in {'require','verify-ca','verify-full'}:
            sslmode = 'require'
        engine = create_engine(_database_url(env), poolclass=NullPool, connect_args={
            'connect_timeout':5, 'sslmode':sslmode,
            'options':'-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000'})
        with engine.connect() as conn:
            mappings = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='facegate' AND setting_key=:key"),
                                    {'key':'mapping_'+device.mapping_device_id()}).scalar() or []
            from vera_web_v2_devices import active_facegate_mappings
            mappings = active_facegate_mappings(conn, mappings if isinstance(mappings, list) else json.loads(mappings))
        # One page only. DB connection has been returned before device I/O.
        device.MAX_RECORDS = device.MAX_PAGE_SIZE
        from vera_web_v2_devices import use_registered_facegate
        with use_registered_facegate(engine):
            log = device.fetch_control_log(day, day)
        print(json.dumps({'ok':True, **summarize(log, mappings)}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok':False, 'error_type':type(exc).__name__, 'attendance_cutover_ready':False}))
        raise SystemExit(1) from None
    finally:
        signal.alarm(0)
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    main()

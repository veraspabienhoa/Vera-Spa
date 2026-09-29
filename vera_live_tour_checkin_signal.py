"""Coalesced check-in invalidation, committed atomically with the source cache.

Uses the existing refresh-event statement and projection worker. No new pool,
poller, per-browser job or attendance calculation is introduced here.
"""
import hashlib
import json
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

QUEUE = 'live_tour_projection'
JOB_KEY = 'checkin-change'
NAME_FIELDS = {'employeeinfo.name', 'employeename', 'name', 'fullname',
               'tennhanvien', 'employee.name'}
DAY_FIELDS = {'workdatestr', 'workdate', 'workingdatestr', 'workingdate'}
RAW_FIELDS = {'thoigian', 'time', 'timestr', 'datetime', 'datetimestr',
              'checktime', 'checktimestr', 'checkindatetime', 'checkindatetimestr',
              'checkintime', 'checkintimestr', 'machinetime', 'machinetimestr',
              'createdate', 'createdatestr', 'createtime', 'createtimestr'}


def _key(value):
    value = unicodedata.normalize('NFD', str(value).lower()).replace('đ', 'd')
    return ''.join(c for c in value if unicodedata.category(c) != 'Mn'
                   and not c.isspace() and c not in '_-')


def fingerprint(payload):
    """Ignore row order, duplicates, payroll, duration and vendor shift metadata.

    Retain every field the check-in reader can use, including checkout-field
    presence (which disables its generic raw-time fallback).
    """
    rows = set()
    for row in json.loads(payload):
        if not isinstance(row, dict):
            continue
        evidence = []
        for name, value in row.items():
            normalized = _key(name)
            if (normalized in NAME_FIELDS | DAY_FIELDS | RAW_FIELDS or
                (name.startswith(('MachineTimeCheckIn', 'LocalTimeCheckIn'))
                 and name.endswith('Str'))):
                evidence.append((name, value))
            elif name.startswith(('MachineTime', 'LocalTime')) and 'CheckOut' in name:
                evidence.append((name, True))
        # Field order matters to the raw reader's first-parseable-time fallback.
        rows.add(json.dumps(evidence, ensure_ascii=False, separators=(',', ':')))
    return hashlib.sha256(json.dumps(sorted(rows), ensure_ascii=False).encode()).hexdigest()


def record_refresh(conn, dataset_key, payload, detail, *, now=None):
    now = now or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    day = now.date()
    from vera_attendance_source import source_for
    prefix = source_for(day) + '_employee_checkin_'
    if dataset_key not in {prefix + 'today', prefix + day.strftime('%Y%m%d'),
                          prefix + day.strftime('%Y%m%d') + '_raw'}:
        return False
    conn.execute(text("""
        WITH refreshed AS (
            INSERT INTO vera_sync_event(dataset_key,event_type,detail)
            VALUES (:key,'refresh',:detail)
        )
        INSERT INTO vera_background_job AS job
            (queue_name,job_key,payload,status,attempts,available_at,created_at,updated_at)
        VALUES (:queue,:job,jsonb_build_object(
            'reason','checkin_changed','day',CAST(:day AS text),'generation',1,
            'fingerprints',jsonb_build_object(CAST(:key AS text),CAST(:fingerprint AS text))),
            'pending',0,NOW(),NOW(),NOW())
        ON CONFLICT(queue_name,job_key) DO UPDATE SET
            payload = EXCLUDED.payload || jsonb_build_object(
                'generation',COALESCE((job.payload->>'generation')::bigint,0)+1,
                'fingerprints',
                    (CASE WHEN job.payload->>'day'=:day
                     THEN COALESCE(job.payload->'fingerprints','{}'::jsonb)
                     ELSE '{}'::jsonb END) || (EXCLUDED.payload->'fingerprints')),
            status=CASE WHEN job.status='processing' THEN 'processing' ELSE 'pending' END,
            attempts=CASE WHEN job.status='processing' THEN job.attempts ELSE 0 END,
            available_at=CASE WHEN job.status IN ('pending','processing')
                              THEN job.available_at ELSE NOW() END,
            completed_at=NULL,last_error=NULL,updated_at=NOW()
        WHERE job.payload->>'day' IS DISTINCT FROM :day
           OR job.payload->'fingerprints'->>:key IS DISTINCT FROM :fingerprint
    """), {'key': dataset_key, 'detail': detail, 'queue': QUEUE, 'job': JOB_KEY,
             'day': day.isoformat(), 'fingerprint': fingerprint(payload)})
    return True

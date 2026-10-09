"""Archive known legacy ownership on the caller's transaction; never erase money.

Original rows remain in staff_retired_identity for audit. Unsupported references
are still rejected by prepare_reuse, rolling back this entire operation.
"""
from copy import deepcopy
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import text

CATEGORY = 'staff_retired_identity'
OWNER_FIELDS = {'payroll_history': 'Tên Hệ thống', 'tichluy': 'Tên nhân viên'}
MARKER = '__retired_identity'


def history_lock(conn):
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:staff-retired-history'))"))


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)


def _archive_row(row, owner_field, old, archived, norm):
    if not isinstance(row, dict) or norm(row.get(owner_field)) != norm(old):
        return row
    result = deepcopy(row)
    result[owner_field] = archived
    result[MARKER] = archived
    # Some legacy personal reports also match full name. Keep it readable but
    # prevent an identical account name from becoming a second ownership key.
    if norm(result.get('Họ và tên')) == norm(old):
        result['Họ và tên'] = str(result['Họ và tên']) + ' (đã nghỉ)'
    headers, raw = result.get('__sheet_header'), result.get('__raw_values')
    if isinstance(headers, list) and isinstance(raw, list):
        for index, header in enumerate(headers):
            if norm(header) == norm(owner_field) and index < len(raw):
                if norm(raw[index]) == norm(old):
                    raw[index] = archived
    return result


def archive_history(conn, old, archived, norm, actor):
    history_lock(conn)
    columns = conn.execute(text('''SELECT table_name,column_name FROM information_schema.columns
        WHERE table_schema=current_schema()''')).mappings().all()
    available = {}
    for col in columns:
        available.setdefault(col['table_name'], set()).add(col['column_name'])
    originals = []
    for table in ('vera_dataset_cache', 'vera_primary_dataset'):
        if not {'dataset_key', 'payload'} <= available.get(table, set()):
            continue
        for dataset, owner in OWNER_FIELDS.items():
            row = conn.execute(text(f'SELECT * FROM {table} WHERE dataset_key=:dataset FOR UPDATE'),
                               {'dataset': dataset}).mappings().first()
            if not row or not isinstance(row['payload'], list):
                continue
            before = row['payload']
            after = [_archive_row(item, owner, old, archived, norm) for item in before]
            if after == before:
                continue
            originals.append({'table': table, 'dataset': dataset, 'checksum': row.get('checksum'),
                              'rows': [item for item, changed in zip(before, after) if item != changed]})
            serialized = _json(after)
            updates = ['payload=CAST(:payload AS jsonb)']
            if 'checksum' in available[table]:
                updates.append('checksum=:checksum')
            if 'revision' in available[table]:
                updates.append('revision=revision+1')
            if 'updated_at' in available[table]:
                updates.append('updated_at=NOW()')
            conn.execute(text(f"UPDATE {table} SET {','.join(updates)} WHERE dataset_key=:dataset"),
                         {'dataset': dataset, 'payload': serialized,
                          'checksum': hashlib.sha256(serialized.encode('utf-8')).hexdigest()})
    # This is an audit subject, not an active leave/penalty record. IDs, before/
    # after snapshots, amounts and timestamps stay intact; preserve the original.
    if {'dataset', 'logical_id', 'payload'} <= available.get('vera_phase16_record', set()):
        rows = conn.execute(text("SELECT dataset,logical_id,payload FROM vera_phase16_record WHERE dataset='leave_activity_log' FOR UPDATE")).mappings().all()
        for row in rows:
            after = _archive_row(row['payload'], 'Tên nhân viên', old, archived, norm)
            if after == row['payload']:
                continue
            originals.append({'table': 'vera_phase16_record', 'dataset': row['dataset'],
                              'logical_id': row['logical_id'], 'rows': [row['payload']]})
            conn.execute(text('''UPDATE vera_phase16_record SET payload=CAST(:payload AS jsonb)
                WHERE dataset=:dataset AND logical_id=:id'''),
                {'payload': _json(after), 'dataset': row['dataset'], 'id': row['logical_id']})
    conn.execute(text('''INSERT INTO vera_app_setting
        (category,setting_key,value_json,source,updated_by,revision,updated_at)
        VALUES (:category,:key,CAST(:value AS jsonb),'staff_name_reuse',:actor,1,NOW())'''),
        {'category': CATEGORY, 'key': archived, 'actor': actor,
         'value': _json({'original_username': old, 'archived_username': archived, 'originals': originals})})


def _retirements(conn):
    if not conn.execute(text("SELECT to_regclass('vera_app_setting')")).scalar():
        return []
    return conn.execute(text('SELECT value_json FROM vera_app_setting WHERE category=:category'),
                        {'category': CATEGORY}).scalars().all()


def guard_legacy_snapshot(conn, dataset, records):
    """An unversioned legacy name cannot establish ownership after reuse.

    V2 saves use the current directory and their normal transaction. Legacy
    snapshots must use the archived name before they can be imported again.
    """
    if dataset not in OWNER_FIELDS:
        return
    from vera_web_v2_system_name import _name_key
    history_lock(conn)
    reused = {_name_key(item.get('original_username')) for item in _retirements(conn)}
    if any(isinstance(row, dict) and _name_key(row.get(OWNER_FIELDS[dataset])) in reused for row in records):
        raise HTTPException(409, 'Dữ liệu cũ có tên đã cấp cho nhân viên mới. Hãy dùng mã hồ sơ đã nghỉ trong dữ liệu Import để giữ đúng chủ sở hữu.')


def preserve_retired_audit(conn, dataset, rows):
    """Rebind a reimported old event by its stable ID, never by name alone."""
    if dataset != 'leave_activity_log':
        return
    history_lock(conn)
    ownership = {}
    for retirement in _retirements(conn):
        for original in retirement.get('originals', []):
            if original.get('table') == 'vera_phase16_record' and original.get('dataset') == dataset:
                ownership[original['logical_id']] = retirement['archived_username']
    for row in rows:
        archived = ownership.get(row['logical_id'])
        if archived:
            payload = json.loads(row['payload'])
            payload.update({'Tên nhân viên': archived, MARKER: archived})
            row['payload'] = _json(payload)

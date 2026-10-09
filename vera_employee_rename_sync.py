"""Employee reference migration and durable FaceGate name synchronization."""
from copy import deepcopy
import hashlib
import json
from sqlalchemy import text
from fastapi import HTTPException
from vera_staff_retired_history import history_lock

IDENTITY_FIELDS = frozenset({'username', 'employee_username', 'employee_name', 'trainer_username',
    'evaluator_username', 'recipient_username', 'Tên nhân viên', 'Tên hệ thống', 'Tên Hệ thống',
    'Nhân viên', 'Tên đăng nhập'})

def rename_json(value, old, new, *, employee=False):
    if isinstance(value, list):
        return [rename_json(v, old, new, employee=employee) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in {'__previous_usernames', '__retired_identity', 'originals', 'original_username'}:
            result[key] = item
        elif (key in IDENTITY_FIELDS or (employee and key == 'name')) and item == old:
            result[key] = new
        else:
            result[key] = rename_json(item, old, new, employee=key == 'employees')
    headers, raw = result.get('__sheet_header'), result.get('__raw_values')
    if isinstance(headers, list) and isinstance(raw, list):
        raw = list(raw)
        for i, header in enumerate(headers):
            if header in IDENTITY_FIELDS and i < len(raw) and raw[i] == old:
                raw[i] = new
        result['__raw_values'] = raw
    # Feature permissions identify account owners by target, never role targets.
    if isinstance(result.get('accounts'), list):
        for item in result['accounts']:
            if isinstance(item, dict) and item.get('target') == old:
                item['target'] = new
    return result


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def migrate_references(conn, old, new, actor):
    """Use the caller's connection and the normal Live Tour versioned writer."""
    import vera_web_v2_live_tour as tour
    history_lock(conn)
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:v2:feature_permissions'))"))
    if tour.resource_store.enabled():
        tour.resource_store.lock(conn)
        before, revision, _ = tour.resource_store.read(conn)
    else:
        tour.acquire_state_lock(conn, tour.STATE_LOCK)
        row = conn.execute(text("SELECT value_json,revision FROM vera_app_setting WHERE category='live_tour' AND setting_key='state' FOR UPDATE")).mappings().first()
        before, revision = (row['value_json'], row['revision']) if row else ({}, 0)
    after = rename_json(deepcopy(before), old, new)
    if after != before:
        tour._write_state(conn, after, revision, actor, previous_state=before)
    columns = conn.execute(text("SELECT c.table_name,c.column_name,c.data_type FROM information_schema.columns c JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name WHERE c.table_schema=current_schema() AND t.table_type='BASE TABLE' AND (c.data_type IN ('json','jsonb') OR c.column_name=ANY(:fields))"), {'fields': list(IDENTITY_FIELDS)}).mappings().all()
    available = {}
    all_cols = conn.execute(text('SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()')).mappings().all()
    for col in all_cols:
        available.setdefault(col['table_name'], set()).add(col['column_name'])
    counts = {}
    for col in columns:
        table, field, kind = col['table_name'], col['column_name'], col['data_type']
        # Device/raw evidence remains immutable; serving aliases resolve it.
        if (table.startswith('vera_live_tour_') and kind in {'json', 'jsonb'}) or table in {'employees', 'vera_facegate_rename_job'}:
            continue
        if kind not in {'json', 'jsonb'}:
            if kind not in {'text', 'character varying'}:
                continue
            result = conn.execute(text(f'UPDATE {quote(table)} SET {quote(field)}=:new WHERE {quote(field)}=:old'), {'old': old, 'new': new})
            if result.rowcount: counts[table + '.' + field] = result.rowcount
            continue
        # Never rewrite raw face punches, immutable request hashes or retired archives.
        if any(token in table for token in ('raw', 'control_log', 'mutation', 'receipt')):
            continue
        extra = " AND NOT (category='live_tour' AND setting_key='state') AND category<>'staff_retired_identity'" if table == 'vera_app_setting' else ''
        rows = conn.execute(text(f'SELECT ctid::text AS row_tid,{quote(field)} AS value FROM {quote(table)} WHERE {quote(field)}::text LIKE :needle{extra} FOR UPDATE'), {'needle': '%' + old.replace('%', '\\%').replace('_', '\\_') + '%'}).mappings().all()
        for row in rows:
            changed = rename_json(deepcopy(row['value']), old, new)
            if changed == row['value']: continue
            value = json.dumps(changed, ensure_ascii=False, separators=(',', ':'), default=str)
            updates = [f'{quote(field)}=CAST(:value AS {kind})']
            for hash_field in ('checksum', 'payload_hash'):
                if hash_field in available[table]: updates.append(f'{quote(hash_field)}=:digest')
            if 'revision' in available[table]: updates.append('revision=revision+1')
            if 'updated_at' in available[table]: updates.append('updated_at=NOW()')
            conn.execute(text(f'UPDATE {quote(table)} SET {",".join(updates)} WHERE ctid=CAST(:tid AS tid)'), {'value': value, 'digest': hashlib.sha256(value.encode()).hexdigest(), 'tid': row['row_tid']})
            counts[table + '.' + field] = counts.get(table + '.' + field, 0) + 1
    return counts


def ensure_jobs(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_facegate_rename_job (
        id bigserial PRIMARY KEY, employee_username text NOT NULL,
        device_id text NOT NULL, device_address text NOT NULL, profile_id bigint NOT NULL,
        old_name text NOT NULL, new_name text NOT NULL, registration_ref jsonb NOT NULL,
        status text NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
        updated_at timestamptz NOT NULL DEFAULT NOW())'''))


def queue_device_rename(conn, old, new):
    from vera_web_v2_facegate_enrollment import mappings, target
    from vera_facegate_control_log import mapping_device_id
    ensure_jobs(conn)
    if conn.execute(text("SELECT 1 FROM vera_facegate_rename_job WHERE employee_username=:old AND status='pending'"), {'old': old}).scalar():
        raise HTTPException(409, 'Tên trên máy Face ID đang chờ đồng bộ. Hãy hoàn tất đồng bộ trước khi đổi tên lần nữa.')
    if conn.execute(text("SELECT to_regclass('vera_facegate_enrollment')")).scalar() and conn.execute(text("SELECT 1 FROM vera_facegate_enrollment WHERE status IN ('running','unverified') LIMIT 1")).scalar():
        raise HTTPException(409, 'Máy Face ID đang đăng ký hoặc thay ảnh. Hãy hoàn tất lượt đó trước khi đổi tên.')
    device_id = mapping_device_id()
    rows = mappings(conn, device_id, lock=True)
    owned = [r for r in rows if r.get('username') in {old, new}]
    if not owned: return
    if len(owned) != 1 or not owned[0].get('confirmed_by') or not owned[0].get('registration_ref'):
        raise HTTPException(409, 'Cần xác nhận duy nhất một hồ sơ Face ID trước khi đổi tên.')
    entry = owned[0]
    address = target(conn)
    if entry.get('device_address') != address:
        raise HTTPException(409, 'IP máy Face ID đã thay đổi; cần đối chiếu lại ánh xạ.')
    conn.execute(text('''INSERT INTO vera_facegate_rename_job
        (employee_username,device_id,device_address,profile_id,old_name,new_name,registration_ref)
        VALUES (:username,:device,:address,:uid,:old,:new,CAST(:ref AS jsonb))'''),
        {'username': new, 'device': device_id, 'address': address, 'uid': entry['profile_id'],
         'old': entry['device_name'], 'new': new, 'ref': json.dumps(entry['registration_ref'])})


def sync_device_names(engine, username=None):
    """One serialized worker; no business connection/transaction during device I/O."""
    from vera_facegate_enrollment import FaceGateEnrollmentClient
    from vera_facegate_control_log import facegate_endpoint, mapping_device_id
    from vera_web_v2_facegate_enrollment import mappings, target
    pending = 0
    with engine.connect() as lock_conn:
        if not lock_conn.execute(text("SELECT pg_try_advisory_lock(hashtext('vera:facegate:rename-worker'))")).scalar():
            lock_conn.rollback()
            return {'status': 'pending'}
        lock_conn.commit()
        try:
            with engine.begin() as conn:
                ensure_jobs(conn)
                jobs = conn.execute(text("SELECT * FROM vera_facegate_rename_job WHERE status='pending' AND (CAST(:username AS text) IS NULL OR employee_username=:username) ORDER BY id LIMIT 10"), {'username': username}).mappings().all()
                registered = conn.execute(text('SELECT 1 FROM vera_facegate_rename_job WHERE employee_username=:username LIMIT 1'), {'username': username}).scalar() if username else True
            for job in jobs:
                client = None
                try:
                    with engine.begin() as conn:
                        if target(conn) != job['device_address'] or mapping_device_id() != job['device_id']:
                            raise ValueError('device_changed')
                        entries = mappings(conn, job['device_id'])
                        owned = [e for e in entries if e.get('profile_id') == job['profile_id']]
                        if len(owned) != 1 or owned[0].get('registration_ref') != job['registration_ref'] or owned[0].get('username') != job['employee_username']:
                            raise ValueError('mapping_changed')
                    with facegate_endpoint('http://' + job['device_address']):
                        client = FaceGateEnrollmentClient()
                        client.login()
                        client.rename_profile(int(job['profile_id']), job['old_name'], job['new_name'], job['registration_ref'])
                    with engine.begin() as conn:
                        entries = mappings(conn, job['device_id'], lock=True)
                        owned = [e for e in entries if e.get('profile_id') == job['profile_id'] and e.get('username') == job['employee_username'] and e.get('registration_ref') == job['registration_ref']]
                        if len(owned) != 1 or target(conn) != job['device_address']:
                            raise ValueError('mapping_changed')
                        owned[0]['device_name'] = job['new_name']
                        conn.execute(text("UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb),revision=revision+1,updated_at=NOW() WHERE category='facegate' AND setting_key=:key"), {'value': json.dumps(entries, ensure_ascii=False), 'key': 'mapping_' + job['device_id']})
                        conn.execute(text("UPDATE vera_facegate_rename_job SET status='verified',updated_at=NOW() WHERE id=:id"), {'id': job['id']})
                except Exception:
                    pending += 1
                    with engine.begin() as conn:
                        conn.execute(text('UPDATE vera_facegate_rename_job SET attempts=attempts+1,updated_at=NOW() WHERE id=:id'), {'id': job['id']})
                finally:
                    if client: client.close()
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(hashtext('vera:facegate:rename-worker'))"))
            lock_conn.commit()
    return {'status': 'pending' if pending else 'verified' if registered else 'not_registered'}

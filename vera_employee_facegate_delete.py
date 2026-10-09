"""Durable, identity-checked deletion of a departed employee's device profile."""
import json

from fastapi import HTTPException
from sqlalchemy import text


def ensure_jobs(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_facegate_delete_job (
        id bigserial PRIMARY KEY, employee_username text NOT NULL,
        device_id text NOT NULL, device_address text NOT NULL, profile_id bigint NOT NULL,
        device_name text NOT NULL, registration_ref jsonb NOT NULL,
        status text NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
        updated_at timestamptz NOT NULL DEFAULT NOW())'''))


def deletion_pending(conn):
    return bool(conn.execute(text("SELECT to_regclass('vera_facegate_delete_job')")).scalar()
                and conn.execute(text("SELECT 1 FROM vera_facegate_delete_job WHERE status='pending' LIMIT 1")).scalar())


def queue_employee_delete(conn, username):
    """Called before directory deletion, using its transaction and device lock."""
    from vera_web_v2_facegate_enrollment import mappings, target
    from vera_facegate_control_log import mapping_device_id
    ensure_jobs(conn)
    if conn.execute(text("SELECT to_regclass('vera_facegate_enrollment')")).scalar() and conn.execute(text(
            "SELECT 1 FROM vera_facegate_enrollment WHERE status IN ('running','unverified') LIMIT 1")).scalar():
        raise HTTPException(409, 'Máy Face ID đang có lượt đăng ký hoặc thay ảnh chưa xác minh. Hãy hoàn tất trước khi xoá nhân viên.')
    if conn.execute(text("SELECT to_regclass('vera_facegate_rename_job')")).scalar() and conn.execute(text(
            "SELECT 1 FROM vera_facegate_rename_job WHERE status='pending' LIMIT 1")).scalar():
        raise HTTPException(409, 'Máy Face ID đang chờ đồng bộ tên. Hãy hoàn tất trước khi xoá nhân viên.')
    if not conn.execute(text("SELECT to_regclass('vera_app_setting')")).scalar():
        return
    values = conn.execute(text("SELECT value_json FROM vera_app_setting WHERE category='facegate' AND setting_key LIKE 'mapping_%'")).scalars().all()
    owned = [entry for rows in values if isinstance(rows, list) for entry in rows
             if isinstance(entry, dict) and str(entry.get('username', '')).casefold() == username.casefold()]
    if not owned:
        if conn.execute(text("SELECT to_regclass('vera_facegate_enrollment')")).scalar() and conn.execute(text(
                "SELECT 1 FROM vera_facegate_enrollment WHERE lower(employee_username)=lower(:username) AND status='verified' LIMIT 1"),
                {'username': username}).scalar():
            raise HTTPException(409, 'Nhân viên đã đăng ký Face ID nhưng thiếu ánh xạ; cần đối chiếu trước khi xoá.')
        return
    device_id = mapping_device_id()
    current = mappings(conn, device_id, lock=True)
    if len(owned) != 1 or owned[0] not in current:
        raise HTTPException(409, 'Cần đối chiếu duy nhất một hồ sơ trên đúng máy Face ID trước khi xoá.')
    entry = owned[0]
    address = target(conn)
    if (not entry.get('confirmed_by') or not entry.get('registration_ref')
            or entry.get('device_address') != address or not entry.get('device_name')
            or type(entry.get('profile_id')) is not int or not 0 < entry['profile_id'] <= 2**31 - 1):
        raise HTTPException(409, 'Ánh xạ Face ID chưa xác minh hoặc IP máy đã đổi; chưa thể xoá an toàn.')
    if any(other != entry and (other.get('profile_id') == entry['profile_id']
                               or other.get('registration_ref') == entry['registration_ref']) for other in current):
        raise HTTPException(409, 'Hồ sơ Face ID đang gắn với nhân viên khác; cần đối chiếu trước khi xoá.')
    conn.execute(text('''INSERT INTO vera_facegate_delete_job
        (employee_username,device_id,device_address,profile_id,device_name,registration_ref)
        VALUES (:username,:device,:address,:uid,:name,CAST(:ref AS jsonb))'''),
        {'username': username, 'device': device_id, 'address': address,
         'uid': entry['profile_id'], 'name': entry['device_name'], 'ref': json.dumps(entry['registration_ref'])})
    current.remove(entry)
    conn.execute(text("UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb),revision=revision+1,updated_at=NOW() WHERE category='facegate' AND setting_key=:key"),
                 {'value': json.dumps(current, ensure_ascii=False), 'key': 'mapping_' + device_id})
    return True


def sync_employee_deletions(engine):
    """One pooled connection; every device call runs outside transactions."""
    from vera_facegate_enrollment import FaceGateEnrollmentClient
    from vera_facegate_control_log import facegate_endpoint, mapping_device_id
    from vera_web_v2_facegate_enrollment import mappings, target
    with engine.connect() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_lock(hashtext('vera:facegate:delete-worker'))")).scalar():
            conn.rollback()
            return {'status': 'pending'}
        conn.commit()
        try:
            with conn.begin():
                ensure_jobs(conn)
                jobs = conn.execute(text("SELECT * FROM vera_facegate_delete_job WHERE status='pending' ORDER BY id LIMIT 10")).mappings().all()
            for job in jobs:
                client = None
                try:
                    with conn.begin():
                        if target(conn) != job['device_address'] or mapping_device_id() != job['device_id']:
                            raise ValueError('device_changed')
                        entries = mappings(conn, job['device_id'])
                        if any(e.get('profile_id') == job['profile_id'] or e.get('registration_ref') == job['registration_ref'] for e in entries):
                            raise ValueError('mapping_changed')
                    with facegate_endpoint('http://' + job['device_address']):
                        client = FaceGateEnrollmentClient()
                        client.login()
                        client.delete_profile(int(job['profile_id']), job['device_name'], job['registration_ref'])
                    with conn.begin():
                        entries = mappings(conn, job['device_id'], lock=True)
                        if (target(conn) != job['device_address'] or any(
                                e.get('profile_id') == job['profile_id'] or e.get('registration_ref') == job['registration_ref'] for e in entries)):
                            raise ValueError('mapping_changed')
                        if conn.execute(text("SELECT to_regclass('vera_facegate_enrollment')")).scalar():
                            conn.execute(text("DELETE FROM vera_facegate_enrollment WHERE device_id=:device AND profile_id=:uid AND employee_username=:username"),
                                         {'device': job['device_id'], 'uid': job['profile_id'], 'username': job['employee_username']})
                        conn.execute(text("UPDATE vera_facegate_delete_job SET status='verified',updated_at=NOW() WHERE id=:id"), {'id': job['id']})
                except Exception:
                    with conn.begin():
                        conn.execute(text('UPDATE vera_facegate_delete_job SET attempts=attempts+1,updated_at=NOW() WHERE id=:id'), {'id': job['id']})
                finally:
                    if client:
                        client.close()
            with conn.begin():
                pending = conn.execute(text("SELECT count(*) FROM vera_facegate_delete_job WHERE status='pending'")).scalar()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(hashtext('vera:facegate:delete-worker'))"))
            conn.commit()
    return {'status': 'pending' if pending else 'verified'}

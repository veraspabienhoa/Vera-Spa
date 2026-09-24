"""Import a reviewed TimeSoft photo export. Default is read-only validation.

Manifest format: {"source":"timesoft", "entries":[{"employee_code":"...",
"username":"...", "file":"relative/path.jpg", "sha256":"...",
"mapping_confirmed":true}]}.
No name/facial matching, remote URL fetching, overwrite or device enrollment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from vera_web_v2_face_id import ensure_table, validate_photo

MAX_BATCH = 50


def load_batch(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError('manifest_too_large')
    body = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    entries = body.get('entries', [])
    if body.get('source') != 'timesoft' or not isinstance(entries, list) or not 1 <= len(entries) <= MAX_BATCH:
        raise ValueError('invalid_source_or_batch_size')
    root = manifest_path.parent
    names, codes, paths = set(), set(), set()
    batch = []
    for item in entries:
        username, code = str(item.get('username', '')).strip(), str(item.get('employee_code', '')).strip()
        if not username or not code or len(username) > 200 or len(code) > 64 or item.get('mapping_confirmed') is not True:
            raise ValueError('unconfirmed_mapping')
        path = (root / str(item.get('file', ''))).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('invalid_image_path')
        if username.casefold() in names or code.casefold() in codes or path in paths:
            raise ValueError('duplicate_mapping')
        names.add(username.casefold()); codes.add(code.casefold()); paths.add(path)
        if path.stat().st_size > 700 * 1024:
            raise ValueError('image_too_large')
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != item.get('sha256'):
            raise ValueError('image_hash_mismatch')
        content_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}.get(path.suffix.lower(), '')
        validate_photo(content, content_type)
        batch.append({'username': username, 'employee_code': code.casefold(), 'content': content,
                      'content_type': content_type, 'sha256': digest, 'size_bytes': len(content)})
    return batch


def plan_hash(batch):
    # Bind apply to reviewed username/code/image bytes; filename changes do not
    # change the destination or photo and therefore do not change the plan.
    public = sorted([{k: row[k] for k in ('username', 'employee_code', 'sha256')} for row in batch], key=lambda r: r['username'])
    return hashlib.sha256(json.dumps(public, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def import_batch(conn, batch, *, apply=False, expected_plan='', actor=''):
    digest = plan_hash(batch)
    if apply and (expected_plan != digest or not actor.strip()):
        raise ValueError('reviewed_plan_and_actor_required')
    table_exists = bool(conn.execute(text("SELECT to_regclass('vera_employee_face_id')")).scalar())
    audit_exists = bool(conn.execute(text("SELECT to_regclass('vera_face_id_import_audit')")).scalar())
    for row in batch:
        if audit_exists and conn.execute(text('SELECT 1 FROM vera_face_id_import_audit WHERE employee_code=:employee_code OR employee_username=:username'), row).scalar():
            raise ValueError('previously_imported_mapping')
        # Resolve exact usernames only. Lock targets during apply so deletion or
        # rename cannot race the import. Do not guess from a similar full name.
        user = conn.execute(text("SELECT username FROM employees WHERE username=:username AND COALESCE(payload->>'__deleted','false') <> 'true'" + (' FOR UPDATE' if apply else '')), row).scalar()
        if user != row['username']:
            raise ValueError('unknown_employee')
        if table_exists and conn.execute(text('SELECT 1 FROM vera_employee_face_id WHERE employee_username=:username'), row).scalar():
            raise ValueError('existing_photo_preserved')
    if apply:
        ensure_table(conn)
        conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_face_id_import_audit (
            employee_code text PRIMARY KEY, employee_username text NOT NULL UNIQUE,
            plan_sha256 text NOT NULL, image_sha256 text NOT NULL,
            source text NOT NULL, imported_by text NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT NOW())'''))
        for row in batch:
            conn.execute(text('''INSERT INTO vera_employee_face_id
                (employee_username,content,content_type,size_bytes,sha256,updated_by)
                VALUES (:username,:content,:content_type,:size_bytes,:sha256,:actor)'''), {**row, 'actor': actor})
            conn.execute(text("""INSERT INTO vera_face_id_import_audit
                (employee_code,employee_username,plan_sha256,image_sha256,source,imported_by)
                VALUES (:employee_code,:username,:digest,:sha256,'timesoft',:actor)"""),
                {**row, 'digest': digest, 'actor': actor})
    return {'count': len(batch), 'plan_sha256': digest, 'applied': apply}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--plan-sha', default='')
    parser.add_argument('--actor', default='')
    args = parser.parse_args()
    engine = None
    try:
        batch = load_batch(args.manifest)
        from vera_vps_data_check import _database_url, _running_api_environment
        from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment
        env = ({key: os.environ.get(key, '') for key in RUNTIME_ENV_KEYS}
               if load_managed_runtime_environment() else _running_api_environment())
        sslmode = env.get('DB_SSLMODE', 'require')
        if sslmode not in {'require', 'verify-ca', 'verify-full'}:
            sslmode = 'require'
        engine = create_engine(_database_url(env), poolclass=NullPool, connect_args={
            'connect_timeout': 5, 'sslmode': sslmode,
            'options': '-c statement_timeout=5000 -c lock_timeout=2000' + ('' if args.apply else ' -c default_transaction_read_only=on')})
        with engine.begin() as conn:
            result = import_batch(conn, batch, apply=args.apply, expected_plan=args.plan_sha, actor=args.actor)
        print(json.dumps(result))
    except Exception as exc:
        # Never print database connection strings, image paths or employee data.
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__, 'message': 'Import stopped; verify the import audit before retrying. Check manifest, permissions and existing photos.'}))
        raise SystemExit(1) from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    main()

"""Read-only explanation of an employee-name collision; no secrets in output."""
import argparse
import json

from sqlalchemy import text
from vera_employee_names import reserved_name
from vera_web_v2_staff import norm


def inspect(conn, username):
    conn.execute(text('SET TRANSACTION READ ONLY'))
    rows = conn.execute(text('''SELECT username, full_name,
        jsonb_build_object('__deleted',payload->'__deleted',
            '__previous_usernames',payload->'__previous_usernames',
            'Trạng thái làm việc',payload->'Trạng thái làm việc',
            'employment_status',payload->'employment_status') AS payload
        FROM employees ORDER BY username''')).mappings().all()
    matches = []
    for row in rows:
        if not reserved_name([row], username, norm):
            continue
        payload = row['payload'] or {}
        matches.append({'username': row['username'],
            'current_name_match': norm(row['username']) == norm(username),
            'deleted': str(payload.get('__deleted') or '').lower() == 'true',
            'employment_status': payload.get('Trạng thái làm việc') or payload.get('employment_status') or 'Đang làm việc',
            'previous_usernames': payload.get('__previous_usernames') or []})
    return {'ok': True, 'requested_name': username, 'matches': matches, 'database_writes': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    from vera_facegate_cutover import runtime_engine
    engine = None
    try:
        engine = runtime_engine()
        with engine.begin() as conn:
            result = inspect(conn, args.username.strip())
        print(json.dumps(result, ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__, 'database_writes': False}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

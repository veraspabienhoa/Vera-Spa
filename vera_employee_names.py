"""Explicit employee-name history; never infer identity from similar names.

This resolves VERA employee references only, not device evidence or login aliases.
Raw events, paid receipts and audit actors keep their original evidence.
"""
from sqlalchemy import text

HISTORY_KEY = '__previous_usernames'


def name_key(value):
    return str(value or '').strip().casefold()


def previous_names(row):
    payload = row.get('payload') or {}
    history = payload.get(HISTORY_KEY, []) if isinstance(payload, dict) else []
    names = [value for value in history if isinstance(value, str) and value.strip()] if isinstance(history, list) else []
    # Operator confirmation, 30-09-2026: Anh Nguyễn was renamed to Gia Anh.
    # Require the known directory identity and refuse occupied/ambiguous aliases
    # below. This is not a general reverse-name or accent-insensitive match.
    if (name_key(row.get('username')) == 'gia anh'
            and name_key(row.get('full_name')) == 'nguyễn gia anh'):
        names.extend(['Anh Nguyễn', 'Anh Nguyen'])
    return list(dict.fromkeys(names))


def identity_index(directory):
    rows = list(directory)
    current = {}
    for row in rows:
        key = name_key(row.get('username'))
        if key:
            current.setdefault(key, []).append(row)
    result = {key: owners[0] for key, owners in current.items() if len(owners) == 1}
    candidates = {}
    for row in rows:
        if str((row.get('payload') or {}).get('__deleted', False)).lower() == 'true':
            continue
        for alias in previous_names(row):
            key = name_key(alias)
            if key not in current:
                candidates.setdefault(key, {})[row['username']] = row
    for key, owners in candidates.items():
        if len(owners) == 1:
            result[key] = next(iter(owners.values()))
    return result


def reserved_name(directory, username, normalize=name_key):
    wanted = normalize(username)
    return any(wanted in {normalize(row.get('username')),
                          *(normalize(alias) for alias in previous_names(row))}
               for row in directory)


def load_identity_index(conn, *, lock=False):
    # Reuse the caller transaction; includes deleted names as occupied names.
    return identity_index(conn.execute(text(
        'SELECT username, full_name, payload FROM employees ORDER BY username'
        + (' FOR KEY SHARE' if lock else '')
    )).mappings().all())


def canonical_username(index, username):
    row = index.get(name_key(username))
    return str(row['username']) if row else str(username or '').strip()


def project_employee_rows(conn, rows):
    index = load_identity_index(conn)
    output = []
    for source in rows:
        row = dict(source)
        canonical = canonical_username(index, row.get('employee_username'))
        if canonical != row.get('employee_username'):
            row['employee_username'] = canonical
            row['employee_name'] = canonical
        output.append(row)
    return output

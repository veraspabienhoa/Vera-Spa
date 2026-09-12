"""Reconcile the persisted tour with the server employee directory without clearing work."""
from copy import deepcopy
import unicodedata
import re


def key(value):
    value = unicodedata.normalize('NFD', str(value or '').strip().lower())
    return ' '.join(''.join(c for c in value if unicodedata.category(c) != 'Mn').replace('đ', 'd').split())


def display_shift_label(item):
    name, start, end = (str(item.get(k) or '').strip() for k in ('Tên ca', 'Giờ bắt đầu', 'Giờ kết thúc'))
    label = f'{name} ({start} - {end})' if name and start and end else name
    if str(item.get('Ghi chú') or '').strip().casefold() == 'không đổi' and 'không đổi' not in label.casefold():
        label += ' (Không đổi)'
    return label


def shift_label(value, definitions=None):
    matches = [item for item in (definitions or []) if isinstance(item, dict)
               and key(item.get('Bộ phận') or 'Nhân viên + Leader') == key('Nhân viên + Leader')
               and key(item.get('Trạng thái')) != 'da xoa'
               and key(value) in {key(item.get('Tên ca')), key(display_shift_label(item))}]
    if len(matches) == 1 and matches[0].get('Ca chính') in {'Ca 1', 'Ca 2'}:
        return matches[0]['Ca chính']
    match = re.match(r'^ca\s*([12])(?:\b|\()', key(value))
    return f'Ca {match.group(1)}' if match else ''


def eligible(row):
    payload = row.get('payload') or {}
    return (str(row.get('role') or '').strip().lower() in {'leader', 'nhanvien'}
            and str(payload.get('__deleted', False)).lower() != 'true'
            and (payload.get('Trạng thái làm việc') or payload.get('employment_status') or 'Đang làm việc') == 'Đang làm việc'
            and bool(str(row.get('username') or '').strip()))


def reconcile(state, directory, make_employee):
    before = deepcopy(state)
    by_username = {key(row['username']): row for row in directory if row.get('username')}
    assigned = set()
    for worker in state['employees']:
        row = by_username.get(key(worker.get('username')))
        if row is None and not worker.get('username'):
            # Imported/free-text rows can be linked only when the name is unique.
            matches = [row for row in directory if key(worker.get('name')) in {key(row.get('username')), key(row.get('full_name'))}]
            row = matches[0] if len(matches) == 1 else None
        worker['roster_eligible'] = bool(row and eligible(row) and key(row['username']) not in assigned)
        if row:
            worker.update(name=row['username'], username=row['username'], role=str(row.get('role') or '').strip().lower())
            if 'work_shift' in row:
                worker['assigned_shift'] = shift_label(row.get('work_shift'), row.get('shift_definitions'))
                worker['shift'] = '' if key(worker.get('work_status')) == 'nghi phep' else worker['assigned_shift']
            assigned.add(key(row['username']))
    # The directory owns membership now that manual roster removal is retired.
    state.pop('roster_excluded_usernames', None)
    for row in directory:
        if eligible(row) and key(row['username']) not in assigned:
            worker = make_employee(row, len(state['employees']))
            worker['roster_eligible'] = True
            state['employees'].append(worker)
            if 'work_shift' in row:
                worker['assigned_shift'] = shift_label(row.get('work_shift'), row.get('shift_definitions'))
                worker['shift'] = '' if key(worker.get('work_status')) == 'nghi phep' else worker['assigned_shift']
            assigned.add(key(row['username']))
    state['employee_directory'] = [
        {'username': row['username'], 'name': row['username'], 'role': str(row['role']).strip().lower()}
        for row in directory if eligible(row)
    ]
    # Open receipts follow the display name; paid invoices/reports stay historical.
    names = {row['id']: row['name'] for row in state['employees']}
    for pending in state['pending']:
        for entry in pending.get('entries', []):
            if entry.get('employee_id') in names:
                entry['employee_name'] = names[entry['employee_id']]
    return state != before

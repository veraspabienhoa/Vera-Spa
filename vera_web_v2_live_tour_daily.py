"""Server directory/leave projections for the live board; no workbook connections."""
from vera_web_v2_live_tour_roster import key

FULL_DAY_REASONS = {
    'nghi co phep', 'nghi cuoi tuan co phep', 'nghi phep', 'nghi khong phep',
    'nghi cuoi tuan khong phep', 'nghi khong phep cuoi tuan', 'nghi phat sinh',
    'nghi benh co giay kham hoac duoc quan ly duyet', 'nghi dam hieu',
    'leader nghi phep theo chinh sach', 'nghi phep nam', 'phep nam', 'nghi phep quay video',
}


def sync_daily(state, directory, leaves):
    """Match usernames first, unique full names second; keep every service intact."""
    rows = {key(row['username']): row for row in directory}
    name_owners = {}
    for row in directory:
        name_owners.setdefault(key(row.get('full_name')), []).append(key(row['username']))
    by_user = {}
    for leave in leaves:
        name = key(leave.get('employee_name'))
        matches = name_owners.get(name, [])
        username = name if name in rows else matches[0] if len(matches) == 1 else ''
        if username:
            by_user.setdefault(username, []).append(leave)
    changed = 0
    for worker in state['employees']:
        if worker.get('roster_eligible') is False:
            continue
        username = key(worker.get('username') or worker.get('name'))
        if username not in rows:
            continue
        records = by_user.get(username, [])
        reasons = list(dict.fromkeys(str(row.get('leave_reason') or row.get('leave_type') or '').strip() for row in records))
        # Partial-day events (late arrival/early departure/support) remain working.
        absent = any(key(reason) in FULL_DAY_REASONS for reason in reasons)
        status = 'Nghỉ phép' if absent else 'Đi làm'
        previous_reason = worker.get('synced_leave_reason', '')
        current = worker.get('appointment', '')
        # Remove only our previous suffix, preserving receptionist appointments.
        if previous_reason and current.endswith(previous_reason):
            current = current[:-len(previous_reason)].removesuffix(' · ')
        reason = '; '.join(filter(None, reasons))
        appointment = ' · '.join(filter(None, [current, reason]))
        if worker.get('work_status') != status or worker.get('appointment', '') != appointment:
            changed += 1
        worker.update(work_status=status, appointment=appointment, synced_leave_reason=reason)
    return {'updated': changed, 'message': f'Đã cập nhật lịch nghỉ cho {changed} nhân viên.'}

"""Audited HC late approval; immutable event wages remain the pricing evidence.

No schema/backfill is needed: approval is versioned in the existing financial
record payload. Original event, wage segments, scans and minutes are never edited.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
import json

from fastapi import HTTPException
from sqlalchemy import text

KEY = 'hc_late_approval'
SOURCE = 'postgres:hc_rules'


def payload_dict(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return value if isinstance(value, dict) else {}


def price_basis(basis, day):
    """Reprice only a verified default 2× late component, never a mixed fine."""
    from vera_hc_rules import wage
    if not isinstance(basis, dict) or basis.get('kind') != 'late':
        raise ValueError('not_hc_late')
    rule = basis.get('rule') or {'mode': 'multiplier', 'value': 2}
    if rule.get('mode') != 'multiplier' or Decimal(str(rule.get('value'))) != 2:
        raise ValueError('custom_hc_policy')
    left, right = (datetime.fromisoformat(basis[key]) for key in ('start', 'end'))
    if not left.tzinfo or not right.tzinfo or right <= left:
        raise ValueError('invalid_late_interval')
    segments = basis.get('wage_segments')
    if not isinstance(segments, list) or not segments:
        raise ValueError('missing_wage_evidence')
    total, previous = Decimal(0), left
    for segment in sorted(segments, key=lambda s: s['start']):
        start, end = (datetime.fromisoformat(segment[key]) for key in ('start', 'end'))
        if not start.tzinfo or not end.tzinfo or start < previous or end <= start or end > right:
            raise ValueError('invalid_wage_evidence')
        if segment['shift'] not in {'Ca 1', 'Ca 2', 'Giờ làm'}:
            raise ValueError('invalid_wage_shift')
        if (basis['config'].get('calculation_mode') == 'hourly' and segment['shift'] == 'Giờ làm'
                and start.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date() > day):
            raise ValueError('historical_overnight_wage_bucket')
        total += wage(basis['config'], start, end, segment['shift'], work_day=day)
        previous = end
    if not total.is_finite() or total <= 0:
        raise ValueError('invalid_wage_amount')
    return {approved: int((total * multiplier).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            for approved, multiplier in ((False, 2), (True, 1))}


def metadata(row):
    """Public DTO contains approval/status, not private salary configuration."""
    payload = payload_dict(row.get('payload'))
    basis = payload.get('hc_basis')
    state = payload_dict(payload.get(KEY))
    result = {'hc_late_approval_eligible': False, 'hc_late_approved': state.get('approved') is True}
    if row.get('source_sheet_id') != SOURCE or not isinstance(basis, dict) or basis.get('kind') != 'late':
        return {}
    try:
        day = row.get('leave_date', row.get('violation_date'))
        day = date.fromisoformat(day) if isinstance(day, str) else day
        prices = price_basis(basis, day)
        if KEY in payload:
            stamp = datetime.fromisoformat(state['at'])
            if (state.get('version') != 1 or type(state.get('approved')) is not bool
                    or state.get('multiplier') != (1 if state['approved'] else 2)
                    or not state.get('actor') or not stamp.tzinfo
                    or not isinstance(state.get('event_id'), int) or state['event_id'] <= 0):
                raise ValueError('invalid_approval_audit')
        current = Decimal(str(row.get('penalty', row.get('amount'))))
        if payload.get('__schedule_violation_deleted') or current != prices[result['hc_late_approved']]:
            raise ValueError('fine_was_manually_changed')
        result.update(hc_late_approval_eligible=True, hc_late_minutes=basis.get('minutes'),
                      hc_late_approved_amount=prices[True], hc_late_unapproved_amount=prices[False],
                      hc_late_approved_by=state.get('actor'), hc_late_approved_at=state.get('at'))
    except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation, OverflowError):
        result['hc_late_approval_unavailable'] = 'Chưa đủ căn cứ lương gốc hoặc mức phạt đã được tùy chỉnh.'
    return result


def assert_not_finalized(conn, day, username):
    """Caller holds the same leave lock as HC payroll completion/save."""
    rows = conn.execute(text("""SELECT value_json FROM vera_app_setting
        WHERE category='payroll' AND (setting_key='department_payroll_combined_history'
          OR setting_key LIKE 'department_%_history')""")).mappings().all()
    month, username = day.strftime('%Y-%m'), str(username).strip().casefold()
    for row in rows:
        entries = row['value_json']
        if isinstance(entries, str):
            try:
                entries = json.loads(entries)
            except ValueError as exc:
                raise HTTPException(409, 'Chưa xác minh được lịch sử lương đã chốt. Không thay đổi phạt.') from exc
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise HTTPException(409, 'Chưa xác minh được lịch sử lương đã chốt. Không thay đổi phạt.')
        for entry in entries:
            if entry.get('month') != month:
                continue
            saved_rows = entry.get('rows')
            if not isinstance(saved_rows, list) or any(not isinstance(item, dict) for item in saved_rows):
                raise HTTPException(409, 'Chưa xác minh được lịch sử lương đã chốt. Không thay đổi phạt.')
            if any(str(item.get('employee_username') or '').strip().casefold() == username for item in saved_rows):
                raise HTTPException(409, 'Nhân viên đã có bảng lương chính thức trong tháng này. Không tự sửa phạt hoặc lịch sử đã chốt.')


def apply(conn, row, approved, actor, now):
    """Return revised payload/amount after checks; caller owns CAS and row lock."""
    info = metadata(row)
    if not info.get('hc_late_approval_eligible'):
        raise HTTPException(400, 'Chỉ áp dụng Đi trễ có phép cho phạt HC 2× có đủ căn cứ lương gốc, chưa chỉnh tiền thủ công.')
    if not conn.execute(text("SELECT to_regclass('vera_hc_penalty_event')")).scalar():
        raise HTTPException(409, 'Không tìm thấy sự kiện đi trễ HC gốc.')
    event = conn.execute(text('''SELECT * FROM vera_hc_penalty_event
        WHERE leave_record_uid=:uid FOR UPDATE'''), {'uid': row['record_uid']}).mappings().first()
    payload = deepcopy(payload_dict(row.get('payload')))
    try:
        matches = (event and event['kind'] == 'late' and event['work_date'] == row['leave_date']
                   and event['employee_name'] == row['employee_name']
                   and payload_dict(event['basis']) == payload.get('hc_basis')
                   and Decimal(str(event['amount'])) == info['hc_late_unapproved_amount']
                   and (KEY not in payload or payload[KEY]['event_id'] == event['id']))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        matches = False
    if not matches:
        raise HTTPException(409, 'Căn cứ đi trễ HC không khớp sự kiện gốc. Hãy kiểm tra trước khi thay đổi.')
    assert_not_finalized(conn, row['leave_date'], row['employee_name'])
    amount = info['hc_late_approved_amount'] if approved else info['hc_late_unapproved_amount']
    before = deepcopy(payload.get(KEY))
    payload[KEY] = {'version': 1, 'approved': approved, 'multiplier': 1 if approved else 2,
                    'actor': actor, 'at': now.isoformat(), 'event_id': event['id']}
    history = list(payload.get('schedule_violation_changes') or [])
    history.append({'action': 'hc_late_approval', 'actor': actor, 'at': now.isoformat(),
                    'before': {'approval': before, 'amount': str(row['penalty'])},
                    'after': {'approval': deepcopy(payload[KEY]), 'amount': amount}})
    payload['schedule_violation_changes'] = history
    payload['Phạt vi phạm'] = amount
    return payload, amount

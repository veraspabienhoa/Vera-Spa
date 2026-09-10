"""Audited customer/combo corrections, separate from immutable sales evidence."""
from copy import deepcopy
from uuid import uuid4
from fastapi import HTTPException


def change_customer(state, action, payload, actor, now, *, iso, bounded_number):
    reason = payload.get('reason')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise HTTPException(400, 'Nhập lý do sửa/xóa (tối đa 1000 ký tự).')
    allowed = {'customer_id', 'reason'}
    if action.startswith('customer_combo_'):
        allowed |= {'purchase_id'}
        if action.endswith('update'):
            allowed |= {'remaining', 'components', 'note'}
    if set(payload) - allowed:
        raise HTTPException(400, 'Nội dung điều chỉnh không hợp lệ.')
    working = deepcopy(state)
    customer = next((r for r in working['customers'] if r['id'] == payload.get('customer_id') and not r.get('deleted_at')), None)
    if not customer:
        raise HTTPException(404, 'Không tìm thấy khách hàng còn hiệu lực.')
    open_rows = [r for r in working['employees'] if r.get('service') and r.get('customer_id') == customer['id']]
    open_rows += [entry for r in working['pending'] if r.get('customer_id') == customer['id'] for entry in r.get('entries', [])]
    if action == 'customer_delete':
        if open_rows or any(not r.get('deleted_at') and int(r.get('remaining') or 0) > 0 for r in customer.get('combo_purchases', [])):
            raise HTTPException(409, 'Khách còn booking, phiếu chờ hoặc vé combo. Hãy xử lý các mục này trước khi xóa.')
        target = customer
    else:
        target = next((r for r in customer.get('combo_purchases', []) if r['id'] == payload.get('purchase_id') and not r.get('deleted_at')), None)
        if not target:
            raise HTTPException(404, 'Không tìm thấy combo còn hiệu lực.')
        if any(r.get('combo_purchase_id') == target['id'] for r in open_rows):
            raise HTTPException(409, 'Combo đang được giữ cho booking/phiếu chờ. Hãy xử lý phiên trước khi sửa/xóa.')
    before = deepcopy(target)
    if action.endswith('delete'):
        target['deleted_at'] = iso(now)
    else:
        number = lambda v: int(bounded_number(v, label='Số vé còn lại', minimum=0, maximum=100000, integer=True))
        if 'component_balances' in target:
            if sum(p.get('used', 0) for p in target['component_balances']) != target.get('used', 0):
                raise HTTPException(409, 'Số lượt đã dùng chưa khớp chi tiết dịch vụ; cần đối soát trước khi sửa.')
            parts = payload.get('components')
            if not isinstance(parts, list) or len(parts) != len(target['component_balances']):
                raise HTTPException(400, 'Cần nhập số lượt còn lại cho từng dịch vụ combo.')
            by_id = {}
            for part in parts:
                if not isinstance(part, dict) or set(part) != {'service_id', 'remaining'} or part['service_id'] in by_id:
                    raise HTTPException(400, 'Dịch vụ combo bị trùng hoặc không hợp lệ.')
                by_id[part['service_id']] = number(part['remaining'])
            if set(by_id) != {p['service_id'] for p in target['component_balances']}:
                raise HTTPException(400, 'Không đổi loại dịch vụ của combo đã mua.')
            for part in target['component_balances']:
                part['remaining'] = by_id[part['service_id']]
                part['total'] = part['used'] + part['remaining']
            target['remaining'] = number(sum(by_id.values()))
        else:
            target['remaining'] = number(payload.get('remaining'))
        target['total'] = target.get('used', 0) + target['remaining']
        if target['total'] > 100000:
            raise HTTPException(400, 'Tổng lượt combo vượt giới hạn.')
        if 'note' in payload:
            if not isinstance(payload['note'], str) or len(payload['note']) > 2000:
                raise HTTPException(400, 'Ghi chú không hợp lệ.')
            target['note'] = payload['note'].strip()
    target.update(updated_at=iso(now), updated_by=actor)
    working.setdefault('customer_changes', []).append({'id': str(uuid4()), 'action': action, 'actor': actor,
        'at': iso(now), 'customer_id': customer['id'], 'reason': reason.strip(), 'before': before, 'after': deepcopy(target)})
    state.clear(); state.update(working)
    return {'customer_id': customer['id'], 'changed': True}

"""Assign a catalog add-on to another worker without duplicating revenue."""
from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException


def is_addon(live, state, item):
    service = next((row for row in state['services'] if row['id'] == item.get('service_id')), {})
    return live._norm(service.get('name')) == 'them 1 ktv'


def paired(a, b):
    return bool(a.get('paired_booking_id') and a.get('paired_booking_id') == b.get('paired_booking_id')
                and (a.get('additional_ktv_id') == b.get('id') or a.get('primary_ktv_id') == b.get('id')))


def apply_booking(live, state, action, payload, actor, now):
    """Validate and commit both assignments together, using canonical booking checks."""
    original = live._employee(state, payload.get('employee_id'))
    if original.get('primary_ktv_id'):
        raise HTTPException(409, 'Hãy sửa dịch vụ tại Booking của KTV chính.')
    selected = payload.get('service_items')
    if not isinstance(selected, list):
        if original.get('additional_ktv_id'):
            raise HTTPException(400, 'Hãy chọn lại dịch vụ chính và KTV thêm.')
        return None
    extras = [item for item in selected if isinstance(item, dict) and is_addon(live, state, item)]
    if not extras and not original.get('additional_ktv_id'):
        if payload.get('additional_ktv_id'):
            raise HTTPException(400, 'Chỉ chọn KTV thêm khi có dịch vụ Thêm 1 KTV.')
        return None
    if extras and (len(extras) != 1 or extras[0].get('quantity', 1) != 1):
        raise HTTPException(400, 'Dịch vụ Thêm 1 KTV chỉ được chọn số lượng 1.')
    main_items = [item for item in selected if item not in extras]
    if not main_items:
        raise HTTPException(400, 'Hãy chọn dịch vụ chính trước khi thêm KTV.')
    target_id = str(payload.get('additional_ktv_id') or '') if extras else ''
    if extras and (not target_id or target_id == original['id']):
        raise HTTPException(400, 'Hãy chọn một KTV thêm khác KTV chính.')
    working = deepcopy(state)
    main = live._employee(working, original['id'])
    old_id = main.get('additional_ktv_id')
    old = live._employee(working, old_id) if old_id else None
    if old and (not paired(main, old) or not live._active_booking(old)):
        raise HTTPException(409, 'Phiên KTV thêm đã kết thúc; không thể sửa dịch vụ chính.')
    if old and old_id != target_id:
        if old.get('started_at'):
            raise HTTPException(409, 'KTV thêm đã thực hiện; không thể xóa hoặc đổi nhân viên.')
        live._clear_assignment(old, now)
    target = live._employee(working, target_id) if target_id else None
    group = main.get('paired_booking_id') or str(uuid4())
    main['additional_ktv_id'] = target_id
    main['paired_booking_id'] = group if target else ''
    # Only a stored reciprocal pair can share a bed. Client flags never grant it.
    if target:
        if old_id != target_id and (target.get('service') or target.get('primary_ktv_id') or target.get('additional_ktv_id')):
            raise HTTPException(409, 'KTV thêm đang có dịch vụ; hãy chọn nhân viên đang rảnh.')
        target.update(primary_ktv_id=main['id'], paired_booking_id=group)
    main_payload = {**payload, 'service_items': main_items, 'start_now': False}
    main_payload.pop('additional_ktv_id', None)
    result = live._apply_action_impl(working, action, main_payload, actor, now)
    main = live._employee(working, main['id'])
    if target:
        extra_payload = {'employee_id': target_id, 'service_items': extras, 'room': main['room'],
                         'request': main['request'], 'note': main.get('note', ''),
                         'customer_id': main.get('customer_id') or None,
                         'customer_name': main.get('customer_name', ''),
                         'customer_phone': main.get('customer_phone', '')}
        if old_id == target_id:
            live._apply_action_impl(working, 'update_booking', extra_payload, actor, now)
        else:
            live._booking(working, extra_payload, now, actor,
                          outside_shift=payload.get('_booking_outside_shift') is True)
        target = live._employee(working, target_id)
        target['duration'] = main['duration']
        target['service'] = f"Thêm 1 KTV & {main['service']}"
        for item in target.get('service_items', []):
            item['duration'] = main['duration']
        main['additional_ktv_item'] = deepcopy(extras[0])
    else:
        main.pop('additional_ktv_item', None)
    if payload.get('start_now'):
        live._start_employee(working, main, now, actor=actor)
        if target:
            live._start_employee(working, target, now, actor=actor)
    state.clear()
    state.update(working)
    result['employee'] = main
    return result

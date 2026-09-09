"""Server-owned TIP presets and percentage discounts for Live Tour receipts."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException


def default_settings():
    return {'auto_print': False, 'tip_cards': [
        {'id': f'tip-{amount}', 'name': f'{amount:,} đ'.replace(',', '.'), 'amount': amount}
        for amount in (50000, 100000, 200000, 300000, 500000)
    ]}


def settings_update(payload, money):
    if not isinstance(payload.get('auto_print'), bool):
        raise HTTPException(400, 'Tự động in phải là giá trị đúng/sai.')
    cards = payload.get('tip_cards')
    if not isinstance(cards, list) or len(cards) > 30:
        raise HTTPException(400, 'Cấu hình tối đa 30 thẻ TIP.')
    result = []
    identifiers = set()
    for card in cards:
        if not isinstance(card, dict):
            raise HTTPException(400, 'Thẻ TIP không hợp lệ.')
        name = str(card.get('name') or '').strip()
        identifier = str(card.get('id') or uuid4())
        if isinstance(card.get('amount'), bool):
            raise HTTPException(400, 'Mệnh giá thẻ TIP phải là số tiền.')
        amount = money(card.get('amount'), label='Mệnh giá thẻ TIP')
        if not name or len(name) > 80 or len(identifier) > 120 or identifier in identifiers or amount <= 0:
            raise HTTPException(400, 'Thẻ TIP cần tên, mệnh giá dương và mã không trùng.')
        identifiers.add(identifier)
        result.append({'id': identifier, 'name': name, 'amount': amount})
    return {'auto_print': payload['auto_print'], 'tip_cards': result}


def payment_values(state, payload, subtotal, money, max_money):
    mode = payload.get('discount_mode', 'amount')
    percent = None
    if mode == 'percent':
        try:
            raw = payload.get('discount_percent', 0)
            percent = Decimal(str(raw))
            if isinstance(raw, bool) or not percent.is_finite() or not 0 <= percent <= 100 or percent != percent.quantize(Decimal('.01')):
                raise ValueError()
        except (ValueError, InvalidOperation):
            raise HTTPException(400, 'Giảm giá phải từ 0 đến 100%, tối đa hai chữ số thập phân.') from None
        discount = int((Decimal(subtotal) * percent / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    elif mode == 'amount':
        discount = money(payload.get('discount'), label='Giảm giá', allow_blank_as_zero=True)
    else:
        raise HTTPException(400, 'Chọn giảm giá theo số tiền hoặc phần trăm.')
    if discount > subtotal:
        raise HTTPException(400, 'Giảm giá không được lớn hơn tạm tính.')
    tip = money(payload.get('tip'), label='Tiền tip', allow_blank_as_zero=True)
    selected = payload.get('tip_card_ids', [])
    if not isinstance(selected, list) or len(selected) > 30 or any(not isinstance(item, str) for item in selected) or len(set(selected)) != len(selected):
        raise HTTPException(400, 'Danh sách thẻ TIP không hợp lệ hoặc bị trùng.')
    cards = []
    if selected:
        if tip:
            raise HTTPException(400, 'Chọn nhập TIP hoặc dùng thẻ TIP, không cộng cả hai.')
        configured = (state.get('payment_settings') or default_settings())['tip_cards']
        for identifier in selected:
            card = next((row for row in configured if row['id'] == identifier), None)
            if card is None:
                raise HTTPException(409, 'Thẻ TIP đã thay đổi. Hãy tải lại và chọn thẻ còn hiệu lực.')
            cards.append(deepcopy(card))
        tip = sum(row['amount'] for row in cards)
    if tip > max_money:
        raise HTTPException(400, 'Tổng TIP vượt giới hạn cho phép.')
    return discount, tip, {'discount_mode': mode, 'discount_percent': float(percent) if percent is not None else None, 'tip_cards': cards}

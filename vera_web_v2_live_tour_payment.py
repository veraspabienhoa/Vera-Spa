"""Server-owned TIP presets and percentage discounts for Live Tour receipts."""
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException


def default_settings():
    return {'employee_change_minutes': 10, 'auto_print': False, 'open_receipt': True, 'bank': {'enabled': False, 'bank_id': '', 'account_no': '', 'account_name': ''}, 'tip_cards': [
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
    open_receipt = payload.get('open_receipt', True)
    bank = payload.get('bank', {'enabled': False, 'bank_id': '', 'account_no': '', 'account_name': ''})
    if not isinstance(open_receipt, bool) or not isinstance(bank, dict) or not isinstance(bank.get('enabled', False), bool):
        raise HTTPException(400, 'Cài đặt mở hóa đơn hoặc ngân hàng không hợp lệ.')
    bank = {'enabled': bank.get('enabled', False), **{key: str(bank.get(key) or '').strip() for key in ('bank_id', 'account_no', 'account_name')}}
    if any(len(bank[key]) > 100 for key in ('bank_id', 'account_no', 'account_name')):
        raise HTTPException(400, 'Thông tin ngân hàng quá dài.')
    if bank['enabled'] and (not re.fullmatch(r'[A-Za-z0-9]{2,20}', bank['bank_id']) or not re.fullmatch(r'[0-9]{6,19}', bank['account_no']) or not bank['account_name']):
        raise HTTPException(400, 'Cần mã ngân hàng, số tài khoản từ 6–19 chữ số và tên chủ tài khoản.')
    minutes = payload.get('employee_change_minutes', 10)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 180:
        raise HTTPException(400, 'Thời hạn đổi nhân viên phải từ 1 đến 180 phút.')
    return {'employee_change_minutes': minutes, 'auto_print': payload['auto_print'] and open_receipt, 'open_receipt': open_receipt, 'bank': bank,
            'tip_cards': sorted(result, key=lambda card: card['amount'])}


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


def profile_bank(row):
    """Profile stores VietQR shortName; never invent an account or bank code."""
    bank = {'enabled': True, 'bank_id': str(row.get('bank_name') or '').strip(),
            'account_no': str(row.get('bank_account') or '').strip(),
            'account_name': str(row.get('full_name') or '').strip()}
    if (not re.fullmatch(r'[A-Za-z0-9]{2,20}', bank['bank_id'])
            or not re.fullmatch(r'[0-9]{6,19}', bank['account_no']) or not bank['account_name']):
        return None
    return bank


def selected_bank(settings, viewer_bank, selection='auto'):
    if selection not in {'auto', 'user', 'default'}:
        raise HTTPException(400, 'Lựa chọn tài khoản nhận tiền không hợp lệ.')
    if selection == 'user' and not viewer_bank:
        raise HTTPException(409, 'Hồ sơ tài khoản đăng nhập chưa có ngân hàng hợp lệ.')
    return deepcopy(viewer_bank if selection in {'auto', 'user'} and viewer_bank else settings.get('bank') or {'enabled': False})

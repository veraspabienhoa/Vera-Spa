"""Import remaining service balances without creating sales revenue."""
from fastapi import HTTPException
from vera_web_v2_service_catalog import purchase_terms


def import_terms(combo, row, services, day, total, used, number):
    if not combo.get('components'):
        return {}
    terms = purchase_terms(combo, 1, services, day)
    balances = terms['component_balances']
    if len(balances) == 1:
        balances[0].update(total=total, used=used, remaining=total-used)
    else:
        supplied = row.get('component_remaining')
        if not isinstance(supplied, dict) or set(supplied) != {part['service_id'] for part in balances}:
            raise HTTPException(400, 'Nhập số lượt còn lại cho từng dịch vụ trong combo.')
        for part in balances:
            remaining = int(number(supplied[part['service_id']], label='Số lượt dịch vụ còn lại', minimum=0, maximum=100000, integer=True))
            part.update(total=remaining, used=0, remaining=remaining)
        if sum(part['remaining'] for part in balances) != total-used:
            raise HTTPException(400, 'Tổng số lượt còn lại không khớp các dịch vụ trong combo.')
    return terms

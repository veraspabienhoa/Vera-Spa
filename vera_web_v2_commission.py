"""Invoice-owned KTV earnings: TIP remains separate and payable at 100%."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json

from sqlalchemy import text


def number(value):
    return Decimal(str(value or 0))


def rounded(value):
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def refresh_commission(invoice):
    """Recalculate a corrected invoice using its original rates and combo terms."""
    snapshot = invoice.get('commission')
    if not snapshot:
        return
    entries = invoice.get('entries') or []
    weights = []
    for index, basis in enumerate(snapshot['basis']):
        entry = entries[index]
        gross = number(entry.get('combo_extra_subtotal', entry.get('quick_extra_subtotal', 0))) if invoice.get('combo_purchase_id') else number(entry.get('price'))
        weights.append(max(Decimal(0), gross))
    cash_total = sum(weights)
    net_total = max(Decimal(0), number(invoice.get('subtotal')) - number(invoice.get('discount')))
    rows = []
    for index, basis in enumerate(snapshot['basis']):
        if not basis['username'] or basis['department'] not in {'leader', 'nhanvien'}:
            continue
        share = weights[index] * net_total / cash_total if cash_total else Decimal(0)
        product_fraction = number(basis['product_fraction'])
        service_base = share * (1 - product_fraction) + number(basis['combo_base'])
        product_base = share * product_fraction
        rates = snapshot['policy']['rates'][basis['department']]
        rows.append({
            'username': basis['username'], 'department': basis['department'],
            'service_base': str(service_base), 'product_base': str(product_base),
            'service': rounded(service_base * number(rates['service']) / 100),
            'product': rounded(product_base * number(rates['product']) / 100),
        })
    snapshot['rows'] = rows


def record_commission(invoice, state, context):
    if not context['policy']['enabled'] or invoice.get('purchased_combo_id'):
        return
    customer = next((row for row in state['customers'] if row['id'] == invoice.get('customer_id')), {})
    purchase = next((row for row in customer.get('combo_purchases', []) if row['id'] == invoice.get('combo_purchase_id')), {})
    reports = [row for row in state['reports'] if row.get('invoice_id') == invoice['id']]
    covered_ids = {row['service_id'] for row in purchase.get('component_balances', [])}
    price, tickets = number(purchase.get('price')), number(purchase.get('total'))
    basis = []
    for index, entry in enumerate(invoice['entries']):
        items = entry.get('service_items') or []
        cash_items = entry.get('commission_cash_items', []) if invoice.get('combo_purchase_id') and not covered_ids else [item for item in items if not invoice.get('combo_purchase_id') or item.get('service_id') not in covered_ids]
        item_total = sum(number(item.get('unit_price')) * number(item.get('quantity', 1)) for item in cash_items)
        product_total = sum(number(item.get('unit_price')) * number(item.get('quantity', 1)) for item in cash_items if item.get('revenue_kind') == 'product')
        # Names in Live Tour are system usernames, matching the existing TIP adapter.
        username = str(entry.get('employee_name') or '').strip()
        units = number(reports[index].get('combo_units')) if index < len(reports) else Decimal(0)
        basis.append({
            'username': username, 'department': context['departments'].get(username, ''),
            'product_fraction': str(product_total / item_total if item_total else Decimal(0)),
            'combo_base': str(price * units / tickets if tickets else Decimal(0)),
            'combo_price': str(price), 'combo_tickets': str(tickets), 'combo_units': str(units),
        })
    invoice['commission'] = {'version': 1, 'policy': deepcopy(context['policy']), 'basis': basis}
    refresh_commission(invoice)


def payroll_commissions(conn, start, end, norm):
    """Use the caller's connection and current, non-void invoice ledger only."""
    from vera_web_v2_payroll import _setting
    import vera_live_tour_resource_store as store
    hr = _setting(conn, 'hr_registry', {})
    policy = hr.get('commission') or {}
    if not (policy.get('enabled') or policy.get('ever_enabled')):
        return {}
    if store.enabled():
        state, _, _ = store.read(conn, collections={'invoices'})
    else:
        state = conn.execute(text("""
            SELECT jsonb_build_object('invoices',value_json->'invoices') FROM vera_app_setting
            WHERE category='live_tour' AND setting_key='state' LIMIT 1
        """)).scalar_one_or_none()
    if isinstance(state, str):
        state = json.loads(state)
    result = {}
    seen = set()
    for invoice in (state or {}).get('invoices') or []:
        invoice_id = invoice.get('id')
        if not invoice_id or invoice_id in seen or invoice.get('purchased_combo_id'):
            continue
        seen.add(invoice_id)
        try:
            day = date.fromisoformat(str(invoice.get('business_date') or invoice.get('effective_at') or invoice.get('created_at'))[:10])
        except ValueError:
            continue
        if not start <= day <= end:
            continue
        for row in (invoice.get('commission') or {}).get('rows', []):
            key = norm(row['username'])
            totals = result.setdefault(key, {'service': 0, 'product': 0})
            for kind in totals:
                totals[kind] += int(row[kind])
    return result

export function invoiceServiceSubtotal(invoice = {}) {
  if (String(invoice.payment_method || '').toUpperCase() === 'COMBO' && !invoice.purchased_combo_id) {
    return Number(invoice.combo_extra_subtotal ?? 0)
  }
  if (invoice.subtotal != null) return Number(invoice.subtotal)
  return (invoice.entries || []).reduce((sum, entry) => sum + Number(entry.price || 0), 0)
}

export function invoiceMoneyValues(invoice = {}) {
  return {
    service: invoiceServiceSubtotal(invoice),
    discount: Number(invoice.discount || 0),
    tip: Number(invoice.tip || 0),
    total: Number(invoice.total || 0),
  }
}

export function latestCustomerPurchase(customer) {
  const purchases = (customer?.combo_purchases || []).filter(row => !row.deleted_at)
  const timestamp = row => Date.parse(row.effective_at || row.purchased_at || row.created_at || '') || 0
  return purchases.reduce((latest, row) => !latest || timestamp(row) >= timestamp(latest) ? row : latest, null)
}

export function customerComboRows(customers) {
  return customers.flatMap(customer => {
    const purchases = (customer.combo_purchases || []).filter(row => !row.deleted_at && Number(row.remaining || 0) > 0)
    return (purchases.length ? purchases : [null]).map(purchase => ({ customer, purchase, key: `${customer.id}:${purchase?.id || 'empty'}` }))
  })
}

export function comboTicketText(purchase) {
  return purchase ? `${purchase.combo_name || 'Combo'} · còn ${Number(purchase.remaining || 0)} vé` : ''
}

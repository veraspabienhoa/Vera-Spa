import { availableBookingPurchase, comboBookingItems, customerPurchases } from './liveTourComboBooking.js'
import { catalogIsAvailable, vietnamDate } from './serviceCatalog.js'

export function quickComboPurchases(customer, services, day = vietnamDate()) {
  return customerPurchases(customer).filter(purchase => !purchase.deleted_at)
    .map(purchase => availableBookingPurchase(purchase))
    .filter(purchase => {
      if (!catalogIsAvailable(purchase, day) || Number(purchase.remaining) <= 0) return false
      if (!purchase.component_balances) return true
      const items = comboBookingItems(purchase, services, day)
      return items.length > 0 && items.length <= 30 && items.length <= Number(purchase.remaining)
    })
}

export function autoQuickCombo(form, customers, services, today = vietnamDate()) {
  const customer = customers.find(row => String(row.id || row._id || row.customer_id || '') === String(form.customer_id || ''))
  const choices = quickComboPurchases(customer, services, form.booking_date || today)
  const purchase = choices.find(row => row.id === form.combo_purchase_id) || choices[0]
  return { ...form, quick_combo_auto: true, combo_purchase_id: purchase?.id || '',
    payment_method: purchase ? 'COMBO' : form.payment_method === 'COMBO' ? 'TIỀN MẶT' : form.payment_method,
    ...(purchase ? { service_id: '', discount: '0', discount_mode: 'amount', discount_percent: '0', ticket_price: '' } : {}) }
}

export function quickComboEntry(purchase, services, day = vietnamDate()) {
  if (!purchase) return null
  if (!purchase.component_balances) return { service: `Sử dụng combo: ${purchase.combo_name || 'Combo vé'}`,
    price: 0, price_source: 'combo_ticket', service_items: [] }
  const items = comboBookingItems(purchase, services, day).map(item => {
    const service = services.find(row => row.id === item.service_id)
    return { ...item, name: service.name, unit_price: Number(service.price || 0), ticket_units: 1 }
  })
  if (!items.length) return null
  return { service: items.map(item => item.name).join(' & '), price: items.reduce((total, item) => total + item.unit_price, 0),
    price_source: 'catalog', service_items: items }
}

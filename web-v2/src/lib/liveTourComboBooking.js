import { catalogIsAvailable, vietnamDate } from './serviceCatalog.js'

export const customerPurchases = (customer) => customer?.combo_purchases || customer?.combos || []

// A transaction can reuse its own reservation when editing or checking out.
export function availableBookingPurchase(purchase, ownEntries = []) {
  const own = ownEntries.filter((entry) => entry.combo_purchase_id === purchase.id)
  return {
    ...purchase,
    remaining: purchase.booking_remaining == null ? Number(purchase.remaining || 0)
      : Math.min(Number(purchase.remaining || 0), Number(purchase.booking_remaining) + own.reduce((sum, row) => sum + Number(row.combo_reserved_units || 0), 0)),
    ...(purchase.component_balances ? { component_balances: purchase.component_balances.map((part) => ({
      ...part,
      remaining: part.booking_remaining == null ? part.remaining : Math.min(Number(part.remaining), Number(part.booking_remaining)
        + own.flatMap((row) => row.combo_reserved_components || []).filter((row) => row.service_id === part.service_id).reduce((sum, row) => sum + Number(row.units || 0), 0)),
    })) } : {}),
  }
}

export function customerTicketLabel(customer) {
  const purchases = customerPurchases(customer)
  return purchases.length ? `Có thể đặt ${purchases.reduce((sum, row) => sum + availableBookingPurchase(row).remaining, 0)} vé combo` : ''
}

export function comboBookingItems(purchase, services, day = vietnamDate()) {
  // Legacy generic tickets have no service entitlement. Never guess from names.
  return (purchase?.component_balances || []).filter((part) => Number(part.remaining) > 0
    && services.some((service) => service.id === part.service_id && catalogIsAvailable(service, day)))
    .map((part) => ({ service_id: part.service_id, quantity: 1 }))
}

export function preferredBookingCombo(customer, services, day = vietnamDate()) {
  const purchases = customerPurchases(customer).map((purchase) => availableBookingPurchase(purchase))
  return purchases.find((purchase) => catalogIsAvailable(purchase, day) && purchase.remaining > 0
    && (!purchase.component_balances || comboBookingItems(purchase, services, day).length)) || purchases[0]
}

export function comboBookingError(purchase, items, services, day = vietnamDate()) {
  if (!purchase) return ''
  if (purchase.remaining <= 0) return 'Combo còn 0 vé có thể đặt lịch (đã hết hoặc đã được giữ chỗ).'
  if (!catalogIsAvailable(purchase, day)) return 'Combo đã hết hạn, chưa đến ngày sử dụng hoặc đã ngừng sử dụng.'
  if (purchase.component_balances && !items.length) return 'Combo không còn dịch vụ khả dụng. Hãy chọn combo khác.'
  let units = 0
  for (const item of items) {
    const service = services.find((row) => row.id === item.service_id)
    if (!service || !catalogIsAvailable(service, day)) return 'Dịch vụ trong combo hiện không khả dụng.'
    if (!Number.isInteger(item.quantity) || item.quantity < 1) return 'Số lượng dịch vụ phải là số nguyên dương.'
    const part = purchase.component_balances?.find((row) => row.service_id === item.service_id)
    if (purchase.component_balances && !part) continue
    if (part && item.quantity > part.remaining) return `${service.name} chỉ còn ${part.remaining} lượt có thể đặt lịch.`
    units += item.quantity * (part ? 1 : Number(service.ticket_units ?? 1))
  }
  return items.length && (units <= 0 || units > purchase.remaining) ? `Combo chỉ còn ${purchase.remaining} vé có thể đặt lịch, không đủ dùng ${units} vé.` : ''
}

// Sum every guest using the same owner's purchase before submitting the room.
// The server repeats this check under its customer lock when reserving tickets.
export function multiBookingCombos(rows, customers, services, day = vietnamDate()) {
  const grouped = new Map()
  for (const row of rows) {
    if (!row.combo_purchase_id) continue
    const key = JSON.stringify([row.customer_id, row.combo_purchase_id])
    const group = grouped.get(key) || { customer_id: row.customer_id, purchase_id: row.combo_purchase_id, items: new Map() }
    if (row.service_id) group.items.set(row.service_id, (group.items.get(row.service_id) || 0) + 1)
    grouped.set(key, group)
  }
  return [...grouped.values()].map(group => {
    const customer = customers.find(row => row.id === group.customer_id)
    const owned = customerPurchases(customer).find(row => row.id === group.purchase_id)
    if (!owned) return { ...group, error: 'Đang thiếu dữ liệu combo đã chọn. Hãy chờ tải xong hoặc chọn lại khách hàng.' }
    const purchase = availableBookingPurchase(owned)
    const items = [...group.items].map(([service_id, quantity]) => ({ service_id, quantity }))
    const units = items.reduce((sum, item) => sum + (purchase.component_balances
      ? (purchase.component_balances.some(part => part.service_id === item.service_id) ? item.quantity : 0)
      : item.quantity * Number(services.find(service => service.id === item.service_id)?.ticket_units ?? 1)), 0)
    return { customer_id: group.customer_id, purchase_id: group.purchase_id, customer_name: customer.name,
      combo_name: purchase.combo_name, available: purchase.remaining, units,
      remaining: Math.max(0, purchase.remaining - units), error: comboBookingError(purchase, items, services, day) }
  })
}

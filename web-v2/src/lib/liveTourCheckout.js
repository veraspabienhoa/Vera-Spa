export const money = (value) => Number(value || 0).toLocaleString('vi-VN') + ' đ'

// Freeze the same source fields used by the payment preview and note draft.
// A later board refresh must not replace the assignment beneath an open form.
export function checkoutEmployeeEntry(employee) {
  return structuredClone({
    employee_id: employee.id, employee_name: employee.name, service: employee.service,
    room: employee.room, booked_at: employee.booked_at, note: employee.note,
    price: employee.service_price, price_source: employee.service_price_source, service_items: employee.service_items,
    combo_purchase_id: employee.combo_purchase_id, combo_reserved_units: employee.combo_reserved_units,
    combo_reserved_components: employee.combo_reserved_components,
  })
}

export function tipCardLabel(card) {
  const name = String(card.name || '').trim()
  const amountOnly = /^[\d\s.,]+(?:đ|₫|vnd)?$/i.test(name)
    && Number(name.replace(/\D/g, '')) === Number(card.amount)
  return !name || amountOnly ? money(card.amount) : `${name} · ${money(card.amount)}`
}

export function defaultTipMode(key) {
  try { return window.localStorage.getItem(key) === 'cards' ? 'cards' : 'manual' } catch { return 'manual' }
}

export function bookingDateTime(value = Date.now()) {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return { date: '', time: '' }
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date).map((part) => [part.type, part.value]))
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` }
}

export function bookingTimeLabel(value) {
  const { date, time } = bookingDateTime(value || NaN)
  return date ? `${time} ${date.split('-').reverse().join('-')}` : '—'
}

import { employeeTourStart, tourStartOrder } from './liveTourOrder.js'

export const tourNameKey = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').trim().toLowerCase().replace(/\s+/g, ' ')

export function bookingEmployees(employees) {
  const ranking = (worker) => tourStartOrder(employeeTourStart(worker))
  return employees.filter((worker) => worker.roster_eligible !== false && !worker.hidden && tourNameKey(worker.work_status) === 'di lam' && ['ca 1', 'ca 2'].includes(tourNameKey(worker.shift)) && !worker.break_started_at && tourNameKey(worker.status) !== 'cho thanh toan')
    .sort((a, b) => { const x = ranking(a), y = ranking(b); return x[0] - y[0] || x[1] - y[1] || Number(a.sort_index || 0) - Number(b.sort_index || 0) || tourNameKey(a.name).localeCompare(tourNameKey(b.name)) })
}

export function bookingServiceItems(worker, catalog) {
  if (worker?.service_items?.length) return worker.service_items.map((item) => ({ service_id: item.service_id, quantity: item.quantity }))
  const name = worker?.service || ''
  if (!name) return []
  const exact = catalog.find((item) => tourNameKey(item.name) === tourNameKey(name))
  const names = exact ? [name] : name.split('&').map((item) => item.trim()).filter(Boolean)
  const counts = new Map()
  for (const name of names) {
    const item = catalog.find((item) => tourNameKey(item.name) === tourNameKey(name))
    if (item) counts.set(item.id, (counts.get(item.id) || 0) + 1)
  }
  return [...counts].map(([service_id, quantity]) => ({ service_id, quantity }))
}

export function bookingTotal(items, services) {
  return items.reduce((sum, item) => sum + Number(services.find((service) => service.id === item.service_id)?.price || 0) * Number(item.quantity || 0), 0)
}

export function discountAmount(subtotal, mode, value) {
  const number = Math.max(0, Number(value || 0))
  return mode === 'percent' ? Math.round(subtotal * Math.min(100, number) / 100) : number
}

// Match the server's _booking_timing: settling later preserves the booking date.
export function checkoutBookingTime(entries, pending, now = Date.now()) {
  const timestamp = value => {
    if (!value) return null
    const parsed = new Date(value).getTime()
    return Number.isFinite(parsed) ? parsed : null
  }
  const booked = entries.map(entry => timestamp(entry.booked_at)).filter(value => value !== null)
  return timestamp(pending?.effective_at) ?? timestamp(pending?.booked_at)
    ?? (booked.length ? Math.min(...booked) : null) ?? timestamp(pending?.created_at) ?? now
}

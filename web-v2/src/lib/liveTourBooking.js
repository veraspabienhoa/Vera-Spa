import { employeeTourStart, tourStartOrder } from './liveTourOrder.js'

export const tourNameKey = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').trim().toLowerCase().replace(/\s+/g, ' ')

export function bookingEmployees(employees, now = Date.now(), configuredMinutes = 30, boardRecords = []) {
  const minutes = Number.isInteger(configuredMinutes) && configuredMinutes >= 1 && configuredMinutes <= 180 ? configuredMinutes : 30
  const ranking = (worker) => tourStartOrder(employeeTourStart(worker))
  // The server numbers the full board after applying tour order. Imported stt,
  // sort_index and historical start times are not that displayed STT.
  const boardPositions = new Map(boardRecords.flatMap(record => {
    const id = String(record._employee_id ?? record.employee_id ?? '').trim()
    const position = Number(record.STT)
    return id && Number.isInteger(position) && position > 0 ? [[id, position]] : []
  }))
  const manualOrder = employees.some(worker => worker.manual_order)
  const idlePosition = worker => boardPositions.get(String(worker.id)) ?? Number.MAX_SAFE_INTEGER
  const isIdle = worker => !worker.service && !['dang thuc hien', 'dang su dung'].includes(tourNameKey(worker.status))
  return employees.filter((worker) => worker.roster_eligible !== false && !worker.hidden && tourNameKey(worker.work_status) === 'di lam' && ['ca 1', 'ca 2'].includes(tourNameKey(worker.shift)) && !worker.break_started_at && tourNameKey(worker.status) !== 'cho thanh toan')
    .filter(worker => {
      const status = tourNameKey(worker.status)
      if (status === 'dang cho') return false
      if (!['dang thuc hien', 'dang su dung'].includes(status)) return true
      const started = Date.parse(worker.started_at)
      if (!Number.isFinite(started) || worker.duration == null || !Number.isFinite(Number(worker.duration))) return false
      return started + Number(worker.duration) * 60000 - now < minutes * 60000
    })
    .sort((a, b) => {
      const aIdle = isIdle(a), bIdle = isIdle(b)
      if (aIdle !== bIdle) return aIdle ? -1 : 1
      if (aIdle) return idlePosition(a) - idlePosition(b) || Number(a.sort_index || 0) - Number(b.sort_index || 0)
      if (manualOrder) return Number(a.sort_index || 0) - Number(b.sort_index || 0)
      const x = ranking(a), y = ranking(b)
      return x[0] - y[0] || x[1] - y[1] || Number(a.sort_index || 0) - Number(b.sort_index || 0) || tourNameKey(a.name).localeCompare(tourNameKey(b.name))
    })
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

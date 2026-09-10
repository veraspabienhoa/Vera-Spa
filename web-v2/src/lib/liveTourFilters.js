export const EMPTY_TOUR_FILTERS = { preset: 'all', date_from: '', date_to: '', employee: '', customer: '', service: '' }
export const TOUR_DATE_PRESETS = [['all', 'Tất cả'], ['yesterday', 'Ngày hôm qua'], ['today', 'Hôm nay'], ['last-week', 'Tuần trước'], ['week', 'Tuần này'], ['last-month', 'Tháng trước'], ['month', 'Tháng này'], ['custom', 'Tùy chỉnh']]
const day = (value) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(value)
export function tourDateRange(preset, now = new Date()) {
  if (['all', 'custom'].includes(preset)) return { date_from: '', date_to: '' }
  const today = new Date(`${day(now)}T12:00:00+07:00`)
  const start = new Date(today), end = new Date(today)
  if (preset === 'yesterday') { start.setUTCDate(start.getUTCDate()-1); end.setTime(start.getTime()) }
  if (['week', 'last-week'].includes(preset)) {
    start.setUTCDate(start.getUTCDate() - (start.getUTCDay()+6)%7 - (preset === 'last-week' ? 7 : 0))
    end.setTime(start.getTime()); end.setUTCDate(end.getUTCDate()+6)
  }
  if (['month', 'last-month'].includes(preset)) {
    start.setUTCDate(1); if (preset === 'last-month') start.setUTCMonth(start.getUTCMonth()-1)
    end.setTime(start.getTime()); end.setUTCMonth(end.getUTCMonth()+1); end.setUTCDate(0)
  }
  return { date_from: day(start), date_to: day(end) }
}
const norm = (v) => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase().trim()
export function filterTourRows(rows, filters) {
  return rows.filter(row => {
    const dateValue = row.effective_at || row.booked_at || row.created_at || row.business_date
    const parsed = dateValue ? new Date(dateValue) : null
    const date = parsed && Number.isFinite(parsed.getTime()) ? day(parsed) : ''
    if ((filters.date_from && (!date || date < filters.date_from)) || (filters.date_to && (!date || date > filters.date_to))) return false
    if (filters.customer && !norm(`${row.customer_name || ''} ${row.customer_phone || ''}`).includes(norm(filters.customer))) return false
    const entries = row.entries?.length ? row.entries : [row]
    // Employee and service must match the same invoice line.
    return entries.some(entry => (!filters.employee || norm(entry.employee_name).includes(norm(filters.employee)))
      && (!filters.service || norm(entry.service).includes(norm(filters.service))))
  })
}
export function invoiceLocalTime(item) {
  const value = item.effective_at || item.booked_at || item.created_at
  const date = new Date(value)
  if (!value || !Number.isFinite(date.getTime())) return ''
  return new Date(date.getTime() + 7*3600000).toISOString().slice(0, 16)
}

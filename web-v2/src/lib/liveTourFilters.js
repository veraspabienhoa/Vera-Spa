import { searchTextMatches } from './searchText.js'
import { customerMatches } from './customerSearch.js'
export const EMPTY_TOUR_FILTERS = { preset: 'all', date_from: '', date_to: '', employee: '', customer: '', service: '', bill_no: '' }
export function invoiceNumbers(row) {
  if (!row || typeof row !== 'object') return []
  if (Array.isArray(row)) return row.flatMap(invoiceNumbers)
  return [row.bill_no, ...(row.bill_numbers || []), ...['before', 'after', 'invoice', 'pending', 'payload'].flatMap(key => invoiceNumbers(row[key]))].filter(Boolean)
}
export const TOUR_DATE_PRESETS = [['all', 'Tất cả'], ['yesterday', 'Hôm qua'], ['today', 'Hôm nay'], ['last-week', 'Tuần trước'], ['week', 'Tuần này'], ['last-month', 'Tháng trước'], ['month', 'Tháng này'], ['custom', 'Tùy chỉnh']]
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
export function defaultTourMonthFilters(now = new Date()) {
  return { ...EMPTY_TOUR_FILTERS, preset: 'month', ...tourDateRange('month', now) }
}
export function defaultTourYesterdayFilters(now = new Date()) {
  return { ...EMPTY_TOUR_FILTERS, preset: 'yesterday', ...tourDateRange('yesterday', now) }
}
export function tourRowDate(row) {
  let raw = String(row?.effective_at || row?.booked_at || row?.created_at || row?.business_date || '').trim()
  if (!raw) return ''
  const legacy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(raw)
  if (legacy) raw = `${legacy[3]}-${legacy[2].padStart(2, '0')}-${legacy[1].padStart(2, '0')}`
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) raw += 'T00:00:00+07:00'
  else if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(raw)) raw = raw.replace(' ', 'T') + '+07:00'
  const parsed = new Date(raw)
  return Number.isFinite(parsed.getTime()) ? day(parsed) : ''
}
export function filterTourRows(rows, filters) {
  return rows.filter(row => {
    if (filters.bill_no && !invoiceNumbers(row).some(number => String(number).toLowerCase().includes(filters.bill_no.trim().toLowerCase()))) return false
    const date = tourRowDate(row)
    if ((filters.date_from && (!date || date < filters.date_from)) || (filters.date_to && (!date || date > filters.date_to))) return false
    if (filters.customer && !customerMatches(row, filters.customer)) return false
    const entries = row.entries?.length ? row.entries : [row]
    // Employee and service must match the same invoice line.
    return entries.some(entry => (!filters.employee || searchTextMatches(entry.employee_name, filters.employee))
      && (!filters.service || searchTextMatches(entry.service, filters.service)))
  })
}
export function invoiceLocalTime(item) {
  const value = item.effective_at || item.booked_at || item.created_at
  const date = new Date(value)
  if (!value || !Number.isFinite(date.getTime())) return ''
  return new Date(date.getTime() + 7*3600000).toISOString().slice(0, 16)
}

// Suggestions come from the full active list, so typing never removes other choices.
export function tourFilterOptions(rows = []) {
  const values = { employee: new Set(), customer: new Set(), service: new Set(), bill_no: new Set() }
  const add = (key, value) => { if (String(value || '').trim()) values[key].add(String(value).trim()) }
  for (const row of rows) {
    invoiceNumbers(row).forEach(number => add('bill_no', number))
    add('customer', [row.customer_name, row.customer_phone].filter(Boolean).join(' - '))
    for (const entry of row.entries?.length ? row.entries : [row]) {
      add('employee', entry.employee_name)
      add('service', entry.service)
    }
  }
  return Object.fromEntries(Object.entries(values).map(([key, items]) => [key,
    [...items].sort((a, b) => a.localeCompare(b, 'vi')).map(label => ({ value: key === 'customer' ? label.replace(' - ', ' ') : label, label }))]))
}

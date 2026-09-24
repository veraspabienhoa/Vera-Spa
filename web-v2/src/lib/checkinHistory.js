import { tourDateRange, TOUR_DATE_PRESETS } from './liveTourFilters.js'

export const CHECKIN_PRESETS = TOUR_DATE_PRESETS.map(([id, label]) => [id, id === 'all' ? 'Tất cả (63 ngày gần nhất)' : label])
export const EMPTY_CHECKIN_DETAILS = { employee: '', event_id: '', event_date: '', status: '', event_type: '' }
export function checkinDateRange(preset, now = new Date()) {
  if (preset !== 'all') return tourDateRange(preset, now)
  const { date_from: end } = tourDateRange('today', now)
  const start = new Date(`${end}T00:00:00Z`)
  start.setUTCDate(start.getUTCDate() - 62)
  return { date_from: start.toISOString().slice(0, 10), date_to: end }
}
export function initialCheckinFilters(now = new Date()) {
  return { ...EMPTY_CHECKIN_DETAILS, source: 'facegate', preset: 'month', ...checkinDateRange('month', now) }
}
export function checkinQuery(filters) {
  return { source: filters.source, start: filters.date_from, end: filters.date_to,
    ...Object.fromEntries(Object.entries(EMPTY_CHECKIN_DETAILS).map(([key]) => [key, String(filters[key] || '').trim()])) }
}
export function checkinRangeError(filters) {
  if (!filters.date_from || !filters.date_to) return 'Vui lòng nhập đủ Từ ngày và Đến ngày.'
  const days = (Date.parse(filters.date_to) - Date.parse(filters.date_from)) / 86400000
  if (!Number.isFinite(days) || days < 0 || days > 62) return 'Chọn khoảng ngày hợp lệ, tối đa 63 ngày mỗi lần.'
  if (filters.event_date && (filters.event_date < filters.date_from || filters.event_date > filters.date_to)) return 'Ngày cụ thể phải nằm trong khoảng tra cứu.'
  return ''
}

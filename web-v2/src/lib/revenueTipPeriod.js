import { tourRowDate } from './liveTourFilters.js'

export function defaultRevenueTipStart(currentDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(currentDate || '').trim())
  if (!match) return ''
  return `${match[1]}-${match[2]}-${Number(match[3]) <= 15 ? '01' : '16'}`
}

export function revenueTipRowDate(row) {
  return tourRowDate(row)
}

export function revenueTipValue(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const raw = String(value ?? '').trim()
  if (!raw) return 0
  const cleaned = raw.replace(/[^0-9,.-]/g, '')
  if (!cleaned) return 0
  let normalized = cleaned
  if (cleaned.includes(',') && cleaned.includes('.')) {
    const decimal = cleaned.lastIndexOf(',') > cleaned.lastIndexOf('.') ? ',' : '.'
    const thousands = decimal === ',' ? '.' : ','
    normalized = cleaned.replaceAll(thousands, '').replace(decimal, '.')
  } else if (/^-?\d{1,3}([.,]\d{3})+$/.test(cleaned)) {
    normalized = cleaned.replace(/[.,]/g, '')
  } else if (cleaned.includes(',')) {
    normalized = cleaned.replace(',', '.')
  }
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

export function revenueTipTotal(rows, startDate, endDate) {
  if (!startDate || !endDate || startDate > endDate) return 0
  return Math.round((rows || []).reduce((sum, row) => {
    const rowDate = revenueTipRowDate(row)
    if (!rowDate || rowDate < startDate || rowDate > endDate) return sum
    return sum + revenueTipValue(row?.tip)
  }, 0) * 100) / 100
}

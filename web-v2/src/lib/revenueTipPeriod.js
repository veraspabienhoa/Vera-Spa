import { invoiceRowDate } from './liveTourFilters.js'

export function defaultRevenueTipStart(currentDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(currentDate || '').trim())
  if (!match) return ''
  return `${match[1]}-${match[2]}-${Number(match[3]) <= 15 ? '01' : '16'}`
}

export function revenueTipRowDate(row) {
  return invoiceRowDate(row)
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

// Calendar presets anchored to the Vietnam business day supplied by the caller.
export function revenueTipPreset(today, preset) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(today || '')) return null
  const [year, month, day] = today.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (parsed.toISOString().slice(0, 10) !== today) return null
  if (preset === 'previous_second') {
    const end = new Date(Date.UTC(year, month - 1, 0)).toISOString().slice(0, 10)
    return { start: `${end.slice(0, 7)}-16`, end }
  }
  if (preset === 'current_first') return { start: `${today.slice(0, 7)}-01`, end: `${today.slice(0, 7)}-15` }
  return null
}

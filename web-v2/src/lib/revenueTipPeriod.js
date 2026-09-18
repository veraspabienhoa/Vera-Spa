const vnDateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

export function defaultRevenueTipStart(currentDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(currentDate || '').trim())
  if (!match) return ''
  return `${match[1]}-${match[2]}-${Number(match[3]) <= 15 ? '01' : '16'}`
}

export function revenueTipRowDate(row) {
  const value = row?.business_date || row?.effective_at || row?.booked_at || row?.created_at
  if (!value) return ''
  const raw = String(value).trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw
  const vn = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(raw)
  if (vn) return `${vn[3]}-${vn[2].padStart(2, '0')}-${vn[1].padStart(2, '0')}`
  const parsed = new Date(raw)
  return Number.isFinite(parsed.getTime()) ? vnDateFormatter.format(parsed) : ''
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

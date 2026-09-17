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
  const value = row?.effective_at || row?.booked_at || row?.created_at || row?.business_date
  if (!value) return ''
  const raw = String(value).trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw
  const parsed = new Date(raw)
  return Number.isFinite(parsed.getTime()) ? vnDateFormatter.format(parsed) : ''
}

export function revenueTipTotal(rows, startDate, endDate) {
  if (!startDate || !endDate || startDate > endDate) return 0
  return Math.round((rows || []).reduce((sum, row) => {
    const rowDate = revenueTipRowDate(row)
    if (!rowDate || rowDate < startDate || rowDate > endDate) return sum
    const tip = Number(row?.tip || 0)
    return sum + (Number.isFinite(tip) ? tip : 0)
  }, 0) * 100) / 100
}

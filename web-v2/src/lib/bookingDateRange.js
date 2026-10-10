// Calendar arithmetic is independent of the browser timezone and DST.
export function bookingDateRange(period, now = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now).map(p => [p.type, p.value]))
  const today = new Date(`${parts.year}-${parts.month}-${parts.day}T00:00:00Z`)
  const shift = days => new Date(today.getTime() + days * 86400000).toISOString().slice(0, 10)
  if (period === 'today') return { date_from: shift(0), date_to: shift(0) }
  if (period === 'yesterday') return { date_from: shift(-1), date_to: shift(-1) }
  if (period === 'tomorrow') return { date_from: shift(1), date_to: shift(1) }
  const monday = -((today.getUTCDay() + 6) % 7) + (period === 'next-week' ? 7 : 0)
  return { date_from: shift(monday), date_to: shift(monday + 6) }
}

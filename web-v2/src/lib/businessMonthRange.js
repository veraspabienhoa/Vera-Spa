export function violationMonthRange(offset = 0) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date()).map(p => [p.type, p.value]))
  const first = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1 + offset, 1))
  const last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0))
  return { start: first.toISOString().slice(0, 10), end: last.toISOString().slice(0, 10), today: `${parts.year}-${parts.month}-${parts.day}` }
}


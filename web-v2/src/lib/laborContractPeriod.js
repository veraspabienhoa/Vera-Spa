export function contractPeriod(months = 1, now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit' }).formatToParts(now)
  const year = Number(parts.find(p => p.type === 'year').value)
  const month = Number(parts.find(p => p.type === 'month').value)
  return { contract_signed: `${year}-${String(month).padStart(2, '0')}-01`, contract_end: new Date(Date.UTC(year, month - 1 + Number(months), 0)).toISOString().slice(0, 10) }
}


// Payroll periods follow Vietnam business dates, regardless of the browser timezone.
export function currentPayrollPeriod(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now)
  const date = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return { month: `${date.year}-${date.month}`, periodNo: Number(date.day) <= 15 ? 1 : 2 }
}

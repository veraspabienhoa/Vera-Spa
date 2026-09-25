// All registration reads share the month of the selected date, in ISO calendar
// strings. No UTC conversion can move the last day into a neighboring month.
export function leaveMonthRange(month, start, end) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) throw new Error('Tháng không hợp lệ.')
  const [year, number] = month.split('-').map(Number)
  const first = `${month}-01`
  const last = `${month}-${String(new Date(year, number, 0).getDate()).padStart(2, '0')}`
  if (!start || !end || end < first || start > last) return [first, last]
  const clippedStart = start < first ? first : start > last ? last : start
  const clippedEnd = end > last ? last : end < clippedStart ? clippedStart : end
  return [clippedStart, clippedEnd]
}
